#!/usr/bin/env python3
"""
Relabel the vial-sort dataset from COLOR grammar -> POSITION (source->destination)
grammar, so the executor is addressed by SLOT, not colour:

    old:  "Place the red vial in position 6 of the right rack."
    new:  "Move the vial from position 4 of the left rack to position 6 of the right rack."
          "Move the vial from position 3 of the right rack to the bin."

WHY: with a VLM orchestrator doing the colour reasoning (Hi Robot style), the low-level
policy just needs "grab what's at slot X, put it at slot Y" -> unambiguous even with two
same-colour vials. The DEMONSTRATION is identical (you grabbed the starred target from its
slot and moved it to the dest); only the task TEXT changes, so NO re-recording and NO
video re-encode. Source + dest per episode come straight from ee/SORT_SHEET_v5.md (the '*'
marks the source slot, the '-> DEST' marks the destination).

Diverse paraphrases (many surface forms per src->dst) — same lesson as paraphrase_tasks.py:
one fixed template makes the policy IGNORE the language. Labels never mention colour, so the
model is forced to ground the SLOT (and two same-colour vials can't confuse it).

Run on the WS, AFTER convert_dataset.py (keys by episode_index, which convert preserves):
    .venv/bin/python ee/relabel_positions.py --root ./data/vial-sort-v5-ee \
        --repo-id sari-abdan/vial-sort-v5-pilot --dry-run     # preview
    .venv/bin/python ee/relabel_positions.py --root ./data/vial-sort-v5-ee \
        --repo-id sari-abdan/vial-sort-v5-pilot               # apply in-place
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lerobot.datasets.dataset_tools import modify_tasks
from lerobot.datasets.lerobot_dataset import LeRobotDataset

DEFAULT_SHEET = Path(__file__).parent / "SORT_SHEET_v5.md"

# ── paraphrase pools (position grammar; colour is deliberately never mentioned) ──
VERBS = ["Move", "Take", "Transfer", "Bring", "Relocate", "Carry"]
OBJECTS = ["the vial", "the tube", "the test tube", "the sample tube"]
POS_PHRASES = {
    1: ["position 1", "slot 1", "the first slot", "hole 1", "spot 1"],
    2: ["position 2", "slot 2", "the second slot", "hole 2", "spot 2"],
    3: ["position 3", "slot 3", "the third slot", "hole 3", "spot 3"],
    4: ["position 4", "slot 4", "the fourth slot", "hole 4", "spot 4"],
    5: ["position 5", "slot 5", "the fifth slot", "hole 5", "spot 5"],
    6: ["position 6", "slot 6", "the sixth slot", "hole 6", "the last slot"],
}
RACK_PHRASES = {
    "left":  ["the left rack", "the rack on the left", "the left-side rack", "the left tube rack"],
    "right": ["the right rack", "the rack on the right", "the right-side rack", "the right tube rack"],
}
BIN_PHRASES = ["the bin", "the trash", "the waste bin", "the trash can", "the rubbish bin"]

EP_RE = re.compile(r"^\s*ep\s+(\d+)\s*\|\s*L:\s*(.*?)\s*\|\s*R:\s*(.*?)\s*\|\s*->\s*(.*?)\s*$")


def _slot_phrase(slot: int, k: int) -> str:
    return POS_PHRASES[slot][k % len(POS_PHRASES[slot])]


def _rack_phrase(rack: str, k: int) -> str:
    return RACK_PHRASES[rack][k % len(RACK_PHRASES[rack])]


def position_paraphrase(src, dst, k: int) -> str:
    """Deterministic k-th paraphrase for a (source, destination) pair."""
    s_rack, s_slot = src
    v = VERBS[k % len(VERBS)]
    o = OBJECTS[(k // 2) % len(OBJECTS)]
    source = f"{_slot_phrase(s_slot, k)} of {_rack_phrase(s_rack, k // 2)}"
    if dst[0] == "bin":
        dest = BIN_PHRASES[k % len(BIN_PHRASES)]
    else:
        d_rack, d_slot = dst
        dest = f"{_slot_phrase(d_slot, k + 1)} of {_rack_phrase(d_rack, k // 3)}"
    forms = [
        f"{v} {o} from {source} to {dest}.",
        f"{v} {o} in {source} to {dest}.",
        f"{v} {o} from {source} over to {dest}.",
        f"{v} {o} at {source} into {dest}." if dst[0] == "bin"
        else f"{v} {o} at {source} to {dest}.",
    ]
    return forms[k % len(forms)]


def parse_sheet(path: Path) -> dict[int, tuple]:
    """ep_index -> ((src_rack, src_slot), ('bin', None) | (dst_rack, dst_slot))."""
    out: dict[int, tuple] = {}
    for line in Path(path).read_text().splitlines():
        m = EP_RE.match(line)
        if not m:
            continue
        ep = int(m.group(1))
        left = (m.group(2).split() + ["."] * 6)[:6]
        right = (m.group(3).split() + ["."] * 6)[:6]
        dest_str = m.group(4).strip().upper()

        src = None
        for i, c in enumerate(left):
            if c.endswith("*"):
                src = ("left", i + 1)
        for i, c in enumerate(right):
            if c.endswith("*"):
                src = ("right", i + 1)
        if src is None:
            raise ValueError(f"no '*' target on sheet line: {line!r}")

        if "BIN" in dest_str:
            dst = ("bin", None)
        else:
            dm = re.search(r"(LEFT|RIGHT)\s+POS\s+(\d+)", dest_str)
            if not dm:
                raise ValueError(f"can't parse dest {dest_str!r} on: {line!r}")
            dst = (dm.group(1).lower(), int(dm.group(2)))
        out[ep] = (src, dst)
    return out


def _old_dest(task: str):
    """Best-effort parse of the OLD colour label's destination, for a drift check."""
    t = task.lower()
    if "bin" in t or "trash" in t:
        return ("bin", None)
    m = re.search(r"position (\d+) of the (left|right) rack", t)
    return (m.group(2), int(m.group(1))) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-id", default="sari-abdan/vial-sort-v5-pilot")
    ap.add_argument("--root", default="./data/vial-sort-v5-ee")
    ap.add_argument("--sheet", default=str(DEFAULT_SHEET))
    ap.add_argument("--dry-run", action="store_true", help="print, don't modify")
    ap.add_argument("--force", action="store_true", help="apply even if a drift warning fires")
    args = ap.parse_args()

    sheet = parse_sheet(Path(args.sheet))
    ds = LeRobotDataset(args.repo_id, root=args.root)
    n = ds.meta.total_episodes

    combo_k: dict = {}
    episode_tasks: dict[int, str] = {}
    drift = []
    for i in range(n):
        if i not in sheet:
            raise SystemExit(f"[relabel] episode {i} not found in sheet {args.sheet} "
                             f"(sheet covers {min(sheet)}..{max(sheet)}). Aborting.")
        src, dst = sheet[i]
        # drift guard: does the OLD label's destination still match the sheet's?
        old = ds.meta.episodes[i]["tasks"]
        old = old[0] if isinstance(old, list) else old
        od = _old_dest(old)
        if od is not None and od != dst:
            drift.append((i, od, dst, old))
        k = combo_k.get((src, dst), 0)
        combo_k[(src, dst)] = k + 1
        episode_tasks[i] = position_paraphrase(src, dst, k)

    distinct = sorted(set(episode_tasks.values()))
    print(f"{n} episodes -> {len(combo_k)} source->dest combos, {len(distinct)} distinct paraphrases.")
    for i in range(min(n, 6)):
        print(f"  ep {i:03d}: {episode_tasks[i]}")
    if len(distinct) > 6:
        print(f"  ... (+{len(distinct) - 6} more distinct forms)")

    if drift:
        print(f"\n[!] DRIFT: {len(drift)} episode(s) where the OLD label's destination != the sheet's.")
        print("    This means the dataset and the sheet are out of order (a middle episode was")
        print("    deleted, or re-recorded off-index). Fix the alignment before relabeling.")
        for i, od, sd, old in drift[:8]:
            print(f"      ep {i}: old-dest={od}  sheet-dest={sd}   old={old!r}")
        if not args.force:
            raise SystemExit("Aborting. Re-run with --force only if you are sure the sheet is right.")

    if args.dry_run:
        print("\n[dry-run] no changes written.")
        return
    modify_tasks(ds, episode_tasks=episode_tasks)
    print(f"\nApplied POSITION labels in-place to {args.root}")


if __name__ == "__main__":
    main()

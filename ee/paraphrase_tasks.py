#!/usr/bin/env python3
"""
Instruction paraphrasing for the vial-sort dataset — the fix for "the model ignores
the prompt" (vision-shortcut / weak language grounding). v1/v2 used ONE template string,
so the language never varied -> the policy learned to ignore it. This rewrites each
episode's task into a DIVERSE paraphrase that still encodes the same meaning, forcing
the model to actually parse the COLOR and the DESTINATION.

v5 UPGRADE (2026-07-18): handles 4 COLORS (red/cyan/dark green/light purple) AND the
BIN/trash destination, to match ee/SORT_SHEET_v5.md. Round-robins a large paraphrase
pool per (color, destination) so every combo is seen under many surface forms.
NOT pi0-only — this diversity is needed by every VLA (pi0.5 / SmolVLA / GR00T).

In-place edit of the dataset's task metadata (no re-encode of videos/data).

Run on the WS:
    .venv/bin/python ee/paraphrase_tasks.py --root ./data/vial-sort-v5-ee \
        --repo-id sari-abdan/vial-sort-v5-pilot
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lerobot.datasets.dataset_tools import modify_tasks
from lerobot.datasets.lerobot_dataset import LeRobotDataset

VERBS = ["Place", "Put", "Move", "Set", "Drop", "Insert", "Position"]

# per-colour object phrasings (the model must parse WHICH colour is the target)
COLOR_OBJECTS = {
    "red":          ["the red vial", "the red tube", "the red test tube", "the red sample tube"],
    "cyan":         ["the cyan vial", "the cyan tube", "the light-blue vial", "the cyan test tube"],
    "dark green":   ["the dark green vial", "the green tube", "the dark-green test tube", "the green vial"],
    "light purple": ["the light purple vial", "the purple tube", "the light-purple vial", "the lilac tube"],
}
POS_PHRASES = {
    1: ["position 1", "slot 1", "the first slot", "spot 1", "the 1st position", "hole 1"],
    3: ["position 3", "slot 3", "the third slot", "spot 3", "the 3rd position", "hole 3"],
    6: ["position 6", "slot 6", "the sixth slot", "spot 6", "the 6th position", "the last slot"],
}
RACK_PHRASES = {
    "left":  ["the left rack", "the rack on the left", "the left-side rack", "the left tube rack"],
    "right": ["the right rack", "the rack on the right", "the right-side rack", "the right tube rack"],
}
BIN_PHRASES = ["the bin", "the trash", "the waste bin", "the rubbish bin", "the trash can"]
BIN_VERBS = ["Put", "Throw", "Drop", "Discard", "Toss", "Place"]


def parse_task(task: str):
    """-> (color, ('bin', None)) or (color, ('left'/'right', pos))."""
    t = task.lower()
    color = next((c for c in COLOR_OBJECTS if c in t), None)
    if color is None:
        raise ValueError(f"no known colour in: {task!r}")
    if "bin" in t or "trash" in t:
        return color, ("bin", None)
    m = re.search(r"position (\d+) of the (left|right) rack", t)
    if not m:
        raise ValueError(f"can't parse destination from: {task!r}")
    return color, (m.group(2), int(m.group(1)))


def paraphrase(color: str, dest, k: int) -> str:
    """Deterministic k-th paraphrase for (color, dest) — spreads across the pools."""
    rack, pos = dest
    o = COLOR_OBJECTS[color][(k // 2) % len(COLOR_OBJECTS[color])]
    if rack == "bin":
        v = BIN_VERBS[k % len(BIN_VERBS)]
        b = BIN_PHRASES[(k // 1) % len(BIN_PHRASES)]
        return f"{v} {o} in {b}." if k % 2 == 0 else f"{v} {o} into {b}."
    v = VERBS[k % len(VERBS)]
    p = POS_PHRASES[pos][k % len(POS_PHRASES[pos])]
    r = RACK_PHRASES[rack][(k // 3) % len(RACK_PHRASES[rack])]
    return [f"{v} {o} in {p} of {r}.", f"{v} {o} into {p} of {r}.",
            f"{v} {o} at {p} on {r}.", f"{v} {o} to {p} of {r}."][k % 4]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-id", default="sari-abdan/vial-sort-v5-pilot")
    ap.add_argument("--root", default="./data/vial-sort-v5-ee")
    ap.add_argument("--dry-run", action="store_true", help="print, don't modify")
    args = ap.parse_args()

    ds = LeRobotDataset(args.repo_id, root=args.root)
    n = ds.meta.total_episodes

    counters: dict = {}
    episode_tasks: dict[int, str] = {}
    for i in range(n):
        t = ds.meta.episodes[i]["tasks"]
        t = t[0] if isinstance(t, list) else t
        color, dest = parse_task(t)
        key = (color, dest)
        k = counters.get(key, 0)
        counters[key] = k + 1
        episode_tasks[i] = paraphrase(color, dest, k)

    distinct = sorted(set(episode_tasks.values()))
    print(f"{n} episodes, {len(counters)} (colour,dest) combos -> {len(distinct)} distinct paraphrases.")
    for s in distinct[:16]:
        print("   ", s)

    if args.dry_run:
        print("\n[dry-run] no changes written."); return
    modify_tasks(ds, episode_tasks=episode_tasks)
    print(f"\nApplied paraphrases in-place to {args.root}")


if __name__ == "__main__":
    main()

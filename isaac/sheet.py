"""
Parser for the v5 pilot recording sheet (ee/initial_fable_v5.txt).

The sheet is the single source of episode scenes + prompts, so the sim records
EXACTLY the same 200-episode pilot as the real rig would have.  Read-only —
never writes to ee/.

Episode line format:
  ep 003 | L: P* G  C  .  .  R  | R: .  .  .  .  .  .  | -> BIN
Run header carries the prompt:
  RUN 01/40   "Put the light purple vial in the bin."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

RUN_RE = re.compile(r'^RUN\s+\d+/\d+\s+"(.+)"')
EP_RE = re.compile(r"^\s*ep\s+(\d+)\s*\|\s*L:(.*?)\|\s*R:(.*?)\|\s*->\s*(.+?)\s*$")


@dataclass
class Episode:
    index: int                       # 0-based, == lerobot episode_index
    task: str                        # the run's prompt (dataset label)
    left: list[str | None] = field(default_factory=list)    # 6 slots: "R"/"C"/"G"/"P" or None
    right: list[str | None] = field(default_factory=list)
    target: tuple[str, int] = ("", 0)   # (rack, slot 1..6) of the starred vial
    dest: str = ""                   # "BIN" | "LEFT pos N" | "RIGHT pos N"

    def occupied(self) -> list[tuple[str, int, str]]:
        """[(rack, slot 1..6, color_letter), ...] for every vial in the scene."""
        out = []
        for rack, slots in (("left", self.left), ("right", self.right)):
            for i, c in enumerate(slots):
                if c is not None:
                    out.append((rack, i + 1, c))
        return out


def _parse_slots(chunk: str) -> tuple[list[str | None], int | None]:
    """'P* G  C  .  .  R' -> ([P,G,C,None,None,R], target_slot_or_None)."""
    tokens = chunk.split()
    if len(tokens) != 6:
        raise ValueError(f"expected 6 slot tokens, got {tokens!r}")
    slots: list[str | None] = []
    target = None
    for i, tok in enumerate(tokens):
        if tok == ".":
            slots.append(None)
        else:
            letter = tok.rstrip("*")
            if letter not in "RCGP":
                raise ValueError(f"unknown vial letter {tok!r}")
            slots.append(letter)
            if tok.endswith("*"):
                target = i + 1
    return slots, target


def parse_sheet(path: str) -> list[Episode]:
    episodes: list[Episode] = []
    task = None
    in_schedule = False  # the header's "HOW TO READ" example ep line must be skipped
    with open(path) as f:
        for line in f:
            if line.startswith("EPISODE SCHEDULE"):
                in_schedule = True
            if not in_schedule:
                continue
            m = RUN_RE.match(line.strip())
            if m:
                task = m.group(1)
                continue
            m = EP_RE.match(line)
            if not m:
                continue
            idx, left_s, right_s, dest = int(m.group(1)), m.group(2), m.group(3), m.group(4)
            left, tl = _parse_slots(left_s)
            right, tr = _parse_slots(right_s)
            if task is None:
                raise ValueError(f"episode {idx} appears before any RUN header")
            if (tl is None) == (tr is None):
                raise ValueError(f"episode {idx}: expected exactly one starred vial")
            target = ("left", tl) if tl is not None else ("right", tr)
            episodes.append(Episode(index=idx, task=task, left=left, right=right,
                                    target=target, dest=dest))
    if [e.index for e in episodes] != list(range(len(episodes))):
        raise ValueError("episode indices are not contiguous from 0 — sheet parse bug?")
    return episodes


# ── v4 mode: same scene, the ORIGINAL single-red-vial task ───────────────────
# Mirrors ee/record.py: one red vial, source = a slot on the OPPOSITE rack
# (anchor slots 1,3,4,6 cycled; 2,5 held out), exact v4 grammar. Default dests
# = the v4-merged coverage (left 1/3/6, right 6 — TRAINING_COVERAGE_v4.txt).
V4_TASK_TEMPLATE = "Place the red vial in position {n} of the {rack} rack."
V4_DESTS = [("left", 1), ("left", 3), ("left", 6), ("right", 6)]
V4_SOURCE_ANCHORS = [1, 3, 4, 6]


def make_v4_episodes(n_per_dest: int = 30, dests=tuple(V4_DESTS)) -> list[Episode]:
    """Interleaved v4 episode plan (destination rotates every episode)."""
    episodes = []
    for i in range(n_per_dest * len(dests)):
        rack, n = dests[i % len(dests)]                    # interleave ABCD ABCD…
        src_rack = "right" if rack == "left" else "left"   # source = opposite rack
        src_slot = V4_SOURCE_ANCHORS[(i // len(dests)) % len(V4_SOURCE_ANCHORS)]
        slots = {"left": [None] * 6, "right": [None] * 6}
        slots[src_rack][src_slot - 1] = "R"
        episodes.append(Episode(
            index=i, task=V4_TASK_TEMPLATE.format(n=n, rack=rack),
            left=slots["left"], right=slots["right"],
            target=(src_rack, src_slot), dest=f"{rack.upper()} pos {n}",
        ))
    return episodes


if __name__ == "__main__":
    from sim_config import SHEET_PATH

    eps = parse_sheet(SHEET_PATH)
    print(f"parsed {len(eps)} episodes")
    from collections import Counter

    print("dests:", Counter(e.dest for e in eps))

    def target_color(e: Episode) -> str:
        slots = e.left if e.target[0] == "left" else e.right
        return slots[e.target[1] - 1]

    print("target colors:", Counter(target_color(e) for e in eps))
    print("example:", eps[3])

    v4 = make_v4_episodes(n_per_dest=5)
    print(f"\nv4 mode: {len(v4)} episodes;", Counter(e.dest for e in v4))
    print("v4 example:", v4[0])

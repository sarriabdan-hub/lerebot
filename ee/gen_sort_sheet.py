#!/usr/bin/env python3
"""Generate the v5 FULL-SORT recording sheet (deterministic, seed=42).

Architecture: a VLM plans the sort and issues ATOMIC commands; this VLA learns
ONE skill -> "put the {color} vial in {destination}", color-grounded in clutter,
across 4 colors x 7 destinations (6 rack anchors + trash/bin), FULLY CROSSED so
the PROMPT controls the destination (not a learned color->slot shortcut).

Output: ee/SORT_SHEET_v5.md in the exact format record_v5.sh parses
(RUN NN/TT headers + `ep NNN | L: .. | R: .. | -> DEST` lines, episodes from 0).

  300 episodes = 60 runs x 5 (one label per run).
  PHASE A = runs 1-30 (eps 0-149): covers every (color,dest) combo >=1 -> EVAL here.
  PHASE B = runs 31-60 (eps 150-299): thickens to ~10 eps/combo.

Run:  python ee/gen_sort_sheet.py
"""
import random

SEED = 42
# 3 COLORS (Sari 2026-07-18: max 3, denser data). If your physical vials are a
# different trio, edit these two lines + rerun. Kept the 3 most distinct we use.
COLORS = {"R": "red", "C": "cyan", "G": "dark green"}
LETTERS = list(COLORS)                       # R C G
MAX_PER_RACK = 3                             # racks look realistically full, not sparse
ANCHOR_DEST_SLOTS = [1, 3, 6]                # trained rack slots (2/4/5 held out -> interpolation test)
SOURCE_SLOTS = [1, 3, 4, 6]                  # where the TARGET starts (2/5 held out)
RACKS = ["left", "right"]
EPS_PER_RUN = 5
N_RUNS = 60
PHASE_A_RUNS = 30
OUT = "ee/SORT_SHEET_v5.md"

# destinations: (rack, slot) rack slots + ("bin", None) trash
DESTS = [("bin", None)] + [(r, s) for r in RACKS for s in ANCHOR_DEST_SLOTS]  # 1 + 6 = 7


def dest_label(rack, slot):
    if rack == "bin":
        return "bin"
    return f"{rack.upper()} pos {slot}"


def run_prompt(color_letter, rack, slot):
    c = COLORS[color_letter]
    if rack == "bin":
        return f"Put the {c} vial in the bin."
    return f"Place the {c} vial in position {slot} of the {rack} rack."


def n_distractors(rng):
    # 2-4 distractors -> realistically full racks (scene = 3-5 vials)
    r = rng.random()
    return 4 if r < 0.30 else 3 if r < 0.70 else 2


def build_scene(rng, target_letter, dest):
    """Return (left[6], right[6]) with the starred target + distractors, under the
    PHYSICAL rules (Sari 2026-07-18, no stacking):
      * EVERY vial is SPACED — no two vials adjacent (+/-1) in the same rack. So the
        TARGET has both neighbours free (pick works) and so does any placement.
      * DEST slot is EMPTY with BOTH neighbours free (drop works — one neighbour was
        NOT ok in practice).
      * <=3 vials per rack; distractors never the target colour."""
    d_rack, d_slot = dest
    slots = {"left": [None] * 6, "right": [None] * 6}

    # place the TARGET in a source slot: not the dest, and not ADJACENT to the dest
    # in the same rack (keeps the dest's neighbours visibly empty in the layout).
    while True:
        s_rack = rng.choice(RACKS)
        s_slot = rng.choice(SOURCE_SLOTS)
        if d_rack == "bin" or s_rack != d_rack or abs(s_slot - d_slot) > 1:
            break
    s_i = s_slot - 1
    slots[s_rack][s_i] = target_letter + "*"

    # keep the DEST cell + both its neighbours empty (drop clearance)
    forbidden = set()
    if d_rack != "bin":
        d_i = d_slot - 1
        for di in (-1, 0, 1):
            forbidden.add((d_rack, d_i + di))

    others = [l for l in LETTERS if l != target_letter]
    # only 3 physical vials of each colour exist -> never ask for >3 of any colour
    # in one scene (the target already uses one of its colour).
    color_count = {target_letter: 1}
    per_rack = {"left": 1 if s_rack == "left" else 0,
                "right": 1 if s_rack == "right" else 0}
    want = n_distractors(rng)
    cand = [(r, i) for r in RACKS for i in range(6)
            if slots[r][i] is None and (r, i) not in forbidden]
    rng.shuffle(cand)
    placed = 0
    for (r, i) in cand:
        if placed >= want:
            break
        if per_rack[r] >= MAX_PER_RACK:
            continue
        # global SPACING: no vial immediately beside this cell (keeps every vial pickable)
        if (i > 0 and slots[r][i - 1]) or (i < 5 and slots[r][i + 1]):
            continue
        avail = [l for l in others if color_count.get(l, 0) < 3]
        if not avail:
            continue
        c = rng.choice(avail)
        slots[r][i] = c
        color_count[c] = color_count.get(c, 0) + 1
        per_rack[r] += 1
        placed += 1
    return slots["left"], slots["right"]


def fmt_row(row):
    # pad each cell to width 2 so the * on the target never breaks alignment
    return " ".join(f"{(c if c else '.'):<2}" for c in row).rstrip()


def main():
    rng = random.Random(SEED)

    # balanced combo assignment: every (color,dest) appears ~evenly across 60 runs
    combos = [(c, d) for c in LETTERS for d in DESTS]     # 4*7 = 28
    rng.shuffle(combos)
    run_combos = []
    i = 0
    while len(run_combos) < N_RUNS:
        if i % len(combos) == 0:
            rng.shuffle(combos)
        run_combos.append(combos[i % len(combos)])
        i += 1

    lines = []
    P = lines.append
    P("# SORT_SHEET_v5 — FULL vial-sort recording sheet (generated, seed=42)")
    P("")
    P("VLA learns ONE atomic skill: \"put the {color} vial in {destination}\", color-")
    P("grounded in clutter. A VLM chains these to do full sorting (mismatch -> trash).")
    P("300 eps = 60 runs x 5. Fully crossed: 4 colors x 7 destinations")
    P("(L1 L3 L6 R1 R3 R6 + BIN/trash). Rack slots 2/4/5 held out -> interpolation test;")
    P("source slots 2/5 held out too. Episodes 0-indexed = lerobot episode_index.")
    P("")
    P("HOW TO READ:  ep 000 | L: R* .  G  .  .  .  | R: .  C  .  .  .  .  | -> RIGHT pos 3")
    P("  6 cols/rack = slots 1..6.  . = empty.  R=red C=cyan G=dark-green.")
    P("  * = the TARGET (grasp THIS one).  '-> DEST' = where to place it.")
    P("  HOME the arm before EVERY episode. Set vials EXACTLY as shown.")
    P("")
    P("PERSPECTIVE (fixed, 2026-08-05) — everything is defined from the SIDE CAMERA")
    P("image (the front RealSense, ee/align/new_rack_side.png), NOT your body:")
    P("  * LEFT rack  = the rack on the LEFT of the side image (the one BY THE BIN).")
    P("  * RIGHT rack = the rack on the RIGHT of the side image.")
    P("  * Slots 1->6 = the holes counted LEFT-TO-RIGHT in the side image, BOTH racks")
    P("    (slot 1 = leftmost hole, slot 6 = rightmost).")
    P("  The side cam FACES you: its left rack is on YOUR right if you stand behind the")
    P("  arm -> ALWAYS set up + read labels against the side-cam view, never your body.")
    P("  Recommended: tape 'L'/'R' + number the holes 1-6 on the racks to match.")
    P("")

    ep = 0
    for run_i in range(N_RUNS):
        if run_i == 0:
            P("=" * 78)
            P("  PHASE A  (runs 1-30, eps 0-149)  >> EVAL pi0.5 HERE before Phase B <<")
            P("=" * 78)
        if run_i == PHASE_A_RUNS:
            P("=" * 78)
            P("  PHASE B  (runs 31-60, eps 150-299)  thicken to ~10 eps/combo")
            P("=" * 78)

        cletter, (drack, dslot) = run_combos[run_i]
        prompt = run_prompt(cletter, drack, dslot)
        arrow = "BIN" if drack == "bin" else dest_label(drack, dslot)
        P("")
        P(f'RUN {run_i + 1:02d}/{N_RUNS}   "{prompt}"')
        for _ in range(EPS_PER_RUN):
            left, right = build_scene(rng, cletter, (drack, dslot))
            P(f"  ep {ep:03d} | L: {fmt_row(left)} | R: {fmt_row(right)} | -> {arrow}")
            ep += 1

    P("")
    P("=" * 78)
    P(f"  TOTAL: {ep} episodes, {N_RUNS} runs. After each 25-ep session: audit_labels.py")
    P("=" * 78)

    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")

    # quick coverage report
    from collections import Counter
    cov = Counter((c, dest_label(*d)) for c, d in run_combos)
    ncombos = len(LETTERS) * len(DESTS)
    print(f"wrote {OUT}: {ep} eps, {N_RUNS} runs")
    print(f"combos covered: {len(cov)}/{ncombos}   runs/combo: min={min(cov.values())} max={max(cov.values())}")
    print(f"phase A runs 1-{PHASE_A_RUNS} cover "
          f"{len(set((c, dest_label(*d)) for c, d in run_combos[:PHASE_A_RUNS]))}/{ncombos} combos")


if __name__ == "__main__":
    main()

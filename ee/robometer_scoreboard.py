#!/usr/bin/env python3
"""
Failure-rate / success scoreboard. Turns per-run Robometer verdicts into an overall
"SUCCESS n/N = X%  (FAIL Y%)" plus a breakdown by source slot, destination, and (optionally)
colour — the "how many % failed" the boss asked for. No model / GPU needed here.

Two inputs:
  1) --results ee/eval_results.csv   (what ee/cv_run.py writes per run in the UI):
       columns include `prompt` (the task) and `rbm_verdict` / `rbm_success_peak`, with the
       operator's manual `outcome` used as an override when present.
  2) --scores ee/robometer_scores.jsonl  (what ee/assess_robometer.py writes for batch scoring):
       uses `success_max` (PEAK success) >= threshold as the verdict.

    python ee/robometer_scoreboard.py --results ee/eval_results.csv --threshold 0.5
    python ee/robometer_scoreboard.py --scores  ee/robometer_scores.jsonl [--colors ee/clip_colors.csv]

COLOUR: the position grammar never names the colour, so pass a `video,color` sidecar via --colors
to get a colour breakdown (only meaningful with --scores, which carries the video path).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

# ── Task-string parsing (source -> destination position grammar) ────────────────
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "6th": 6,
}
_BIN_WORDS = ("bin", "trash", "waste", "rubbish", "discard")
_SLOT_NOUNS = r"(?:position|slot|hole|spot)"
_NUM = r"(?:[1-6]|first|second|third|fourth|fifth|sixth|1st|2nd|3rd|4th|5th|6th)"
_SLOT_AFTER = re.compile(rf"{_SLOT_NOUNS}\s+({_NUM})\b", re.I)
_SLOT_BEFORE = re.compile(rf"\b({_NUM})\s+{_SLOT_NOUNS}\b", re.I)
_SIDE = re.compile(r"\b(left|right)\b", re.I)


def _num(token: str) -> int | None:
    token = token.lower()
    return int(token) if token.isdigit() else _ORDINALS.get(token)


def _ordered_slots(task: str) -> list[int]:
    hits: list[tuple[int, int]] = []
    for rx in (_SLOT_AFTER, _SLOT_BEFORE):
        for m in rx.finditer(task):
            n = _num(m.group(1))
            if n is not None:
                hits.append((m.start(), n))
    hits.sort(key=lambda x: x[0])
    out, seen = [], set()
    for pos, n in hits:
        if pos not in seen:
            seen.add(pos)
            out.append(n)
    return out


def parse_task(task: str) -> dict:
    """{source_slot, source_side, dest('bin'/'rack'), dest_slot, dest_side, ok}."""
    t = (task or "").lower()
    is_bin = any(w in t for w in _BIN_WORDS)
    slots = _ordered_slots(t)
    sides = [m.group(1).lower() for m in _SIDE.finditer(t)]
    res = {"source_slot": None, "source_side": None, "dest": None,
           "dest_slot": None, "dest_side": None, "ok": False}
    if not slots:
        return res
    res["source_slot"], res["source_side"] = slots[0], (sides[0] if sides else None)
    if is_bin:
        res["dest"], res["ok"] = "bin", True
        return res
    res["dest"] = "rack"
    if len(slots) >= 2:
        res["dest_slot"] = slots[1]
        res["dest_side"] = sides[1] if len(sides) >= 2 else None
        res["ok"] = True
    return res


# ── Loading records into a common shape: {task, ok(1/0/None)} ────────────────────
def _outcome_flag(val: str | None) -> int | None:
    if not val:
        return None
    v = str(val).strip().lower()
    if v in ("1", "y", "yes", "pass", "ok", "true") or v.startswith("s") or v.startswith("succ"):
        return 1
    if v in ("0", "n", "no", "fail", "false") or v.startswith("f") or v.startswith("drop"):
        return 0
    return None


def load_from_results(path: str, threshold: float) -> list[dict]:
    recs = []
    with open(path) as fh:
        for row in csv.DictReader(fh):
            task = row.get("prompt") or row.get("task") or ""
            manual = _outcome_flag(row.get("outcome"))
            ok = None
            rv = row.get("rbm_verdict")
            peak = row.get("rbm_success_peak")
            if rv not in (None, ""):
                ok = int(float(rv))
            elif peak not in (None, ""):
                ok = int(float(peak) >= threshold)
            if manual is not None:  # operator override wins
                ok = manual
            recs.append({"task": task, "ok": ok})
    return recs


def load_from_scores(path: str, threshold: float) -> list[dict]:
    recs = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        peak = r.get("success_max")
        if peak is None:  # older rows only had last-frame success
            peak = r.get("success_prob")
        ok = int(peak >= threshold) if peak is not None else None
        recs.append({"task": r.get("task", ""), "ok": ok, "video": r.get("video")})
    return recs


# ── Aggregation / reporting ──────────────────────────────────────────────────────
def _rate(bucket: list[int]) -> str:
    if not bucket:
        return "   —   (n=0)"
    return f"{100 * sum(bucket) / len(bucket):5.0f}%  (n={len(bucket)})"


def _load_colors(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    out = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            key = Path(row.get("video", "")).name
            col = (row.get("color") or row.get("colour") or "").strip().lower()
            if key and col:
                out[key] = col
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--results", help="ee/eval_results.csv from the cv_run UI")
    src.add_argument("--scores", help="ee/robometer_scores.jsonl from assess_robometer.py")
    ap.add_argument("--colors", default=None, help="optional video,color sidecar (with --scores)")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="success_peak >= threshold counts as a success")
    ap.add_argument("--out", default="ee/robometer_scoreboard.json")
    args = ap.parse_args()

    if args.results:
        recs = load_from_results(args.results, args.threshold)
    else:
        recs = load_from_scores(args.scores, args.threshold)
    colors = _load_colors(args.colors)

    graded = [r for r in recs if r["ok"] is not None]
    n = len(graded)
    n_ok = sum(r["ok"] for r in graded)
    n_fail = n - n_ok

    by_source: dict[int, list[int]] = defaultdict(list)
    by_dest: dict[str, list[int]] = defaultdict(list)
    by_color: dict[str, list[int]] = defaultdict(list)
    n_unparsed = 0
    for r in graded:
        p = parse_task(r["task"])
        if not p["ok"]:
            n_unparsed += 1
            continue
        if p["source_slot"]:
            by_source[p["source_slot"]].append(r["ok"])
        dest_key = "bin" if p["dest"] == "bin" else (str(p["dest_slot"]) if p["dest_slot"] else "?")
        by_dest[dest_key].append(r["ok"])
        col = colors.get(Path(r.get("video") or "").name)
        if col:
            by_color[col].append(r["ok"])

    print(f"\n=== Robometer scoreboard — {len(recs)} runs ({n} graded), threshold={args.threshold} ===")
    if n == 0:
        print("  (no graded runs yet)")
        return
    print(f"\n  SUCCESS {n_ok}/{n} = {100 * n_ok / n:.0f}%     FAIL {n_fail}/{n} = {100 * n_fail / n:.0f}%")
    if n_unparsed:
        print(f"  ({n_unparsed} run(s) had an unparseable task — excluded from the breakdowns)")

    print("\n  SUCCESS by DESTINATION (rack slot / bin):")
    for d in sorted(by_dest, key=lambda k: (k == "bin", k)):
        print(f"    dest {d:>3}: {_rate(by_dest[d])}")
    print("\n  SUCCESS by SOURCE slot:")
    for s in sorted(by_source):
        print(f"    source {s}: {_rate(by_source[s])}")
    if by_color:
        print("\n  SUCCESS by COLOUR:")
        for c in sorted(by_color):
            print(f"    {c:>10}: {_rate(by_color[c])}")

    def _summ(d):
        return {str(k): {"n": len(v), "success_rate": (sum(v) / len(v) if v else None)}
                for k, v in d.items()}

    Path(args.out).write_text(json.dumps({
        "n_runs": len(recs), "n_graded": n, "success": n_ok, "fail": n_fail,
        "success_rate": (n_ok / n if n else None), "threshold": args.threshold,
        "by_destination": _summ(by_dest), "by_source_slot": _summ(by_source),
        "by_color": _summ(by_color),
    }, indent=2))
    print(f"\n  wrote {args.out}")


if __name__ == "__main__":
    main()

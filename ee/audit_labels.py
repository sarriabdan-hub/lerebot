#!/usr/bin/env python3
"""Audit a LeRobot dataset's episode->task labels (find the mis-recorded session).

Prints every episode index with its task string, plus a per-task count summary, so you
can line the dataset up against the recording sheet and spot label mistakes before v5
merges old episodes in.

Usage:
    .venv/bin/python ee/audit_labels.py --root ./data/vial-sort-v4-merged-ee
    .venv/bin/python ee/audit_labels.py --root ./data/vial-sort-v2-static --group
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def load_episodes(root: Path):
    """Yield (episode_index, [task, ...]) across v2.x (jsonl) and v3 (parquet) layouts."""
    jl = root / "meta" / "episodes.jsonl"
    if jl.exists():
        for line in jl.read_text().splitlines():
            d = json.loads(line)
            yield d["episode_index"], d.get("tasks", [d.get("task", "?")])
        return
    pq_dir = root / "meta" / "episodes"
    files = sorted(pq_dir.rglob("*.parquet")) if pq_dir.exists() else []
    if files:
        import pandas as pd
        for f in files:
            df = pd.read_parquet(f)
            tcol = "tasks" if "tasks" in df.columns else "task"
            for _, row in df.iterrows():
                t = row[tcol]
                yield int(row["episode_index"]), list(t) if not isinstance(t, str) else [t]
        return
    raise SystemExit(f"no meta/episodes.jsonl or meta/episodes/*.parquet under {root}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="dataset root dir (contains meta/)")
    ap.add_argument("--group", action="store_true",
                    help="print consecutive same-task runs instead of every episode "
                         "(fast way to see the session blocks)")
    args = ap.parse_args()

    eps = sorted(load_episodes(Path(args.root)))
    counts = Counter()
    if args.group:
        start, cur = None, None
        for i, tasks in eps + [(-1, ["__end__"])]:
            t = tasks[0]
            counts[t] += 1 if t != "__end__" else 0
            if t != cur:
                if cur is not None:
                    print(f"  ep {start:>4}-{prev:<4} ({prev-start+1:>3} eps)  {cur}")
                start, cur = i, t
            prev = i
    else:
        for i, tasks in eps:
            counts[tasks[0]] += 1
            print(f"  ep {i:>4}  {tasks[0]}")

    print("\n=== per-task totals ===")
    for t, n in counts.most_common():
        print(f"  {n:>4}  {t}")
    print(f"\ntotal episodes: {len(eps)}")


if __name__ == "__main__":
    main()

# Inference Performance — vial-sort-pi0-lora

## Hardware

| | Workstation | Jetson Thor |
|---|---|---|
| GPU | NVIDIA RTX PRO 6000 Blackwell (97 GB) | — |
| Checkpoint | vial-sort-pi0-lora / step 30000 | same |
| dtype | bfloat16 | bfloat16 |
| LoRA rank | 16 | 16 |

## Workstation dry-run (2026-06-09)

`python ee/rollout_pi0_lora.py --dry-run` — synthetic images, no robot.

| Metric | Value |
|---|---|
| Inference latency mean | 4.6 ms |
| Inference latency p95 | 3.2 ms |
| Control loop frequency | 28.5 Hz (target: 30 Hz) |

> **Note on latency measurement**: π0 generates action chunks of 50 steps.
> `select_action` dequeues one step per tick; a full forward pass runs every
> 50 ticks (~1.7 s at 30 Hz).  The latency above is averaged across all ticks
> (dequeue-only ticks are ~0 ms; full-pass ticks dominate the mean).
> Use `--log-chunk-only` in a future profiling run to isolate full-pass cost.

## Jetson Thor (TODO — fill in after deploy)

| Metric | Value |
|---|---|
| Inference latency mean | — |
| Inference latency p95 | — |
| Control loop frequency | — |

## Smoke test — 10 fresh scenarios (TODO)

Run `python ee/rollout_pi0_lora.py --trials 10` and fill results into
`ee/smoke_test_log.csv`. Summary here after completion.

| Result | Count |
|---|---|
| OK | — |
| MissedGrip | — |
| DroppedVial | — |
| Collision | — |
| WrongRack | — |

# VLM → VLA pipeline (vial-sort "ChatGPT for the arm")

This is the language-conditioned control stack. A **VLM planner** (Claude) looks at the
starting scene and writes an ordered list of **atomic commands**; a warm **VLA server**
(π0 on Thor) executes them one at a time. The policy is a *command-executor*, not a
decision-maker — all "if the color is wrong, throw it in the bin" logic lives in the VLM.

```
 workstation (internet + ANTHROPIC_API_KEY)            Thor / Jetson (robot)
 ┌───────────────────────────────────────┐            ┌──────────────────────────┐
 │ orchestrator.py                        │  GET /observe   │ vla_server.py        │
 │   1. GET /observe ──────────────────────────────────────▶ (π0 loaded ONCE,     │
 │   2. planner.py  (Claude VLM) ─┐        │            │    cameras+motors up,    │
 │        scene+goal → plan        │       │            │    stays warm forever)   │
 │   3. for step in plan:          │       │ POST /execute   │                      │
 │        POST /execute {task} ────┴───────────────────────▶ runs 30 Hz control    │
 └───────────────────────────────────────┘            └──────────────────────────┘
```

## Why a persistent server (the whole point)

Loading the 4B π0 model + warming the cameras takes **~3 minutes**. We pay that **once**,
at server startup. Every planned step is then a cheap `/execute` HTTP call — **no
re-initialization per prompt**. Between steps the server calls `policy.reset()` so a new
command never runs on stale chunked actions from the previous one.

## Files

| File | Runs on | Purpose |
|---|---|---|
| `ee/vla_server.py` | **Thor** | Loads π0 once, serves `/health` `/observe` `/execute` |
| `ee/planner.py` | workstation | Qwen2.5-VL (Ollama, free/local) vision → structured atomic plan |
| `ee/orchestrator.py` | workstation | observe → plan → execute each step |

`vla_server.py` reuses the proven setup/inference path from `rollout_pi0_lora.py`; the
only change is the task string is per-request instead of the hardcoded global `TASK`.

## Run it (test on the 100-ep full-FT checkpoint = `base_v1`)

**1 — Thor: start the server (once, in tmux).** Defaults to the rsync target
`/home/robot/dev/lerebot/pretrained_model` (currently the fullft run):

```bash
# on Thor, from the lerobot repo root
tmux new-session -s vla
/home/robot/miniforge3/envs/lerobot/bin/python ee/vla_server.py \
    --checkpoint /home/robot/dev/lerebot/pretrained_model --port 8000
# wait for "VLA server ready ..." (~3 min), then Ctrl+B then D to detach
```

**2 — workstation: free local VLM planner (Qwen2.5-VL via Ollama — no API key).**

```bash
curl -fsSL https://ollama.com/install.sh | sh      # one time; starts the localhost:11434 service
ollama pull qwen2.5vl:7b                            # fast; or qwen2.5vl:32b for sharper scene reading

# dry: just see the VLM's plan, robot does not move
/home/sari/lerobot/.venv/bin/python ee/orchestrator.py \
    --server http://192.168.123.198:8000 \
    --goal "put the red vial from position 3 to position 3 in the right rack" --plan-only

# real: execute, confirming each step (Enter=go, s=skip, q=quit)
/home/sari/lerobot/.venv/bin/python ee/orchestrator.py \
    --server http://192.168.123.198:8000 \
    --goal "complete vial sort" --duration 30
```

The planner uses only the stdlib + Ollama's JSON-schema structured output (no pip installs).
To run the VLM on Thor instead of the workstation, start Ollama there and add
`--ollama-url http://192.168.123.198:11434`. Pick the model with `--model qwen2.5vl:32b`.

## ⚠️ What this test actually validates (be honest about it)

`base_v1` was trained on 100 episodes that **all carry the same label**, so it has learned
to **ignore the prompt** — it will do its trained behavior (pick → place toward right rack
pos 3) regardless of what `task` you send. So this run validates:

- ✅ the **plumbing**: warm server, no re-init per prompt, observe→plan→execute flow,
  per-step `policy.reset()`, latency/Hz on Thor, the Claude planner emitting valid plans.
- ❌ **NOT** prompt-following yet. The VLA can't follow `position N` until it's retrained
  on the varied-label dataset (the data-collection plan below).

So: use this to prove the pipeline works end-to-end on real hardware, then swap in the
language-grounded checkpoint when it's trained and the *same* orchestrator starts steering.

## Prompt grammar (keep tokens exact, vary the filler)

The VLA keys on the load-bearing tokens — the **rack side** and **position number** (or
"bin"). The VLM may vary surrounding phrasing; the trained dataset must use the same grammar:

- `place the vial in the right rack position N`   (N = 1..6, 6 = boundary)
- `place the vial in the left rack position N`    (reverse direction)
- `throw the vial in the bin`

## Atomic-skill model (recap of the plan)

- 3 atomic skills only: place→right N, place→left N, throw→bin. Everything else (full
  sort, reject-on-wrong-color) is the VLM chaining these.
- **"Complete vial sort"** needs **no extra policy training** — it's the VLM emitting the
  full ordered list of atomic placements; the orchestrator runs them in sequence.
- Single vial per scene for v1 (color in the prompt is redundant). Multi-vial + color
  disambiguation is v2.

## Data collection → retrain (next, after pipeline is proven)

To make the VLA actually follow `position N`, the dataset label must **vary with the
behavior** — destination is the only thing the cameras can't reveal, so destination must
vary. Plan:

1. **Relabel** existing 100 eps with their true source→dest-3 strings (free).
2. **Record** destination variation: L→R dest 1,2,4,5,**6** (dest 3 already covered),
   each from 2–3 sources; **R→L** extremes 1 & 6 + middle 3 & 4; **throw-to-bin** from
   varied starts. Write each episode's prompt with **varied sentence structure**.
3. **Robustness:** ~30% of new episodes recorded with **distractor/noisy backgrounds**
   (people/motion in the gripper-cam periphery) — fixes the "8 people" failure.
4. **Train (warm-start + replay):** start from `base_v1`, train on new + ~40% sampled old
   data, ~10–15k steps. NOT new-data-only (catastrophic forgetting). NOT from-scratch
   (wasteful). ~2–3h/run vs ~5h from scratch.
5. **Eval loop:** after each session, retrain → eval on a FIXED held-out trial set, log
   `(skill, cumulative eps, GPU-hours, success%, {missed pickup / missed drop / collision})`.
   Existing curve shows a hard threshold ~75 eps (15%→76%); new destinations should need
   fewer eps each thanks to the `base_v1` motor base — measure exactly how many.

## Open detail for next round

- **Step-done detection** in the orchestrator: currently fixed `--duration` per step.
  Options for v2: chunk-count cap, or a tiny success classifier so steps end when the
  place/throw actually completes instead of on a timer.
- Optional retract-to-home between steps (currently the arm stays where the policy left it).

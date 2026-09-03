# Robometer env setup on the WS (RTX PRO 6000, Blackwell) — working notes

The referee (Robometer-4B) runs in its **own** venv, isolated from lerobot's. Do NOT install it
into lerobot's env — it pins torch 2.8 + a big TF/unsloth/qwen stack.

## Install (one-time)
```bash
cd ee/robometer
UV_PYTHON=3.10 uv sync --extra robometer     # py3.10, torch 2.8.0+cu128, transformers 4.57 — creates ee/robometer/.venv
```
Verified working: python 3.10.20, torch 2.8.0+cu128, CUDA available, device Blackwell **sm_120**,
GPU matmul OK, transformers 4.57.6. (cu128 DOES support this Blackwell card — no torch bump needed
for inference.)

## GOTCHA — must fix after every `uv sync`: remove torchao
`uv sync` resolves **torchao==0.18.0**, which needs torch ≥ 2.11 (`from torch.nn.functional import
ScalingType`). On torch 2.8 it ImportErrors, and because it's *present*, `transformers` tries to
import it at module load → the whole robometer import chain dies (via sentence_transformers →
transformers.modeling_utils → quantizer_torchao → torchao). We don't quantize for inference, so:
```bash
cd ee/robometer && uv pip uninstall torchao      # transformers then skips it cleanly
```
Re-run this any time you `uv sync` again. (TF/cuDNN "already registered" spam and the unsloth
import-order warning are harmless.)

## Run inference (score a video)
Always run from the lerobot root so `ee/...` video paths resolve; use the robometer venv python:
```bash
export HF_HUB_ENABLE_HF_TRANSFER=1     # faster first-time ~8GB model pull
# single clip:
ee/robometer/.venv/bin/python ee/assess_robometer.py \
    --video ee/presentation/place_good.mp4 \
    --task "Move the vial to slot 1 of the right rack." --fps 3
# labeled manifest (video,task[,ground_truth]) — loads model ONCE, scores all, prints agreement %:
ee/robometer/.venv/bin/python ee/assess_robometer.py --manifest ee/robometer_pilot.csv --fps 3 \
    --out ee/robometer_scores.jsonl
# whole lerobot dataset (task read from meta):  --lerobot-root ./data/... --cam cam_side
```
Model `robometer/Robometer-4B` (Qwen3-VL-4B base, Apache-2.0, not gated) caches under
`~/.cache/huggingface/hub/`.

## Aggregate into the success map (no GPU/venv needed)
```bash
python ee/robometer_scoreboard.py --scores ee/robometer_scores.jsonl [--colors ee/clip_colors.csv]
```
Parses source/dest slots from the task string (position grammar); colour comes from an optional
`video,color` sidecar (the grammar never names colour). Writes `ee/robometer_scoreboard.json`.

## The dashboard (what the boss sees) — `ee/robometer_server.py`
Self-contained "robometer UI": loads the model once, serves its own web page, runs a command on the
robot, captures the side cam, scores it, and shows Robometer's progress/success **chart** + a big
SUCCESS/FAIL verdict + a **failure-rate** meter. Replaces the old confusing "loading bar". Does NOT touch
`ee/cv_run.py` or Thor's `vla_server.py` — it only talks to Thor over HTTP (same calls cv_run makes).
```bash
# WS (robometer venv): start the dashboard, pointed at the Thor VLA server
ee/robometer/.venv/bin/python ee/robometer_server.py --server http://192.168.123.198:8000 --port 8010
#   then open http://127.0.0.1:8010  → type a command, Execute; the arm homes, runs, and the page
#   shows the Robometer chart + ✓/✗ + success% + fail-rate. Needs Thor's vla_server up for /run + live cam.
```
Endpoints: `/` (page), `/run` (home+execute+capture+score), `/live` (side-cam+phase), `/stats`
(session+all-time fail rate), `/score` (score an arbitrary clip, multipart), `/stop`, `/health`.
Per-run rows are logged to `ee/robometer_runs.csv` → feed that to the scoreboard:
`python ee/robometer_scoreboard.py --results ee/robometer_runs.csv`.

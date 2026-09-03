# MODEL STRATEGY v5 (2026-07-18) — brief

## Verdict
Bottleneck is DATA + camera stability, NOT the model. Pick from models that run
REAL-TIME on Thor and are already in our LeRobot. World-Action Models (LingBot-VA,
Cosmos) are out — see below.

## Deployable candidates (all in-tree, A/B on the SAME v5 data)
| Model | why | knobs |
|---|---|---|
| **pi0.5** (primary) | proven on our Thor, best language of the tested set, 63ms class | frozen vision, train_expert_only |
| **SmolVLA** (NEW — try it) | purpose-built for small-data + Jetson; `policy.type=smolvla` | small 135M LM = fine for "position 3" |
| **GR00T N1.5 + LoRA** | fixes the overfit (1.5B params on 118 eps was the bug) | `lora_rank 32`, not full FT |
| pi0_fast / MolmoAct2 | secondary hedges | Molmo = depth-reasoning from RGB |

## OUT — World-Action Models (the "2x generalization" idea)
Source paper (arXiv 2603.22078) also reports: **LingBot-VA = 5,230 ms/inference (83x
slower than pi0.5)**, Cosmos = 390ms; **sim-only, never on a real robot**; not merged
into our LeRobot. 5.2s/step vs the ~10Hz the arm needs = unusable on Thor. Revisit only
if distilled 50x faster. (2nd RTX6000 does NOT fix this — the 5.2s is algorithmic: 70
diffusion steps through a 5B model. On RTX6000 ~2-3s, still ~40x too slow.)

## The 2nd RTX 6000 Blackwell → use for TRAINING, not WAM
Run the pi0.5 / SmolVLA / GR00T A/B **in parallel** (one card each) = 3x faster to a
decision. WAM only worth touching in SIM there, if curious. Robot stays on Thor.

## A3/B6 prompts → DECOUPLE ui-label from training-label
UI shows a button "A3"; the recorder SAVES the sentence "put the vial in position 3 of
the left rack" as the dataset task. Model never sees "A3" (keeps LLM semantics + slot
interpolation); operator never types the sentence. A lookup table joins them. Build this
into the recorder ONCE the v5 destination set is fixed.

## Data rules that actually decide success
- **Cross colors x destinations** (every color -> several destinations, vice versa) or
  the model fuses color+slot and ignores the prompt (our v1 shortcut).
- **Data math**: episodes must fill each (color, destination) cell. 4 colors x N dests;
  168 eps / (4xN). Keep N SMALL (3-4 dests) for v5 -> ~8+ eps/cell. Every extra
  destination multiplies the data you need.
- Vary source slot (anchors 1/3/4/6, hold out 2/5 to TEST interpolation); add distractors.
- **Depth**: recording now (cam_depth OK). Train the 2x2 (pi0.5 +/-depth), keep depth
  only on a measured first-try-grasp win.

## Order
1. LOCK cam_top + cam_side, strain-relief cables, capture fresh reference frames (biggest
   single fix — the pi0 "got lost" = camera drift).
2. Record v5: crossed colors x SMALL dest set, distractors, depth, A3-decoupled labels.
3. Train+A/B pi0.5 / SmolVLA / GR00T+LoRA on the 2 GPUs.
4. Shelve WAM/LingBot-VA.

Cross-refs: ee/DEPTH_PLAN.md, ee/ROADMAP_v5.md, ee/Papers_v5.md.

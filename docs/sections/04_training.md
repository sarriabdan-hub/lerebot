# 4. Policy Learning

The policy is **π0.5**, a ~3B-parameter vision–language–action (VLA) flow model in
the π0 family, **fine-tuned from the released base**.

## Frozen regime (only the action expert trains)
The **vision encoder and the vision–language backbone are frozen**; only the
**action expert** (the flow-matching head that produces motions) is updated.

**Why freeze:** with only 150 demonstrations, updating billions of vision
parameters overfits the recorded scenes and erodes the pretrained language
grounding that makes the model follow instructions. Freezing preserves those
priors and regularizes the small-data regime — the standard transfer-learning
outcome for VLAs. Training from scratch is infeasible at this scale. The choice is
also empirical: an **unfrozen** variant of the comparison model overfit and failed
to grasp, while the frozen policy trained cleanly.

## Configuration
| Setting | Value |
|---|---|
| Base model | π0.5 pretrained base |
| Trainable | action expert only (vision + VLM frozen) |
| Precision | bfloat16 |
| Learning rate | 1e-4 |
| Batch size | 16 |
| Steps | 30,000 (checkpoint every 2,000) |
| Action chunk | 50 |
| Action / state | 7-D end-effector (padded to 32) |
| Image augmentation | on |
| Cameras | RGB only (top, wrist, side) |

## Hardware
A single **NVIDIA RTX PRO 6000 Blackwell (96 GB)**. Because only the action expert
receives gradients, the frozen regime used **~19 GB** — the frozen majority of the
network runs a forward pass only, with no gradient/optimizer/activation memory.

## Comparisons
- **GR00T N1.5** (frozen visual backbone) fine-tuned on the same data — an
  architectural comparison.
- **ACT** (Action Chunking Transformer) and **π0** as baselines demonstrating the
  autonomous pipeline across policy classes (ACT executes the motion but is not
  language-conditioned; π0 and π0.5 follow the instruction).

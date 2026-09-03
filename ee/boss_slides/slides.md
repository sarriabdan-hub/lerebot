---
theme: seriph
background: https://cover.sli.dev
title: Vial-Sort Robot — Training Update
info: SO-101 arm + π0 VLA fine-tuning status
class: text-center
highlighter: shiki
transition: slide-left
mdc: true
---

# Vial-Sort Robot
## Training Update

SO-101 arm · π0 VLA · LeRobot framework

---
layout: two-cols
---

# What the System Does

**Hardware**
- SO-101 6-DOF robot arm
- 3 cameras: top, side, wrist
- Two test-tube racks (left / right)

**Task**
- Pick a red vial from one rack
- Place it in a specific slot on the other rack
- Controlled by a natural-language instruction

::right::

**The model: π0 (pi-zero)**
- 4B parameter Vision-Language-Action model
- Reads camera images + text instruction → outputs arm movements
- Fine-tuned on our own recorded demonstrations

> _"Place the red vial in position 3 of the left rack."_

---

# The Problem We Hit

### The model ignored the instruction

We recorded 120 demonstrations — but used **one template sentence** for all of them.

> _"Place the red vial in position N of the {rack} rack."_

Only a number and a word ever changed.

**Result:** the model learned that text is noise.  
It memorized the motion and ignored the prompt entirely.

<br>

> **Vision Shortcut** — when visual/action diversity >> text diversity,  
> VLAs stop reading the instruction and execute memorized motions.  
> _(arXiv 2602.17659, "When Vision Overrides Language")_

---

# The Fix: Instruction Paraphrasing

Instead of one template, every episode gets a **unique phrasing** of the same meaning.

| Episode | Instruction |
|---------|-------------|
| 18 | _"Place the red vial in position 1 of the left rack."_ |
| 19 | _"Put the red vial into slot 1 of the left rack."_ |
| 20 | _"Move the red tube at the first slot on the left rack."_ |
| 22 | _"Drop the red test tube in the 1st position of the rack on the left."_ |
| 25 | _"Place the red vial to slot 1 of the left-side rack."_ |

78 episodes → **78 unique phrasings**, all encoding the same (rack, slot).

The model is now **forced** to parse "left/right" and the slot number — it can't shortcut.

---

# Training Architecture: Knowledge Insulation

### Why we freeze the vision encoder

π0 has two parts:
- **Vision/Language backbone** (PaliGemma, 3.7B) — understands images and language
- **Action expert** (300M) — converts understanding → arm movements

**The problem:** fine-tuning corrupts the backbone's language understanding.

**The fix (Knowledge Insulation, π0.5 paper):**
- Freeze the vision encoder completely
- Only train the action expert
- The backbone keeps its language grounding; the expert learns the motions

> Proven approach — documented in the π0.5 Knowledge Insulation paper

---
layout: two-cols
---

# LoRA vs Full Fine-Tune

We tested both. **Full fine-tune wins.**

|  | LoRA (corrected) | Full Fine-Tune |
|--|--|--|
| Trainable params | ~14M | ~300M |
| Training time | ~6h | ~5h |
| GPU VRAM | ~52 GB | ~52–58 GB |
| Checkpoint size | 54 MB | 8.3 GB |
| Training loss | ~0.029 | ~0.030 |
| **Robot result** | **Misses grasp** | **Reliable grasp ✓** |

::right::

<br><br>

### Why LoRA loses despite equal loss

LoRA approximates the weight updates with a low-rank patch.  
Equal training loss did **not** predict equal robot performance.

The gap shows up at the hardest moment — **the grasp** — where full precision matters.

<br>

> Equal loss ≠ equal robot success.  
> We learned this the hard way.

---

# LoRA: The Right Tool Later

LoRA is **not abandoned** — it's the right tool for a different problem.

**Current use:** Full fine-tune as the strong base  
**Future use:** LoRA adapters on top for fast task switching

```
base_v1 (full-FT, 8.3 GB)
    ├── adapter_sort_vials.safetensors   (54 MB)
    ├── adapter_sort_caps.safetensors    (54 MB)
    └── adapter_handover.safetensors     (54 MB)
```

- Swap tasks in seconds by loading a different adapter
- No retraining the full model for each new task
- One strong base → many cheap specializations

---

# Current Status & Next Steps

### v3 training (running now)
- 78 episodes, paraphrased instructions, frozen vision + train_expert_only
- 40,000 steps, saving checkpoint every 2,000
- Evaluating on robot: pick the checkpoint with the best real-world success

### Why we're moving to π0.5 next

- π0.5 has a **better architecture for language grounding** (OpenVLA-OFT, arXiv 2410.24164)
- Designed specifically to avoid the vision-shortcut failure mode
- Same Knowledge Insulation approach, stronger backbone

> _"The best fine-tuned VLA is only as good as its language grounding."_

---
layout: center
class: text-center
---

# Summary

| What | Status |
|------|--------|
| Vision-shortcut failure diagnosed | ✅ |
| Paraphrased dataset (v3) built | ✅ |
| v3 training running | ✅ 40k steps |
| Robot eval (checkpoints 8k→40k) | 🔄 In progress |
| Upgrade to π0.5 | 📋 Next run |
| LoRA adapters for task switching | 📋 After base validated |

<br>

**Key papers:**  
[2602.17659](https://arxiv.org/html/2602.17659v1) · [2410.24164](https://arxiv.org/pdf/2410.24164) · [π0.5 KI](https://www.pi.website/download/pi05_KI.pdf) · [OpenVLA-OFT](https://openvla-oft.github.io/)

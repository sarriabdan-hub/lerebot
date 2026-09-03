# Depth + "Lingbot" — verdict and plan (2026-07-08, planning only)

Question asked: *we have the RealSense D435i — why not use its depth? Can we use the
"Lingbot" model in lerobot and feed it the depth camera?*

**Short answer: NO to Lingbot (it's the wrong model — a name collision), YES to depth —
but as a colorized 4th camera into pi0.5/GR00T, riding on the v5 pilot re-record.**

---

## 1. The name collision (this decides the Lingbot question)

There are TWO unrelated "LingBot" models, both from Ant Group's Robbyant unit:

| | LingBot-**VA** | LingBot-**VLA** |
|---|---|---|
| What | Autoregressive **video-action world model** on Wan2.2 (predicts future video latents + actions in one sequence) | Depth-aware **VLA** foundation model ([release, Jan 2026](https://www.marktechpost.com/2026/01/29/ant-group-releases-lingbot-vla-a-vision-language-action-foundation-model-for-real-world-robot-manipulation/)) |
| In lerobot? | Branch `origin/worktree-lingbot-va-port` only — **NOT merged into our main** (`docs/source/lingbot_va.mdx` on that branch) | **NO** — would be a full port project |
| Depth input? | **NONE.** `configuration_lingbot_va.py` inputs = `observation.images.*` RGB only | **Not live either**: depth-awareness is *distilled* — visual queries aligned to LingBot-Depth tokens via a projection layer + distillation loss at training time. The deployed model does not consume the D435i's depth stream |
| Runtime | ~5B DiT + ~20 GB frozen Wan-VAE/UMT5 stack; AR loop with ~20 video-denoise steps per chunk; `--eval.batch_size=1` only; checkpoints = LIBERO/RoboTwin | No SO-101/Thor recipe exists |
| Verdict for vial-sort | **Unusable**: no depth, no real-time on Thor, no SO-101 checkpoint | **Not worth it**: weeks of porting for a model that still wouldn't read our sensor's depth |

So "plug the depth camera into Lingbot" does not exist as an option, under either name.

## 2. The pragmatic depth path (what we WOULD do) — `cam_depth` as a 4th camera

pi0.5 and GR00T take **arbitrary named RGB camera streams**. The standard cheap way to give
an RGB VLA depth is to render the depth map as a 3-channel image and record it as one more
camera. Zero architecture change; A/B-able by simply dropping the key at train time.

Recipe (rides on the v5 pilot recording — depth CANNOT be retro-added to the 118 v4 eps):

1. **Capture**: D435i `use_depth=True` (already supported:
   `src/lerobot/cameras/realsense/camera_realsense.py` → `read_depth()`).
2. **Colorize** with a FIXED mapping (must be deterministic across episodes and at
   inference): clip to the work volume ~0.2–1.2 m → normalize → single fixed colormap.
   No auto-scaling per frame — that would break the pixel→depth correspondence.
3. **Record** as `observation.images.cam_depth` (just another mp4 stream) alongside
   cam_top / cam_side / cam_wrist during the v5 pilot sessions.
   - Bonus: this sidesteps the fact that our lerobot checkout (June-8) predates native
     depth-feature support in datasets — a colorized stream is plain video.
4. **Train the 2×2 from the same data** (Sari 2026-07-08: BOTH models get depth, not just
   pi0.5): pi0.5+D, GR00T+D, pi0.5 RGB-only baseline, GR00T RGB-only (optional). "RGB-only"
   = simply not passing the cam_depth key in the train config — no filtering, same dataset.
   Keep depth ONLY if first-try-grasp measurably improves on the robot vs the baseline.
5. **Inference**: vla_server adds the same colorize step on the live depth frame.

**Pre-flight check (before the pilot, on Thor)**: depth z16 640×480@30 adds ~18 MB/s on the
same D435i. We already had the USB-2 bandwidth-starvation saga (fixed with MJPG + RS-first
init; on 2026-07-01 the camera was on a 480M USB-2 port — see PLAN_FABLE §1 for the check
command). Run a 60 s bench with all 3 RGB streams + depth enabled and watch for frame
drops BEFORE committing the pilot to it.

### Thor patch — REQUIRED for cam_depth to actually record

`use_depth: true` alone records nothing extra: stock `SO101Follower.get_observation()`
only calls `cam.read_latest()` (color), and `_cameras_ft` only declares 3-channel color
features — the driver captures depth into `latest_depth_frame` but nothing surfaces it.
Verified in `src/lerobot/robots/so_follower/so_follower.py` (get_observation ~line 178,
`_cameras_ft` ~line 70) and `src/lerobot/cameras/realsense/camera_realsense.py`.

Apply to **Thor's** lerobot install (`so_follower.py`), same file both hunks:

```python
# 1) module level — the FIXED colorizer (same constants at train AND inference; never
#    per-frame autoscale). RealSense z16 depth is uint16 millimeters.
import cv2
import numpy as np

DEPTH_NEAR_M, DEPTH_FAR_M = 0.25, 1.20   # vial-sort work volume

def colorize_depth(depth_mm: np.ndarray) -> np.ndarray:
    d = depth_mm.astype(np.float32) / 1000.0
    u8 = ((np.clip(d, DEPTH_NEAR_M, DEPTH_FAR_M) - DEPTH_NEAR_M)
          / (DEPTH_FAR_M - DEPTH_NEAR_M) * 255.0).astype(np.uint8)
    u8[depth_mm == 0] = 0                 # invalid pixels -> black, not "near"
    return cv2.applyColorMap(u8, cv2.COLORMAP_JET)[..., ::-1]  # HxWx3 RGB

# 2) in _cameras_ft(): declare the extra feature so lerobot-record creates the stream
#    (add after the existing dict comprehension)
        ft = {cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
              for cam in self.cameras}
        for cam in self.cameras:
            if getattr(self.config.cameras[cam], "use_depth", False):
                ft["cam_depth"] = (self.config.cameras[cam].height,
                                   self.config.cameras[cam].width, 3)
        return ft

# 3) in get_observation(), after the camera loop:
        for cam_key, cam in self.cameras.items():
            if getattr(cam, "use_depth", False) and cam.latest_depth_frame is not None:
                obs_dict["cam_depth"] = colorize_depth(cam.latest_depth_frame)
```

Then verify with a 2-episode throwaway recording: the dataset must contain
`videos/observation.images.cam_depth/`. **Inference symmetry**: when a +depth checkpoint
is deployed, `ee/vla_server.py` must feed `observation.images.cam_depth` built with the
SAME `colorize_depth` (same NEAR/FAR constants) from the live `read_depth()` frame.
(Do NOT scp this patched file from WS→Thor blindly — Thor's copy has its own camera fixes;
apply the hunks by hand.)

## 3. Model comparison (planning only — no new training implied)

| Model | In our lerobot? | Depth? | Thor real-time? | Fit for vial-sort |
|---|---|---|---|---|
| **pi0.5** (primary) | yes | RGB only (+`cam_depth` trick) | yes — proven | Best language-following (VILAS 0.67); whole stack proven |
| **GR00T N1.5** (hedge #1, v4 A/B trained) | yes | RGB only (+`cam_depth` trick) | yes — official support | First-class SO-101/Thor; A/B eval pending servo |
| **LingBot-VA** | unmerged branch only | NO (RGB world model) | NO (~seconds/chunk, bs=1) | Unusable here |
| **LingBot-VLA** | NO | Distilled only — no live sensor input | unknown | Port ≫ payoff; skip |
| **MolmoAct2** | yes (in tree, `policy.type=molmoact2`) | Internal depth *reasoning* from RGB (predicts depth tokens; no sensor needed) | untested by us | Interesting zero-hardware spatial hedge if grasp-height errors persist |

## 4. Honest framing — depth is optionality, not the fix

Our documented failure modes and their fixes were: **language grounding** (→ paraphrased
instructions), **data density per destination** (→ v4/v5 densification), **camera-mount
drift** (→ mechanical fix + re-anchor). None of them were depth problems. Depth buys
grasp-height precision and lighting/texture robustness — worth *recording* during v5
(cheap optionality, can't be added later), worth *training* only as the one A/B run in
step 4 above. LingBot-* stays out of the plan entirely.

**Decision rule**: record `cam_depth` in the v5 pilot IF the Thor bandwidth bench passes;
train the +depth A/B once, keep only on a measurable first-try-grasp win.

---
Priority order unchanged: replace shoulder_lift servo → v5 pilot recording → pi0.5-v5
primary + GR00T A/B → (then, optionally) the depth A/B.
Cross-refs: `ee/PLAN_FABLE.md` §1 (depth), §7 (model choice) · `ee/Papers_v5.md` #16 (GR00T).

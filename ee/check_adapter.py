#!/usr/bin/env python3
"""Prove a LoRA adapter actually learned — the check that was missing last time.

LoRA initializes the B matrices to zero, so a freshly-initialized (or barely-trained)
adapter has lora_B norm ~ 0. If training moved the weights, the B norms are clearly > 0.
This is the cheap antidote to the "5 MB checkpoint, did anything happen?" uncertainty.

Usage:
    .venv/bin/python ee/check_adapter.py outputs/train/vial-sort-pi0-lora-fair/checkpoints/last/pretrained_model
    .venv/bin/python ee/check_adapter.py <dir>   # any dir containing adapter_model.safetensors
"""

import json
import sys
from pathlib import Path

from safetensors.torch import load_file


def main(model_dir: str) -> int:
    d = Path(model_dir)
    weights = d / "adapter_model.safetensors"
    cfg = d / "adapter_config.json"
    if not weights.exists():
        print(f"ERROR: {weights} not found")
        return 2

    if cfg.exists():
        c = json.loads(cfg.read_text())
        scaling = (c.get("lora_alpha") or 0) / (c.get("r") or 1)
        print(f"config: r={c.get('r')} lora_alpha={c.get('lora_alpha')} -> scaling={scaling:.2f}x")
        tm = c.get("target_modules")
        has_mlp = isinstance(tm, str) and ("mlp" in tm or "gate_proj" in tm)
        print(f"target_modules includes MLP: {has_mlp}")
        if scaling < 1.0:
            print("  WARNING: scaling < 1.0 — adapter is being dampened (the old footgun).")

    sd = load_file(str(weights))
    b_norms = {k: v.float().norm().item() for k, v in sd.items() if "lora_B" in k}
    a_norms = {k: v.float().norm().item() for k, v in sd.items() if "lora_A" in k}
    if not b_norms:
        print("ERROR: no lora_B tensors found — is this a LoRA adapter?")
        return 2

    nonzero = sum(n > 1e-6 for n in b_norms.values())
    total = len(b_norms)
    mean_b = sum(b_norms.values()) / total
    print(f"\nlora_B tensors with norm > 1e-6: {nonzero}/{total}")
    print(f"mean lora_B norm: {mean_b:.4g}   (0 = untrained; clearly >0 = learned)")
    print(f"mean lora_A norm: {sum(a_norms.values()) / max(len(a_norms), 1):.4g}")

    if nonzero == 0:
        print("\nVERDICT: adapter did NOT learn (all B≈0). Do not deploy this checkpoint.")
        return 1
    if nonzero < total * 0.5:
        print(f"\nVERDICT: only {nonzero}/{total} layers moved — partial learning, investigate.")
        return 1
    print("\nVERDICT: adapter learned across layers. Good to evaluate on the robot.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))

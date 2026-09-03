"""
Client for sim_server.py — used by teleop_record.py and eval_pi05.py, which run
in the NORMAL lerobot env (Python 3.12), not the isaac-venv.
"""

from __future__ import annotations

import base64

import cv2
import numpy as np
import requests


class SimClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 6060, timeout: float = 5.0):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout
        self.session = requests.Session()

    def ping(self) -> dict:
        return self.session.get(f"{self.base}/ping", timeout=self.timeout).json()

    def reset(self, episode: int, v4: bool = False) -> dict:
        r = self.session.post(f"{self.base}/reset", json={"episode": episode, "v4": v4},
                              timeout=30.0)
        r.raise_for_status()
        return r.json()

    def home(self) -> None:
        self.session.post(f"{self.base}/home", json={}, timeout=self.timeout)

    def act(self, action: dict[str, float]) -> None:
        """action: {'shoulder_pan.pos': deg, ..., 'gripper.pos': 0..100}"""
        self.session.post(f"{self.base}/act", json={"action": action}, timeout=self.timeout)

    def obs(self) -> tuple[dict[str, float], dict[str, np.ndarray]]:
        """Returns (joint_state_deg, {'cam_top': HxWx3 uint8 RGB, ...})."""
        r = self.session.get(f"{self.base}/obs", timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        imgs = {}
        for name, b64 in data["images"].items():
            buf = np.frombuffer(base64.b64decode(b64), dtype=np.uint8)
            imgs[name] = cv2.cvtColor(cv2.imdecode(buf, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        return data["state"], imgs

# Bin-release patch for `vla_server.py` (pi0.5 deployment, Thor)

**Problem.** On a bin/discard command, pi0.5 carries the vial over the bin and stops
(the `/execute` inference ends) but never opens the gripper, so the vial isn't dropped.

**Fix (no retrain).** After a bin/discard `/execute` finishes, open the gripper **in
place** (hold every other joint, move only the gripper) to drop the vial. Auto-triggered
when the task mentions bin/trash; can also be forced with `{"release": true}` on any
`/execute`.

**Gripper values (measured from the v5 data):** closed-on-vial ≈ 0–5, fully open ≈ 70
(arm reached ~72 in demos). So open target = **70**.

Apply BY HAND to Thor's `/home/robot/dev/lerebot/ee/vla_server.py` (don't scp — it has
your camera/bus patches). Two edits.

---

## EDIT 1 — add the release function
Paste this block anywhere at module level **just above `def go_home(`**
(it reuses `STATE`, `FPS`, `STOP_EVENT`, `_set_live`, `precise_sleep`, exactly like
`go_home`):

```python
# ── Bin-release workaround (pi0.5 doesn't open the gripper over the bin) ─────────
GRIPPER_OPEN = 70.0      # fully-open target; demos reached ~72. Lower if it over-travels.
RELEASE_S    = 0.8       # seconds to open

def release_gripper(open_val: float = GRIPPER_OPEN, duration: float = RELEASE_S) -> dict:
    """Open the gripper IN PLACE to drop the held object, holding every other joint at its
    current measured position. Completes a bin move the policy ends by hovering."""
    follower = STATE["follower"]
    STATE["policy"].reset()                      # drop any queued VLA actions
    obs = follower.get_observation()
    cur = {k: float(v) for k, v in obs.items() if k.endswith(".pos")}
    if "gripper.pos" not in cur:
        return {"error": "no gripper joint", "robot_keys": sorted(cur)}
    g0 = cur["gripper.pos"]
    _set_live(busy=True, phase="home", task=None, t_start=time.time(), duration=duration)
    STOP_EVENT.clear()
    n = max(int(duration * FPS), 1)
    try:
        for i in range(1, n + 1):
            if STOP_EVENT.is_set():
                break
            a = i / n
            step = dict(cur)                     # hold EVERY joint where it is
            step["gripper.pos"] = g0 + (open_val - g0) * a
            follower.send_action(step)
            precise_sleep(1.0 / FPS)
        return {"released": True, "gripper_from": round(g0, 1), "gripper_to": round(open_val, 1)}
    finally:
        _set_live(busy=False, phase="idle")


def _is_discard(task: str) -> bool:
    t = (task or "").lower()
    return any(w in t for w in ("bin", "trash", "waste", "rubbish", "discard"))
```

---

## EDIT 2 — call it after `/execute` finishes
In `do_POST`, find the execute block:

```python
            with ROBOT_LOCK:  # serialize all robot access
                stats = run_command(task, duration)
```

and change it to (add the 5 new lines, same indentation, INSIDE the `with ROBOT_LOCK`):

```python
            with ROBOT_LOCK:  # serialize all robot access
                stats = run_command(task, duration)
                # complete a bin/discard drop: open the gripper in place
                want_release = req.get("release")
                if want_release is None:
                    want_release = _is_discard(task)
                if want_release:
                    stats = {**stats, "release": release_gripper()}
```

*(`ROBOT_LOCK` is reentrant, so calling `release_gripper` — which uses `send_action` —
inside the `with ROBOT_LOCK` block is safe, exactly like `go_home` under `/home`.)*

---

## EDIT 3 (optional) — a `/release` endpoint for a UI "Open gripper" button
So a UI button can open the gripper on demand (drop whatever it's holding), add a route.

1. In `do_POST`, add `"/release"` to the allowed-paths check:
```python
        if self.path not in ("/execute", "/home", "/tune", "/release"):
```
2. Add this branch just after the `/home` block:
```python
        if self.path == "/release":
            try:
                with ROBOT_LOCK:
                    rel = release_gripper()
                self._send(200, rel)
            except Exception as e:  # noqa: BLE001
                _set_live(busy=False, phase="error")
                self._send(500, {"error": repr(e)})
            return
```
Now `POST /release` opens the gripper in place. Wire a UI button to it — see
`ee/ui_notes.md`.

---

## Test & tune
1. Restart `vla_server.py`, Home, then run a **bin** command, e.g.
   `Move the vial from position 3 of the right rack to the bin.`
   The arm carries the vial over the bin, and when the move ends it **opens and drops**.
2. It only triggers on bin/trash tasks — **rack-to-rack sorts are unaffected**
   (`_is_discard` is False for them).
3. Force it on any command with `{"task": "...", "duration": 30, "release": true}`, or
   disable with `"release": false`.
4. **Tuning `GRIPPER_OPEN`:** if the vial doesn't fully drop, raise toward `72`; if the
   gripper over-travels or errors, lower it. `STOP` still halts everything mid-release.

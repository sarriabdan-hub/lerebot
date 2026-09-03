# UI notes — vial-sort control panel (pi0.5 v5)

Two things to build into the UI: an **Open-gripper button**, and the **command
constraints** (which positions the model actually knows).

---

## 1. "Open gripper" button
A manual button that opens the gripper on demand — completes a bin drop, or releases
after any hover. It calls the new `POST /release` endpoint (add it via
`ee/bin_release_patch.md` EDIT 3).

Built-in dashboard (in `vla_server.py`'s HTML) or `cv_run.py` — add near Home/Execute:
```html
<button onclick="release()">Open gripper</button>
<script>
async function release(){
  try { const r = await fetch('/release', {method:'POST'}); console.log(await r.json()); }
  catch(e){ console.log('release failed: '+e); }
}
</script>
```
(Bin commands already auto-release; this button is for manual completion / testing.)

---

## 2. Command constraints — which positions to expose
The v5 model was trained on a **subset** of slots. Only offer trained combos; the rest
are out-of-distribution and unreliable.

| Field | Offer (TRAINED) | Do NOT offer (held out / untrained) |
|---|---|---|
| **Source slot** | 1, 3, 4, 6 | 2, 5 |
| **Destination slot** | 1, 3, 6, **bin** | 2, 4, 5 |

**Reliability within the trained set:**
- **Slot 3 (central):** most reliable grasp + placement.
- **Slots 1 & 6 (edges):** trained, but at the arm's reach extremes → grasp is harder,
  lower success. Mark them "edge (less reliable)" in the UI.
- **Bin:** navigation works; the drop needs the gripper release (auto on bin, or the
  Open-gripper button above).

**Suggested UI:** a **Source** picker `{1, 3, 4, 6}` and a **Destination** picker
`{1, 3, 6, bin}`, with 1 & 6 flagged as edge. Slots 2/4/5 hidden, or shown but labeled
"experimental (untrained)".

---

## 3. Prompt format (unchanged)
Position grammar, color never named (the executor is spatial):
> `Move the vial from position 3 of the left rack to slot 6 of the right rack.`
> `Move the vial from position 4 of the right rack to the bin.`

Left/right and slot numbers are read from the **side camera** (left rack = image-left, by
the bin; slots 1→6 left-to-right).

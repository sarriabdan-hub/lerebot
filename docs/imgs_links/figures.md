# Figure manifest — what to capture and where it comes from

Put each finished image in `docs/imgs/` using the **filename in bold** (that's the
name `main.tex` expects). Sources on the workstation (WS `192.168.123.170`) and
Thor (`192.168.123.198`) are given; commands to extract a frame are included.

---

### 1. **system_diagram.png** — Figure 1 (overview)
A simple block diagram: `planner → position command → π0.5 executor → SO-101 arm`.
- **Source:** draw it (draw.io / Excalidraw / PowerPoint). No existing asset.

### 2. **setup_side.png** — Figure 2 (the rig)
The side-camera view of the whole rig: arm, the two diagonal racks, bin on the left.
- **Source:** `ee/align/new_rack_side.png` on the WS.
- Copy: `cp /home/sari/lerobot/ee/align/new_rack_side.png docs/imgs/setup_side.png`

### 3. **cameras.png** — Figure 3 (three feeds)
The three live feeds side by side (top / wrist / side).
- **Source:** crop the camera row from the dashboard screenshot
  `~/Downloads/Screenshot from 2026-08-12 17-44-51.png`, or screenshot the
  dashboard camera row fresh.

### 4. **teleop_dataset.png** — Figure 4 (a demonstration)
One recorded episode with all camera views + trajectory + prompt on one timeline.
- **Source:** on Thor run the dataset visualizer and screenshot a clean episode:
  ```
  lerobot-dataset-viz --repo-id sari-abdan/vial-sort-v5-pilot \
    --root /home/robot/my_local_data_v5 --episode-index 0 \
    --mode distant --web-port 9090      # open http://localhost:9090
  ```

### 5. **depth_triptych.png** — Figure 5 (depth evaluation)
RGB (left) | Depth Anything V2 (center) | Intel RealSense (right).
- **Source:** frame from `~/Downloads/triptych_rgb_da_intel_v5.mp4`.
  ```
  ffmpeg -ss 8 -i ~/Downloads/triptych_rgb_da_intel_v5.mp4 -frames:v 1 docs/imgs/depth_triptych.png
  ```

### 6. **dashboard.png** — Figure 6 (control panel)
The browser control panel served on the Jetson (feeds + command field + Home/Execute).
- **Source:** `~/Downloads/Screenshot from 2026-08-12 17-44-51.png` (already have it).
  ```
  cp "$HOME/Downloads/Screenshot from 2026-08-12 17-44-51.png" docs/imgs/dashboard.png
  ```

### 7. **rack_sort_sequence.png** — Figure 7 (a successful sort)
A few frames of a complete rack-to-rack sort: approach → grasp → transport → release.
- **Source:** the working-run clip `~/Downloads/exec_playable/place_good_v3.mp4`.
  Extract 3–4 frames and tile them (e.g. in any image editor):
  ```
  for t in 1 4 7 10; do ffmpeg -ss $t -i ~/Downloads/exec_playable/place_good_v3.mp4 \
      -frames:v 1 docs/imgs/racksort_$t.png; done
  ```
  Then combine `racksort_*.png` into a single `rack_sort_sequence.png`.

### 8. **bin_hover.png** — Figure 8 (the bin limitation)
The arm holding the vial above the bin without releasing.
- **Source:** capture a frame during a bin command (record with `--record-video`
  and pull a frame), or screenshot the side feed mid-hover.

### 9. **architecture_diagram.png** — system architecture
Client–server architecture: control panel (WS) ↔ inference server (Thor) ↔
policy / cameras / arm.
- **Source:** open `docs/diagrams/system_architecture.drawio` in
  draw.io / diagrams.net → **File → Export as → PNG** →
  `docs/imgs/architecture_diagram.png`.

### 10. **usecase_diagram.png** — use cases
Operator use cases: monitor feeds, analyze scene, enter command, home, execute,
emergency stop.
- **Source:** open `docs/diagrams/usecase.drawio` in draw.io / diagrams.net →
  **File → Export as → PNG** → `docs/imgs/usecase_diagram.png`.

### 11. **scene_example.drawio.png** — example scene (Dataset / Constraints)
A labeled example scene: two 6-slot racks + bin, showing the starred target, spaced
distractors, the empty destination with both neighbors free, and the held-out slots
{2,4,5} shaded.
- **Source:** open `docs/diagrams/scene_example.drawio` in draw.io / diagrams.net →
  **File → Export as → PNG** → `imgs/scene_example.drawio.png`.

---

**Tip:** `main.tex` compiles with grey placeholder boxes until you add images. For
each figure, drop the PNG in `docs/imgs/`, uncomment its `\includegraphics` line,
and remove the matching `\figplaceholder{...}` line.

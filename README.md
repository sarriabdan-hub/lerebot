# SO-101 LeRobot Setup on Ubuntu 24.04

## What this repo is for

This repository contains everything you need to set up and teleoperate SO-101 leader/follower robot arms using LeRobot on Ubuntu 24.04.

It includes:
- A LeRobot setup for SO-101 leader/follower arms
- Saved calibration files in `calibration/robots/so_follower` and `calibration/teleoperators/so_leader`
- A local copy of the LeRobot source inside the `lerobot/` folder

## Requirements

- Ubuntu 24.04
- Git
- wget
- Miniforge / Conda
- Two SO-101 arms (one leader, one follower)
- Both USB cables
- Both power supplies

## 1. Install basic Ubuntu packages

```bash
sudo apt update
sudo apt install -y git wget build-essential
```

## 2. Install Miniforge

```bash
wget "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash Miniforge3-$(uname)-$(uname -m).sh
source ~/.bashrc
```

## 3. Clone this repository

```bash
git clone https://github.com/sarriabdan-hub/lerebot.git
cd lerebot
```

## 4. Create a clean Conda environment

```bash
conda create -y -n lerobot python=3.12
conda activate lerobot
```

> Do not rely on `environment.yml` if it causes package conflicts. Use the manual install steps below instead.

## 5. Install LeRobot from the local source folder

```bash
cd ~/lerebot/lerobot
pip install -e ".[feetech]"
cd ..
```

**Fallback** (if the above fails):

```bash
conda activate lerobot
conda install -y pip
cd ~/lerebot/lerobot
python -m pip install -e ".[feetech]"
cd ..
```

## 6. Restore calibration files

```bash
mkdir -p ~/.cache/huggingface/lerobot/calibration/robots
mkdir -p ~/.cache/huggingface/lerobot/calibration/teleoperators

cp -r calibration/robots/so_follower ~/.cache/huggingface/lerobot/calibration/robots/
cp -r calibration/teleoperators/so_leader ~/.cache/huggingface/lerobot/calibration/teleoperators/
```

## 7. Connect the arms

Plug in both USB cables and both power supplies for the leader and follower arms.

Then verify the ports are detected:

```bash
ls /dev/ttyACM*
sudo chmod 666 /dev/ttyACM*
```

## 8. Start teleoperation

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACM1 \
  --robot.id=so_follower \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyACM0 \
  --teleop.id=so_leader
```

> **Note:** The port assignments may be reversed. If the command does not work, swap `/dev/ttyACM0` and `/dev/ttyACM1` in the command above.

## 9. Calibration note

If the saved calibration does not work correctly, you can recalibrate manually.

Before starting calibration:
- Put all servo motors near the middle of their range of motion.
- Calibrate the **leader** arm first.
- Move every motor through its full range of motion during calibration.
- Then repeat the process for the **follower** arm.

## Troubleshooting

| Problem | Solution |
|---|---|
| `conda` command not found | Run `source ~/.bashrc` or reopen the terminal |
| Permission denied on `/dev/ttyACM*` | Run `sudo chmod 666 /dev/ttyACM*` |
| Wrong port / arm not responding | Swap `ttyACM0` and `ttyACM1` in the teleoperate command |
| Package conflicts during install | Delete the conda environment (`conda env remove -n lerobot`) and recreate it |

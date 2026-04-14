# SO-Arm101 setup

## On a new Ubuntu machine

git clone <YOUR-GITHUB-REPO-URL>
cd soarm101-repo
conda env create -f environment.yml
conda activate lerobot
cd lerobot
pip install -e ".[feetech]"

mkdir -p ~/.cache/huggingface/lerobot/calibration/robots
mkdir -p ~/.cache/huggingface/lerobot/calibration/teleoperators

cp -r ../calibration/robots/so_follower ~/.cache/huggingface/lerobot/calibration/robots/
cp -r ../calibration/teleoperators/so_leader ~/.cache/huggingface/lerobot/calibration/teleoperators/

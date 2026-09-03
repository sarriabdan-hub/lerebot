# Integrating Robometer into an Existing π0.5 Policy

## Goal

Integrate **Robometer** (paper: arXiv `2603.02115`) with an already working **π0.5 / OpenPI policy**.

The objective is **not** to replace π0.5 or merge Robometer weights into π0.5.

Instead:

- π0.5 remains the robot action policy.
- Robometer acts as an external **reward / progress / success model**.
- First use Robometer for runtime evaluation and rollout scoring.
- Later, if desired, use Robometer as the reward model for **RL steering in π0.5 noise space**.

The implementation should be done incrementally and should preserve the current π0.5 behavior as much as possible.

---

# High-Level Architecture

```text
Task instruction
      │
      ▼
Camera + robot state
      │
      ▼
     π0.5
      │
      │ action chunk
      ▼
    Robot
      │
      │ resulting observations / camera frames
      ▼
  Robometer
 ┌───────────────┐
 │ progress 0..1 │
 │ success 0..1  │
 │ preference    │
 └───────────────┘
      │
      ▼
reward / feedback / rollout score
```

Important:

**Robometer should initially run as a separate model/process. Do not insert it inside the π0.5 transformer.**

---

# Existing π0.5 Assumptions

Assume that the project already has:

- a working π0.5 checkpoint,
- a working robot inference loop,
- camera observations,
- robot state observations,
- action chunk execution,
- OpenPI or code derived from Physical Intelligence's OpenPI implementation.

Locate the code where inference currently looks conceptually like:

```python
observation = get_robot_observation()
actions = policy.infer(observation)
execute(actions)
```

or:

```python
actions = model.sample_actions(...)
```

Do not rewrite the whole policy pipeline.

---

# Phase 1 — Add Robometer as an External Runtime Critic

This is the first implementation target.

## Desired behavior

After π0.5 executes actions, collect camera frames and periodically send them to Robometer together with the current task instruction.

Robometer should return:

- progress estimate,
- success probability.

Example:

```text
Instruction:
"Pick up the red cube"

π0.5 executes actions

Camera frames:
frame_1
frame_2
frame_3
...

Robometer:

progress = 0.72
success_probability = 0.18
```

Later:

```text
progress = 0.98
success_probability = 0.93
```

Then the system can determine that the task is likely completed.

---

# Recommended Separation

Run π0.5 and Robometer as **separate processes**.

Suggested architecture:

```text
PROCESS 1
π0.5 robot control

PROCESS 2
Robometer inference server
```

Communication can happen over HTTP.

This is preferable because Robometer and OpenPI may have different:

- Python dependencies,
- PyTorch / JAX dependencies,
- CUDA dependencies,
- transformers versions.

Do not combine both environments unless necessary.

---

# Suggested Project Structure

Add something similar to:

```text
project/
│
├── existing_pi05_code/
│
├── robometer_client.py
├── robometer_buffer.py
├── reward_config.py
└── logs/
    └── robometer/
```

Do not move existing π0.5 files unless required.

---

# `robometer_client.py`

Create a small client whose only responsibility is communicating with the Robometer inference server.

Desired interface:

```python
class RobometerClient:
    def __init__(self, server_url: str):
        ...

    def evaluate(
        self,
        frames,
        task: str,
    ):
        """
        Returns:
            progress: np.ndarray
            success_probs: np.ndarray
        """
```

Expected use:

```python
robometer = RobometerClient(
    server_url="http://localhost:8000"
)

progress, success = robometer.evaluate(
    frames=frames,
    task="Pick up the red cube",
)
```

Keep Robometer-related HTTP logic outside of the robot-control code.

---

# Frame Buffer

Create a small frame buffer.

Example:

```python
class RobometerFrameBuffer:
    def __init__(self, max_frames=64):
        self.frames = []
        self.max_frames = max_frames

    def add(self, frame):
        self.frames.append(frame)

        if len(self.frames) > self.max_frames:
            self.frames = self.frames[-self.max_frames:]

    def reset(self):
        self.frames = []

    def get(self):
        return self.frames
```

Robometer does not need to be called at every control timestep.

π0.5 may run at a relatively high control rate, whereas Robometer is a large video-language reward model.

Therefore:

```text
π0.5 control
π0.5 control
π0.5 control
π0.5 control
↓
Robometer evaluation

π0.5 control
π0.5 control
...
```

A simple starting point is to query Robometer:

- once after each executed action chunk, or
- every N action chunks.

Make this configurable.

---

# Minimal Integration into Current π0.5 Loop

Transform this:

```python
while not done:

    observation = get_robot_observation()

    actions = pi05.infer(observation)

    execute(actions)
```

into something conceptually like:

```python
frames = RobometerFrameBuffer()

while not done:

    observation = get_robot_observation()

    actions = pi05.infer(observation)

    execute(actions)

    frame = get_latest_camera_frame()
    frames.add(frame)

    if should_query_robometer():

        progress, success = robometer.evaluate(
            frames=frames.get(),
            task=current_instruction,
        )

        latest_progress = float(progress[-1])
        latest_success = float(success[-1])

        print(
            f"Robometer: progress={latest_progress:.3f}, "
            f"success={latest_success:.3f}"
        )
```

Initially:

**Do not allow Robometer to alter π0.5 actions.**

Only log its outputs.

---

# Logging

Every Robometer query should be logged.

Suggested fields:

```json
{
    "timestamp": "...",
    "task": "pick up the red cube",
    "episode_id": 17,
    "action_chunk_index": 6,
    "progress": 0.74,
    "success_probability": 0.11
}
```

At the end of the episode also record:

```json
{
    "episode_id": 17,
    "final_progress": 0.98,
    "final_success_probability": 0.93,
    "environment_success": true
}
```

This is important because Robometer must first be validated on the robot/domain before it is trusted as a reward model.

---

# Phase 1 Validation

Before doing any RL, test Robometer on known good and bad π0.5 executions.

At minimum collect:

## Successful rollout

Example:

```text
robot approaches cube
robot grasps cube
robot lifts cube
robot places cube correctly
```

Expected:

```text
progress gradually increases
success becomes high near completion
```

## Failed grasp

Example:

```text
robot approaches cube
gripper closes beside cube
robot moves away without object
```

Expected:

```text
progress may initially rise
success should remain low
```

## Wrong-object rollout

Example:

```text
instruction = "pick up red cube"

robot picks up blue cube
```

Expected:

```text
success should remain low
```

If Robometer cannot distinguish these reliably, do not proceed to RL yet.

---

# Success Threshold

Do not hard-code task completion immediately.

Start by logging values.

After observing the score distribution, optionally add:

```python
SUCCESS_THRESHOLD = 0.85
```

Then:

```python
if latest_success >= SUCCESS_THRESHOLD:
    task_completed = True
```

The threshold must be configurable.

---

# Long-Horizon π0.5 Tasks

If the current π0.5 setup produces high-level subtasks, Robometer should preferably evaluate the **current subtask**, not only the full long-horizon instruction.

Example:

```text
Main task:
"Clean the table"

π0.5 subtask:
"Pick up the cup"
```

Robometer receives:

```text
"Pick up the cup"
```

When π0.5 changes the subtask:

```text
"Put the cup in the sink"
```

reset the frame buffer:

```python
frame_buffer.reset()
```

and begin evaluating:

```text
"Put the cup in the sink"
```

This makes progress/success estimates easier to interpret.

---

# Phase 2 — Score π0.5 Rollouts

After runtime Robometer evaluation works reliably, use it to score stored π0.5 trajectories.

For every episode store:

```text
episode/
├── frames/
├── observations
├── actions
├── task.txt
└── robometer_score.json
```

Example score:

```json
{
    "final_progress": 0.91,
    "final_success": 0.88,
    "max_success": 0.91
}
```

Then classify trajectories.

For example:

```python
if final_success > 0.85:
    category = "successful"

elif final_success < 0.20:
    category = "failed"

else:
    category = "suboptimal"
```

Do not assume these thresholds are universally correct.

Make them configurable.

---

# Dataset Filtering / Fine-Tuning Option

A safe intermediate improvement before RL is:

```text
existing expert demonstrations
        +
high-scoring π0.5 rollouts
        ↓
π0.5 fine-tuning
```

Robometer can therefore serve as an automatic rollout-quality filter.

Pipeline:

```text
π0.5
  │
  ▼
many robot rollouts
  │
  ▼
Robometer scoring
  │
  ├── good
  ├── mediocre
  └── failed
  │
  ▼
select useful trajectories
  │
  ▼
π0.5 fine-tuning
```

Keep this as a separate training experiment.

Do not overwrite the original π0.5 checkpoint.

---

# Phase 3 — Robometer Reward + π0.5 Noise-Space RL Steering

This is the advanced integration.

Do this only after Phase 1 works.

The idea is:

- freeze π0.5,
- freeze Robometer,
- train a small steering policy,
- steering policy predicts the initial noise supplied to π0.5,
- Robometer provides the reward.

Architecture:

```text
observation
    │
    ▼
steering actor
    │
    │ noise tensor
    ▼
π0.5 flow matching
    │
    ▼
action chunk
    │
    ▼
robot
    │
    ▼
camera frames
    │
    ▼
Robometer
    │
    ▼
reward
    │
    └────────────► train steering actor
```

---

# Why Noise-Space Steering is Possible

OpenPI π0/π0.5 action sampling conceptually has:

```python
def sample_actions(
    ...,
    noise=None,
):
```

When `noise is None`, the policy samples random Gaussian noise.

Conceptually:

```python
noise = random.normal(
    shape=(
        batch_size,
        action_horizon,
        action_dim,
    )
)
```

That noise is transformed by the flow-matching action model into a final action trajectory.

Therefore instead of random noise:

```python
actions = pi05.sample_actions(
    observation,
    noise=random_noise,
)
```

use learned noise:

```python
noise = steering_actor(observation)

actions = pi05.sample_actions(
    observation,
    noise=noise,
)
```

Important:

Do not hard-code the noise tensor dimensions.

Use the current π0.5 model's:

```python
action_horizon
action_dim
```

Expected actor output:

```text
[B, action_horizon, action_dim]
```

---

# Freeze π0.5

For the RL steering experiment:

```text
π0.5 parameters: frozen
Robometer parameters: frozen
Steering actor: trainable
RL critic: trainable
```

Do not initially fine-tune all π0.5 parameters with RL.

---

# Conceptual RL Loop

Example only:

```python
observation = env.get_observation()

features = get_policy_or_observation_features(observation)

noise = steering_actor(features)

actions = pi05.sample_actions(
    observation=observation,
    noise=noise,
)

env.execute(actions)

new_frames = env.get_recent_frames()

progress, success = robometer.evaluate(
    frames=new_frames,
    task=current_instruction,
)

reward = build_reward(
    progress=progress,
    success=success,
)

next_observation = env.get_observation()

replay_buffer.add(
    observation=observation,
    steering_action=noise,
    reward=reward,
    next_observation=next_observation,
)

update_actor_and_critic()
```

---

# Reward Design

Do not start with a complicated reward.

Possible first version:

```python
reward = latest_progress
```

Better:

```python
reward = (
    progress_delta
    + success_bonus
)
```

Example:

```python
progress_delta = (
    latest_progress - previous_progress
)

success_bonus = (
    5.0 if latest_success > SUCCESS_THRESHOLD else 0.0
)

reward = progress_delta + success_bonus
```

Potential penalties can later include:

- collision,
- dropped object,
- timeout,
- unsafe joint configuration,
- action magnitude,
- task regression.

Keep Robometer reward separate from hard safety constraints.

---

# Safety Constraints

Robometer is a learned reward model.

It must **not** replace deterministic robot safety logic.

Maintain hard constraints for:

- joint limits,
- collision detection,
- workspace bounds,
- emergency stop,
- force / torque limits,
- velocity limits.

Conceptually:

```text
π0.5 / RL action
      │
      ▼
hard safety filter
      │
      ▼
robot
```

Robometer only evaluates task progress/success.

---

# Robometer Failure Handling

The robot-control loop must continue safely if Robometer becomes unavailable.

Example:

```python
try:
    progress, success = robometer.evaluate(...)
except Exception as exc:
    logger.warning(
        "Robometer unavailable: %s",
        exc,
    )

    progress = None
    success = None
```

Do not crash robot execution because the reward server failed.

---

# Configuration

Create configuration similar to:

```yaml
robometer:
  enabled: true
  server_url: "http://localhost:8000"

  query_every_n_chunks: 1

  max_buffer_frames: 64

  success_threshold: 0.85

  terminate_on_success: false

  log_scores: true
```

Initially:

```yaml
terminate_on_success: false
```

Only switch it to true after validating Robometer.

---

# Important Implementation Rules

## Rule 1

Do not modify the internal π0.5 architecture for Phase 1.

## Rule 2

Do not retrain Robometer initially.

Use pretrained Robometer first.

## Rule 3

Keep Robometer communication behind a clean client interface.

## Rule 4

Do not call Robometer for every low-level motor timestep.

## Rule 5

Log everything before using Robometer for automatic termination.

## Rule 6

Validate Robometer on both success and failure trajectories.

## Rule 7

For RL steering, freeze π0.5 first.

## Rule 8

Do not hard-code action dimensions or horizon.

Read them from the current π0.5 configuration.

---

# Implementation Order

Please implement in this order.

## Step 1

Inspect the repository and identify:

- π0.5 checkpoint loading,
- policy inference entry point,
- robot control loop,
- image/camera observation source,
- task-language source,
- action chunk length,
- action dimension,
- location of `sample_actions()` if OpenPI is used.

Do not change code yet.

Report the relevant files.

---

## Step 2

Add:

```text
robometer_client.py
robometer_buffer.py
reward_config.py
```

without modifying policy behavior.

---

## Step 3

Add passive Robometer logging.

π0.5 behavior should remain identical.

Output:

```text
[PI05] executing chunk 15
[ROBOMETER] progress=0.61 success=0.08

[PI05] executing chunk 16
[ROBOMETER] progress=0.77 success=0.15
```

---

## Step 4

Save per-episode Robometer logs.

---

## Step 5

Run test rollouts:

- successful,
- failed grasp,
- wrong object,
- partial completion.

Compare Robometer predictions.

---

## Step 6

Only after validation, optionally add Robometer-based task completion.

---

## Step 7

Build offline rollout scoring / filtering.

---

## Step 8

Only after all previous steps work, implement experimental π0.5 noise-space RL steering.

---

# Do NOT Do These Things

Do not:

- merge Robometer weights with π0.5,
- replace π0.5's vision encoder with Robometer,
- train all π0.5 parameters with RL immediately,
- alter action dimensions,
- alter action normalization without understanding the existing pipeline,
- remove existing safety checks,
- make Robometer mandatory for normal policy inference,
- assume a Robometer score is ground truth,
- hard-code paper-specific noise dimensions.

---

# Expected First Deliverable

The first working version should achieve only this:

```text
π0.5 performs task exactly as before

+

Robometer watches execution

+

terminal prints progress/success estimates

+

scores are saved to a log
```

For example:

```text
Task: Pick up the red cube

Chunk 1
progress=0.08
success=0.01

Chunk 2
progress=0.25
success=0.02

Chunk 3
progress=0.57
success=0.04

Chunk 4
progress=0.83
success=0.27

Chunk 5
progress=0.99
success=0.94
```

No action modification is required in this first deliverable.

---

# Information Claude Should Return Before Editing the Repository

Before implementing changes, inspect the repository and report:

1. Which file loads π0.5.
2. Which file performs inference.
3. Which function produces action chunks.
4. Whether the code uses OpenPI's `sample_actions`.
5. Current `action_horizon`.
6. Current `action_dim`.
7. Camera observation keys and shapes.
8. How the current language instruction is stored.
9. Where the main robot-control loop lives.
10. Whether execution is synchronous or asynchronous.
11. Where Robometer calls can be inserted with the least disruption.

Then make the smallest possible changes.

---

# References

Paper:

```text
https://arxiv.org/pdf/2603.02115
```

Robometer repository:

```text
https://github.com/robometer/robometer
```

OpenPI:

```text
https://github.com/Physical-Intelligence/openpi
```

---

# Final Objective

The long-term system should look like:

```text
                    ┌─────────────┐
camera/state ──────►│    π0.5     │
task instruction ─►│             │
                    └──────┬──────┘
                           │
                       actions
                           │
                           ▼
                         robot
                           │
                       observations
                           │
                           ▼
                    ┌─────────────┐
                    │  Robometer  │
                    └──────┬──────┘
                           │
                     reward/score
                           │
             ┌─────────────┴─────────────┐
             │                           │
             ▼                           ▼
       evaluation/logging       optional RL steering
                                      │
                                      ▼
                               learned noise input
                                      │
                                      └────► π0.5
```

The immediate goal is only the **evaluation/logging path**.

Do not implement RL steering until the Robometer predictions are validated on this robot and task distribution.

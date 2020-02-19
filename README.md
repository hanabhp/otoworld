# Reinforcement learning for computer audition

Authors: Grant Gasser, David Terpay, Omkar Ranadive
Advisor: Prem Seetharaman

Applying reinforcement learning to perform source separation.

Project timeline
- Week of 1/13
  - Learn: RL, Double Deep Q-Learning (DDQN), SOTA (vision-related tasks), acoustics (how sound travels)
  - Code: Existing implementations (Gym), Pyroom acoustics
  - Deliverable: Want `f(direct_sound, agent_loc, sound_loc, room_config) => convolved_sound`
- Week of 1/20
  - RL review 
  - Deliverable: Want environment setup and be observable; `file = env.render()`, save audio file with librosa
- Week of 1/27
  - Presentation on Thursday (RL overview + Project Explanation)
  - Deliverable: See To-do
- Week of 2/03
  - See To-do
- Week of 2/10
  - See To-do
- Week of 2/17
  - See To-do
- Week of 2/24
- Week of 3/02
- Week of 3/09

### Requirements:
#### Using Poetry
- For development, we are using Poetry for package and dependency management
- Install [Poetry](https://python-poetry.org/docs/#installation) - we use Poetry for package and dependency management
- Run `poetry install` to install dependencies for the project (listed in `pyproject.toml`)
- Run `poetry export -f requirements.txt` to create/update requirements based on `pyproject.toml`

#### Otherwise
Assuming `requirements.txt` is up do date, run `pip install -r requirements.txt` for the correct packages

### Run
`poetry run python main.py `

### Model
- Old way: mask in (0, 1); element-wise multiply and get the original source
- Train anchor points and "red" points 
- Steps:
    1. Project L and R channels to separate embedding spaces (features)
    2. Create anchors
    3. Track size (loudness) of clusters/sources in matrix (embedding spaces); go to louder side (L or R)
    4. Element-wise multiple anchors embedding to get mask
    5. Mask * respective channel, then sum that
    4. Embedding -> 
        - loudness of source0 in L ear
        - loudness of source1 in R ear
        - loudness of source0 in L ear
        - loudness of source1 in R ear
    5. Take these with linear layer and map to action space 

### Directions
- Keep < 8K Hz sample rate (8,000 samples/time intervals per second)

### To-do (High Level)
- [X] Split up Pyroom initiliazation and convolution calculation (in `basic_room.py`)
- [X] If stereo file, take mean of 2 channels (in `basic_room.py`)
- [X] Replace `wavfile.read` with `librosa` (add with poetry)
- [X] Figure out how to poetry `export` to a `requirements.txt` so users don't have to use `poetry`
- [X] Need 1 more microphone (2 total)
- [X] Randomize sound source files
- [X] Put sources randomly in the environment 
- [X] Place the agent roughly equidistant to the sources 
- [X] Keep the distance between mics 20 cm 
- [X] Add the orientation actions (left x degrees, right x degrees) to set of actions 
    - (NOTE: angle is determined in radians using the `linear_2D_array` function, use `np.pi`) 
- [X] More rooms (randomly generated if possible), simple rooms like hexagon, octagon 
- [X] Cut the lengths of the sources based on length of shortest source.
- [X] Make step size tunable
- [X] Updated movements to be able to deal with floats
- [X] Get running on gpubox
- [ ] One Action structure: rotate left, rotate right, step forward
- [ ] Second Action structure: U, D, L, R, rotate left, rotate right (similar to current)
- [ ] Have agent turn off both sources (move randomly in small environment)
- [X] Measure throughput (how many steps we can run per second without plotting with random agent)
  - ~ **20 steps/second**
- [ ] Store in buffer (S, A, S', R) which is (prev audio, action, current audio, reward), refer to [DQN code](https://pytorch.org/tutorials/intermediate/reinforcement_q_learning.html)

### RL Setup
* Agent should find source and "turn it off" (agent reaches same grid location)
    - State: convolved sound
    - Action space 1: rotate_left (x degrees), rotate_right (x degrees), 
    - Action space 2: rotate_left (x degrees), rotate_right (x degrees), step (L, R, U, D)
    - Small negative reward for each action, large reward for turning off source
    - Store replay buffer SAR

### Resources: 
#### Environments
* [PyRoom Acoustics](https://github.com/LCAV/pyroomacoustics)
* [Gym mini world](https://github.com/maximecb/gym-miniworld)
* [Gym mini grid](https://github.com/maximecb/gym-minigrid)
* [Pytorch DQN](https://pytorch.org/tutorials/intermediate/reinforcement_q_learning.html)


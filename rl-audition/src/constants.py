import os

# source data
DIR_MALE = "../sounds/dry_recordings/dev/051_subset/"
DIR_FEMALE = "../sounds/dry_recordings/dev/050_subset/"
AUDIO_EXTENSION = ".wav"

# saved data during experiment
DATA_PATH = "../data"
DIR_PREV_STATES = os.path.join(DATA_PATH, 'prev_states/')
DIR_NEW_STATES = os.path.join(DATA_PATH, 'new_states/')
DIR_DATASET_ITEMS = os.path.join(DATA_PATH, 'dataset_items/')
DIST_URL = "init_dist_to_target.p"
STEPS_URL = "steps_to_completion.p"
REWARD_URL = "rewards_per_episode.p"

# audio stuff
RESAMPLE_RATE = 8000

# env stuff
DIST_BTWN_EARS = 0.2

# max and min values of exploration rate
MAX_EPSILON = 1.0
MIN_EPSILON = 0.01

# reward structure
STEP_PENALTY = -0.1
TURN_OFF_REWARD = 10.0  # Keep this a float, otherwise Pytorch dataloader will throw errors

# dataset (reminder: do 20000 for experiments)
MAX_BUFFER_ITEMS = 500

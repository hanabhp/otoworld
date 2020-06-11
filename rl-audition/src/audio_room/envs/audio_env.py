import gym
from pyroomacoustics import MicrophoneArray, ShoeBox, Room, linear_2D_array, Constants
import numpy as np
import matplotlib.pyplot as plt
from gym import spaces
from scipy.spatial.distance import euclidean
from sklearn.metrics.pairwise import euclidean_distances
from copy import deepcopy
import nussl
import logging

import sys
sys.path.append("../../")

from utils import choose_random_files
import constants

# setup logging (with different logger than the agent logger)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(message)s')
file_handler = logging.FileHandler('environment.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.info('\n')
logger.info('-'*50)
logger.info('\nCreating new Audio Environment!\n')
logger.info('-'*50)
logger.info('\n')


class AudioEnv(gym.Env):
    def __init__(
        self,
        room_config,
        agent_loc=None,
        resample_rate=8000,
        num_channels=2,
        bytes_per_sample=2,
        corners=False,
        absorption=0.0,
        max_order=2,
        step_size=1,
        acceptable_radius=.5,
        num_sources=2,
        degrees=np.deg2rad(30),
        reset_sources=True,
    ):
        """
        This class inherits from OpenAI Gym Env and is used to simulate the agent moving in PyRoom.

        Args:
            room_config (List or np.array): dimensions of the room. For Shoebox, in the form of [10,10]. Otherwise,
                in the form of [[1,1], [1, 4], [4, 4], [4, 1]] specifying the corners of the room
            agent_loc (List or np.array): initial location of the agent (mic array)
            resample_rate (int): sample rate in Hz
            num_channels (int): number of channels (used in playing what the mic hears)
            bytes_per_sample (int): used in playing what the mic hears
            corners (bool): False if using Shoebox config, otherwise True
            absorption (float): Absorption param of the room (how walls absorb sound)
            max_order (int): another room parameter
            step_size (float): specified step size else we programmatically assign it
            acceptable_radius (float): source is considered found/turned off if agent is within this distance of src
            num_sources (int): the number of audio sources the agent will listen to
            degrees (float): value of degrees to rotate in radians (.2618 radians = 15 degrees)
            reset_sources (bool): True if you want to choose different sources when resetting env
        """
        self.resample_rate = resample_rate
        self.absorption = absorption
        self.max_order = max_order
        self.audio = []
        self.num_channels = num_channels
        self.bytes_per_sample = bytes_per_sample
        self.num_actions = 4
        self.action_space = spaces.Discrete(self.num_actions)
        self.action_to_string = {
            0: "Forward",
            1: "Backward",
            3: "Rotate Left",
            4: "Rotate right",
        }
        self.corners = corners
        self.room_config = room_config
        self.agent_loc = agent_loc
        self.initial_agent_loc = agent_loc
        self.acceptable_radius = acceptable_radius
        self.step_size = step_size
        self.num_sources = num_sources
        self.source_locs = None
        self.min_size_audio = np.inf
        self.degrees = degrees
        self.cur_angle = 0  # The starting angle is 0
        self.reset_sources = reset_sources

        # randomly choose sources
        self.direct_sources = choose_random_files(num_sources=self.num_sources)
        self.direct_sources_copy = deepcopy(self.direct_sources)

        # create the room and add sources
        self._create_room()
        self._add_sources()

        # The step size must be smaller than radius in order to make sure we don't
        # overstep a audio source
        if self.acceptable_radius < self.step_size / 2:
            raise ValueError(
                """The threshold radius (acceptable_radius) must be at least step_size / 2. Else, the agent may overstep 
                an audio source."""
            )

        # reward dict
        self.reward = {
            'step_penalty': constants.STEP_PENALTY, 
            'turn_off': constants.TURN_OFF_REWARD,
            'min_distance': 0
        }


    def _create_room(self):
        """
        This function creates the Pyroomacoustics room with our environment class variables.
        """
        logger.info('Create room.')
        # non-Shoebox config (corners of room are given)
        if self.corners:
            self.room = Room.from_corners(
                self.room_config, fs=self.resample_rate,
                absorption=self.absorption, max_order=self.max_order
            )

            # The x_max and y_max in this case would be used to generate agent's location randomly
            self.x_min = min(self.room_config[0])
            self.y_min = min(self.room_config[1])
            self.x_max = max(self.room_config[0])
            self.y_max = max(self.room_config[1])

        # ShoeBox config
        else:
            self.room = ShoeBox(
                self.room_config, fs=self.resample_rate,
                absorption=self.absorption, max_order=self.max_order
            )
            self.x_max = self.room_config[0]
            self.y_max = self.room_config[1]
            self.x_min, self.y_min = 0, 0

    def _move_agent(self, new_agent_loc, initial_placing=False):
        """
        This function moves the agent to a new location (given by new_agent_loc). It effectively removes the
        agent (mic array) from the room and then adds it back in the new location.

        TODO: 
        If initial_placing == True, the agent is placed in the room for the first time. This needs work.

        Args:
            new_agent_loc (List[int] or np.array or None): [x,y] coordinates of the agent's new location. Should be
                None if initial_placing is True.
            initial_placing (bool): True if initially placing the agent in the room at the beginning of the episode
        """
        # Placing agent in room for the first time (likely at the beginning of a new episode, after a reset)
        if initial_placing:
            if new_agent_loc is None:
                loc = self._sample_points(1, sources=False, agent=True)
                logger.info(f'Placing agent at {loc}')
                self.initial_agent_loc = loc
                self.agent_loc = loc
                self.cur_angle = np.random.uniform(-np.pi, np.pi)
            else:
                raise ValueError(
                    """new_agent_loc must be None (instead of new_agent_loc={}) if initial_placing is True. With initial placement, 
                    the agent is randomly placed in the room and there is no need for a new 
                    location to be provided.""".format(new_agent_loc)
                )
        else:
            # Set the new agent location (where to move)
            self.agent_loc = new_agent_loc
        # Delete the array at previous time step
        self.room.mic_array = None

        if self.num_channels == 2:
            # Create the array at current time step (2 mics, angle IN RADIANS, 0.2m apart)
            mic = MicrophoneArray(
                linear_2D_array(self.agent_loc, 2, self.cur_angle,
                                constants.DIST_BTWN_EARS), self.room.fs
            )
            self.room.add_microphone_array(mic)
        else:
            mic = MicrophoneArray(self.agent_loc.reshape(-1, 1), self.room.fs)
            self.room.add_microphone_array(mic)

    def _sample_points(self, num_points, sources=True, agent=False):
        """
        This function generates randomly sampled points for the sources (or agent) to be placed

        Args:
            num_points (int): Number of [x, y] random points to generate
            sources (bool): True if generating points for sources (agent must be False)
            agent(bool): True if generating points for agent (sources must be False)

        Returns:
            sample_points (List[List[int]]): A list of [x,y] points for source location
            or
            random_point (List[int]): An [x, y] point for agent location
        """
        assert(sources != agent)
        sampled_points = []

        if sources:
            angles = np.arange(0, 2 * np.pi, self.degrees).tolist()
            while len(sampled_points) < num_points:
                chosen_angles = np.random.choice(angles, num_points)
                for angle in chosen_angles:
                    direction = np.random.choice([-1, 1])
                    distance = np.random.uniform(2 * self.step_size, 5 * self.step_size)
                    x = (self.x_min + self.x_max) / 2
                    y = (self.y_min + self.y_max) / 2
                    x = x + direction * np.cos(angle) * distance
                    y = y + direction + np.sin(angle) * distance
                    point = [x, y]
                    if self.room.is_inside(point, include_borders=False):
                        accepted = True
                        if len(sampled_points) > 0:
                            dist_to_existing = euclidean_distances(
                                np.array(point).reshape(1, -1), sampled_points)
                            accepted = dist_to_existing.min() > 2 * self.step_size
                        if accepted:
                            sampled_points.append(point)
            return sampled_points
        elif agent:
            x = (self.x_min + self.x_max) / 2
            y = (self.y_min + self.y_max) / 2
            self.cur_angle = np.random.uniform(-np.pi, np.pi)
            return [x, y]


        #     for source_loc in self.source_locs:
        #         if (
        #             euclidean(random_point,
        #                         point) < self.acceptable_radius
        #             or euclidean(random_point, source_loc) < self.acceptable_radius
        #         ):
        #             out_of_range = False
                



        # while len(sampled_points) < num_points:
        #     random_point = [
        #         np.random.uniform(self.x_min, self.x_max),
        #         np.random.uniform(self.y_min, self.y_max),
        #     ]
        #     try:
        #         out_of_range = True
        #         for point in sampled_points:
        #             # ensures sources are not too close to each other or the agent
        #             if sources:
        #                 if (
        #                     euclidean(random_point, point) < 4.0 * self.acceptable_radius
        #                     or euclidean(random_point, self.agent_loc) < 4.0 * self.acceptable_radius
        #                 ):
        #                     out_of_range = False
        #             # ensures agent is not too close to sources
        #             elif agent:
        #                 for source_loc in self.source_locs:
        #                     if (
        #                         euclidean(random_point,
        #                                   point) < self.acceptable_radius
        #                         or euclidean(random_point, source_loc) < self.acceptable_radius
        #                     ):
        #                         out_of_range = False

        #         if self.room.is_inside(random_point, include_borders=False) and out_of_range:
        #             if sources:
        #                 sampled_points.append(random_point)
        #             elif agent:
        #                 # keep agent loc formatting ([x, y] instead of [[x, y]])
        #                 return random_point
        #     except:
        #         # in case is_inside func fails, randomly sample again
        #         continue

        # return sampled_points

    def _add_sources(self, new_source_locs=None, reset_env=False, removing_source=None):
        """
        This function adds the sources to the environment.

        Args:
            new_source_locs (List[List[int]]): A list consisting of [x, y] coordinates if the programmer wants
                to manually set the new source locations
            reset_env (bool): Bool indicating whether we reset_env the agents position to be the mean
                of all the sources
            removing_source (None or int): Value that will tell us if we are removing a source
                from sources
        """
        # Can reset with new randomly sampled sources (typically at the start of a new episode)
        if self.reset_sources:
            self.direct_sources = choose_random_files(
                num_sources=self.num_sources)
        else:
            self.direct_sources = deepcopy(self.direct_sources_copy)

        if new_source_locs is None:
            self.source_locs = self._sample_points(num_points=self.num_sources)
        else:
            self.source_locs = new_source_locs

        logger.info('Adding sources')
        logger.info(f'Direct Sources: {self.direct_sources}')
        logger.info(f'Source locs: {self.source_locs}')

        self.audio = []
        self.min_size_audio = np.inf
        for idx, audio_file in enumerate(self.direct_sources):
            logger.info(f'Adding src {idx} ({audio_file}) to pyroom.')
            # Audio will be automatically re-sampled to the given rate (default sr=8000).
            a = nussl.AudioSignal(audio_file, sample_rate=self.resample_rate)
            a.to_mono()

            # normalize audio so both sources have similar volume at beginning before mixing
            loudness = a.loudness()

            # mix to reference db
            ref_db = -40
            db_diff = ref_db - loudness
            gain = 10 ** (db_diff / 20)
            a = a * gain

            # Find min sized source to ensure something is playing at all times
            if len(a) < self.min_size_audio:
                self.min_size_audio = len(a)
            self.audio.append(a.audio_data.squeeze())

        # add sources using audio data
        for idx, audio in enumerate(self.audio):
            self.room.add_source(
                self.source_locs[idx], signal=audio[: self.min_size_audio])

    def _remove_source(self, index):
        """
        This function removes a source from the environment

        Args:
            index (int): index of the source to remove
        """
        src = self.source_locs.pop(index)
        src2 = self.direct_sources.pop(index)

        # actually remove source from the room
        room_src = self.room.sources.pop(index)

        logger.info(f'Removing src {src}, direct src {src2}, room src {room_src} at index {index}')
        logger.info(f'Remaining sources: {self.direct_sources}, and their locations: {self.source_locs}, '
                    f'and in pyroom: {self.room.sources}')

    def step(self, action, play_audio=False, show_room=False):
        """
        This function simulates the agent taking one step in the environment (and room) given an action:
            0 = Move forward
            1 = Move backward
            2 = Turn left x degrees
            3 = Turn right x degrees

        It calls _move_agent, checks to see if the agent has reached a source, and if not, computes the RIR.

        Args:
            action (int): direction agent is to move - 0 (L), 1 (R), 2 (U), 3 (D)
            play_audio (bool): whether to play the the mic audio (stored in "data")
            show_room (bool): Controls whether room is visually plotted at each step

        Returns:
            Tuple of the format List (empty if done, else [data]), reward, done

        # NOTE: unlikely case that agent finds source on step 0, data doesn't get recorded
        """
        x, y = self.agent_loc[0], self.agent_loc[1]
        done = False

        if action in [0, 1]:
            if action == 0:
                sign = 1
            if action == 1:
                sign = -1
            x = x + sign * np.cos(self.cur_angle) * self.step_size
            y = y + sign * np.sin(self.cur_angle) * self.step_size
        elif action == 3:
            self.cur_angle += self.degrees
        elif action == 4:
            self.cur_angle -= self.degrees
        # Check if the new points lie within the room
        try:
            if self.room.is_inside([x, y], include_borders=False):
                points = np.array([x, y])
            else:
                points = self.agent_loc
        except:
            # in case the is_inside func fails
            points = self.agent_loc

        # Move agent in the direction of action
        self._move_agent(new_agent_loc=points)

        # Check if goal state is reached
        for index, source in enumerate(self.source_locs):
            # Agent has found the source
            if euclidean(self.agent_loc, source) <= self.acceptable_radius:
                logger.info(f'Agent has found source. Agent loc: {self.agent_loc}, Source loc: {source}')
                # If there is more than one source, then we want to remove this source
                if len(self.source_locs) > 1:
                    logger.info(f'Not the last source! Still returning reward {constants.TURN_OFF_REWARD}')
                    # remove the source (will take effect in the next step)
                    self._remove_source(index=index)

                    # Calculate the impulse response
                    self.room.compute_rir()
                    self.room.simulate()
                    data = self.room.mic_array.signals

                    # Convert the data back to Nussl Audio object
                    data = nussl.AudioSignal(
                        audio_data_array=data, sample_rate=self.resample_rate)

                    if play_audio or show_room:
                        self.render(data, play_audio, show_room)

                    done = False
                    reward = constants.TURN_OFF_REWARD
                    return data, reward, done

                # This was the last source hence we can assume we are done
                else:
                    logger.info(f'Last source found. Returning reward {constants.TURN_OFF_REWARD}')
                    done = True
                    reward = constants.TURN_OFF_REWARD
                    self.reset()
                    return None, reward, done

        if not done:
            # Calculate the impulse response
            self.room.compute_rir()
            self.room.simulate()
            data = self.room.mic_array.signals

            # Convert data to nussl audio signal
            data = nussl.AudioSignal(
                audio_data_array=data, sample_rate=self.resample_rate)

            if play_audio or show_room:
                self.render(data, play_audio, show_room)

            # penalize time it takes to reach a source (penalty for each step)
            reward = constants.STEP_PENALTY
            min_dist = euclidean_distances(
                np.array(self.agent_loc).reshape(1, -1), self.source_locs).min()
            reward += min(1 / (min_dist + 1e-4), constants.TURN_OFF_REWARD)
            print(self.agent_loc, self.cur_angle, self.source_locs, reward)

            # Return the room rir and convolved signals as the new state
            return data, reward, done

    def reset(self, removing_source=None):
        """
        This function resets the sources to a random location within the room. To be used after each episode.

        args:
            removing_source (int): Integer that tells us the index of sources that we will be removing
        """
        logger.info('\n')
        logger.info('-'*50)
        logger.info('\nReset environment. Create room, place agent, add sources.')
        # re-create room
        self._create_room()

        # randomly place agent in room at beginning of next episode
        self._move_agent(new_agent_loc=None, initial_placing=True)

        # randomly add sources to the room
        self._add_sources()

    def render(self, data, play_audio, show_room):
        """
        Play the convolved sound using SimpleAudio.

        Args:
            data (AudioSignal): if 2 mics, should be of shape (x, 2)
            play_audio (bool): If true, audio will play
            show_room (bool): If true, room will be displayed to user
        """
        if play_audio:
            data.play()

            # Show the room while the audio is playing
            if show_room:
                fig, ax = self.room.plot(img_order=0)
                plt.pause(1)

            plt.close()

        elif show_room:
            fig, ax = self.room.plot(img_order=0)
            plt.pause(1)
            plt.close()

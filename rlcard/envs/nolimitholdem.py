import json
import os
import numpy as np

import rlcard
from rlcard.envs.env import Env
from rlcard.games.nolimitholdem.game import NolimitholdemGame as Game

class NolimitholdemEnv(Env):
    ''' Limitholdem Environment
    '''

    def __init__(self, config):
        ''' Initialize the Limitholdem environment
        '''
        self.game  =Game()
        super().__init__(config)
        self.actions = ['call', 'fold', 'check']
        self.state_shape = [54]
        for raise_amount in range(1, self.game.init_chips+1):
            self.actions.append(raise_amount)

        with open(os.path.join(rlcard.__path__[0], 'games/limitholdem/card2index.json'), 'r') as file:
            self.card2index = json.load(file)

    def _get_legal_actions(self):
        ''' Get all leagal actions

        Returns:
            encoded_action_list (list): return encoded legal action list (from str to int)
        '''
        return self.game.get_legal_actions()

    def _extract_state(self, state):
        ''' Extract the state representation from state dictionary for agent

        Note: Currently the use the hand cards and the public cards. TODO: encode the states

        Args:
            state (dict): Original state from the game

        Returns:
            observation (list): combine the player's score and dealer's observable score for observation
        '''
        extracted_state = {}

        legal_actions = [self.actions.index(a) for a in state['legal_actions']]
        extracted_state['legal_actions'] = legal_actions

        public_cards = state['public_cards']
        hand = state['hand']
        my_chips = state['my_chips']
        all_chips = state['all_chips']
        cards = public_cards + hand
        idx = [self.card2index[card] for card in cards]
        obs = np.zeros(54)
        obs[idx] = 1
        obs[52] = float(my_chips)
        obs[53] = float(max(all_chips))
        extracted_state['obs'] = obs

        if self.allow_raw_data:
            extracted_state['raw_obs'] = state
            extracted_state['raw_legal_actions'] = [a for a in state['legal_actions']]
        if self.record_action:
            extracted_state['action_record'] = self.action_recorder
        return extracted_state

    def get_payoffs(self):
        ''' Get the payoff of a game

        Returns:
           payoffs (list): list of payoffs
        '''
        return self.game.get_payoffs()

    def _decode_action(self, action_id):
        ''' Decode the action for applying to the game

        Args:
            action id (int): action id

        Returns:
            action (str): action for the game
        '''
        legal_actions = self.game.get_legal_actions()
        if self.actions[action_id] not in legal_actions:
            if 'check' in legal_actions:
                return 'check'
            else:
                return 'fold'
        return self.actions[action_id]

    def get_perfect_information(self):
        ''' Get the perfect information of the current state

        Returns:
            (dict): A dictionary of all the perfect information of the current state
        '''
        state = {}
        state['chips'] = [self.game.players[i].in_chips for i in range(self.player_num)]
        state['public_card'] = [c.get_index() for c in self.game.public_cards] if self.game.public_cards else None
        state['hand_cards'] = [[c.get_index() for c in self.game.players[i].hand] for i in range(self.player_num)]
        state['current_player'] = self.game.game_pointer
        state['legal_actions'] = self.game.get_legal_actions()
        return state



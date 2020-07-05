from ray import tune
from ray.rllib.agents.ppo import PPOTrainer
from ray.rllib.agents.dqn import DQNTrainer
from ray.rllib.agents.ppo.ppo_tf_policy import PPOTFPolicy
from ray.rllib.agents.dqn.dqn_tf_policy import DQNTFPolicy
from ray.rllib.models import ModelCatalog
from ray.tune.registry import register_env

from rlcard.rllib_utils.random_policy import RandomPolicy
from rlcard.rllib_utils.model import ParametricActionsModel
from rlcard.rllib_utils.rlcard_wrapper import RLCardWrapper

import time


class RLTrainer:
    """
    Class used to train an rllib agent on an environment.

    policy_to_class = {
        'ppo_policy_1': PPOTFPolicy,
        'dqn_policy_1': DQNTFPolicy,
        'random_policy': RandomPolicy
    }

    agent_to_policy = {
        'player_1': 'ppo_policy_1',
        'player_2': 'dqn_policy_1',
    }
    """

    POLICY_TO_TRAINER = {
        PPOTFPolicy: PPOTrainer,
        DQNTFPolicy: DQNTrainer,
        RandomPolicy: None
    }

    POLICY_TO_CONFIG = {
        PPOTFPolicy: {
            # "env": rlcard_env_id,
            "model": {
                "custom_model": "parametric_model_tf",
                # 'fcnet_hiddens': [256, 256, 256]
            },
            # disable filters, otherwise we would need to synchronize those
            # as well to the DQN agent
            # "observation_filter": "NoFilter",
        },
        DQNTFPolicy: {
            "model": {
                "custom_model": "parametric_model_tf",
                # 'fcnet_hiddens': [256, 256, 256]
            },
            # TODO(ekl) we need to set these to prevent the masked values
            # from being further processed in DistributionalQModel, which
            # would mess up the masking. It is possible to support these if we
            # defined a a custom DistributionalQModel that is aware of masking.
            'hiddens': [],
            "dueling": False,
        },
        RandomPolicy: {}
    }

    def __init__(self, rlcard_env_id, agent_to_policy, policy_to_class, experiment_name=None, resources={}):

        self.rlcard_env_id = rlcard_env_id
        self.agent_to_policy = agent_to_policy
        self.policy_to_class = policy_to_class
        self.experiment_name = rlcard_env_id if experiment_name is None else experiment_name

        # --- Assert input parameters are valid ---
        all_policies = {v for _, v in policy_to_class.items()}
        non_supported_policies = all_policies.difference(self.POLICY_TO_CONFIG.keys())
        assert len(non_supported_policies) == 0, 'The following policies are not supported: {}.'.format(
            non_supported_policies)
        assert all([v in policy_to_class for _, v in agent_to_policy.items()]),\
            'Check that agents in agent_to_policy are assigned to policies in policy_to_class.'

        # --- Register env and model to be used by rllib ---
        # TODO: how to create a RLcard env with multiple agents? Seems by default is with 2
        RLCardWrapped = lambda _: RLCardWrapper(rlcard_env_id=rlcard_env_id)
        register_env(rlcard_env_id, RLCardWrapped)
        ModelCatalog.register_custom_model("parametric_model_tf", ParametricActionsModel)

        # --- Extract the configuration for the trainer(s) ---
        env_tmp = RLCardWrapped(None)
        self.trainer_to_config = self.collect_trainers_config(
            policy_to_class=policy_to_class,
            agent_to_policy=agent_to_policy,
            observation_space=env_tmp.observation_space,
            action_space=env_tmp.action_space,
            resources=resources
        )  # {trainer class: trainer config}

    def collect_trainers_config(self, policy_to_class, agent_to_policy, observation_space, action_space, resources):
        # 1. Collect the policy configs to be used by the trainer(s)
        policies = {}  # {policy_name: (policy class, obs space, action space, policy config), ...}
        for policy_name, policy_class in policy_to_class.items():
            policies[policy_name] = (
                policy_class,
                observation_space,
                action_space,
                self.POLICY_TO_CONFIG[policy_class]
            )

        # 2. Collect for every trainer the polices it should train
        policies_to_train = {}  # {trainer class: ['policy name 1', ...], ...}
        for _, policy_name in agent_to_policy.items():
            policy_class = policy_to_class[policy_name]
            trainer_class = self.POLICY_TO_TRAINER[policy_class]
            if trainer_class is not None:  # RandomPolicy is not to be trained and has trainer None
                if trainer_class not in policies_to_train:
                    policies_to_train[trainer_class] = set()
                policies_to_train[trainer_class].add(policy_name)

        # 3. Finally collect all the trainers config
        trainer_to_config = {}  # {trainer class: trainer config}
        for trainer_class, policies_to_train_ in policies_to_train.items():
            trainer_to_config[trainer_class] = {
                "env": self.rlcard_env_id,
                "multiagent": {
                    "policies_to_train": policies_to_train_,
                    "policies": policies,
                    "policy_mapping_fn": lambda agent_id: self.agent_to_policy[agent_id],
                },
            }
            trainer_to_config[trainer_class].update(resources)
        return trainer_to_config

    def train(self, stop=None, restore=None):
        # -------- Most interesting parameters for trainer setting --------
        # callbacks: <class 'ray.rllib.agents.callbacks.DefaultCallbacks'>
        # env_config: {}
        # evaluation_config: {}
        # evaluation_num_episodes: 10
        # gamma: 0.99
        # lr: 5.0e-05
        # model:
        #   fcnet_activation: tanh
        #   fcnet_hiddens:
        #   - 256
        #   - 256
        #   use_lstm: false
        # num_gpus: 0
        # num_gpus_per_worker: 0
        # num_cpus_per_worker: 1,
        # num_workers: 2
        # train_batch_size: 4000

        start = time.time()
        # TODO: (1) add evaluation, (2) add support for multi policy training
        if len(self.trainer_to_config) > 1:
            raise NotImplementedError('Support for multiple policy training still to be implemented, please set agents with same policy.')
            # # --- Initialize ray ---
            # # ray.init(num_cpus=4, num_gpus=1)
            # ray.init(num_cpus=4)

            # TODO: iterate over all the trainers then propagate all the model parameters at the end of every iteration
            # # Instantiate all the trainers
            # trainers = []
            # for trainer_class, trainer_config in self.trainer_to_config.items():
            #     # print(policies)
            #     trainers.append(trainer_class(trainer_config))
            # # Train all the trainers
            # for i in range(stop['training_iteration']):
            #     trainer.config.policies_to_train
            #     for trainer in trainers:
            #         trainer.train()
            #     for trainer in trainers:
            #         for p in trainer.config['multiagent']['policies_to_train']
            #             trainer.set_weights(trainer_eval.get_weights(["ppo_policy_1"]))
            #     policy_rewards = sorted(['{}: {}'.format(k, v) for k, v in res['policy_reward_mean'].items()])
            #     print("Iteration {}. policy_reward_mean: {}".format(i, policy_rewards))
        else:
            # If there is only one trainer then we use tune
            trainer_class, trainer_config = self.trainer_to_config.popitem()

            res = tune.run(
                trainer_class,
                name=self.experiment_name,  # This is used to specify the logging directory.
                # resources_per_trial=resources_per_trial,
                # scheduler=scheduler,
                stop=stop,
                verbose=1,
                config=trainer_config,
                # checkpoint_freq=0,
                checkpoint_at_end=True,
                restore=restore
            )

        stop = time.time()
        train_duration = time.strftime('%H:%M:%S', time.gmtime(stop-start))
        print('Training finished ({}), check the results in ~/ray_results/<dir>/'.format(train_duration))
        return res
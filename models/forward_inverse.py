from __future__ import print_function, division, absolute_import

import torch

from .models import *
from .priors import SRLDenseNetwork, SRLConvolutionalNetwork
from .autoencoders import CNNAutoEncoder
from .priors import SRLLinear

from preprocessing.preprocess import INPUT_DIM


class BaseForwardModel(BaseModelSRL):
    def __init__(self):
        """
        :param state_dim: (int)
        :param action_dim: (int)
        """
        super(BaseForwardModel, self).__init__()

    def initForwardNet(self, state_dim, action_dim, ratio=1):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.forward_net = nn.Linear(int(state_dim * ratio) + action_dim, state_dim)
        self.ratio = ratio

    def forward(self, x):
        raise NotImplementedError()

    def forwardModel(self, state, action):
        """
        Predict next state given current state and action
        :param state: (th Variable)
        :param action: (th Tensor)
        :return: (th Variable)
        """
        # Predict the delta between the next state and current state
        concat = torch.cat((state[:, :int(self.state_dim*self.ratio)], encodeOneHot(action, self.action_dim)), 1)
        return state + self.forward_net(concat)


class BaseInverseModel(BaseModelSRL):
    def __init__(self):
        """
        :param state_dim: (int)
        :param action_dim: (int)
        """
        super(BaseInverseModel, self).__init__()

    def initInverseNet(self, state_dim, action_dim, ratio=1):
        self.inverse_net = nn.Linear(int(state_dim * ratio) * 2, action_dim)
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.ratio = ratio

    def forward(self, x):
        raise NotImplementedError()

    def inverseModel(self, state, next_state):
        """
        Predict action given current state and next state
        :param state: (th Variable)
        :param next_state: (th Variable)
        :return: probability of each action
        """
        return self.inverse_net(th.cat((state[:, :int(self.state_dim*self.ratio)], next_state[:, :int(self.state_dim*self.ratio)]), 1))


class BaseRewardModel(BaseModelSRL):
    def __init__(self, state_dim=2, action_dim=6):
        """
        :param state_dim: (int)
        :param action_dim: (int)
        """
        super(BaseRewardModel, self).__init__()

    def initRewardNet(self, state_dim, action_dim, ratio=1):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.reward_net = nn.Sequential(nn.Linear(int(state_dim *ratio), 2),
                                        nn.ReLU(),
                                        nn.Linear(2, 2),
                                        nn.ReLU(),
                                        nn.Linear(2, 2))
        self.ratio = ratio

    def forward(self, x):
        raise NotImplementedError()

    def rewardModel(self, state):
        """
        Predict reward given current state and action
:        :param state: (th Variable)
        :param action: (th Tensor)
        :return: (th Variable)
        """
        #return self.reward_net(torch.cat((state[:, int(self.state_dim* ( 1 - self.ratio) ):], encodeOneHot(action, self.action_dim), next_state[:, int(self.state_dim * ( 1 - self.ratio) ):]), 1))
        return self.reward_net(state)


class SRLModules(BaseForwardModel, BaseInverseModel, BaseRewardModel):
    def __init__(self, state_dim=2, action_dim=6, ratio=1, cuda=False, losses=None, model_type="custom_cnn"):
        """
        :param state_dim:
        :param action_dim:
        :param cuda:
        """
        self.model_type = model_type

        bool_ = "forward" not in losses and "inverse" not in losses and "reward" not in losses
        if bool_:
            BaseModelSRL.__init__(self)
        else:
            if "forward" in losses:
                BaseForwardModel.__init__(self)

            if "inverse" in losses:
                BaseInverseModel.__init__(self)

            if "reward" in losses:
                BaseRewardModel.__init__(self)

            if "forward" in losses:
                self.initForwardNet(state_dim, action_dim, ratio)

            if "inverse" in losses:
                self.initInverseNet(state_dim, action_dim, ratio)

            if "reward" in losses:
                self.initRewardNet(state_dim, action_dim, ratio)

        # Architecture
        if model_type == "custom_cnn":
            self.nn = CustomCNN(state_dim)
        elif model_type == "linear":
            self.nn = SRLLinear(input_dim=INPUT_DIM, state_dim=state_dim, cuda=cuda)
        elif model_type == "mlp":
            self.nn = SRLDenseNetwork(INPUT_DIM, state_dim, cuda=cuda)
        elif model_type == "resnet":
             self.nn = SRLConvolutionalNetwork(state_dim, cuda)
        elif model_type == "ae":
            self.nn = CNNAutoEncoder(state_dim)
            self.nn.encoder_fc.cuda()
            self.nn.decoder_fc.cuda()

        if cuda:
            self.nn.cuda()

    def getStates(self, observations):
        """
        :param observations: (PyTorch Variable)
        :return: (PyTorch Variable)
        """
        if self.model_type == "ae":
            return self.nn.encode(observations)
        else:
            return self.forward(observations)

    def forward(self, x):
        if self.model_type == "ae":
            return self.nn.forward(x)
        if self.model_type == 'linear' or self.model_type == 'mlp':
            x = x.contiguous()
        return self.nn(x)
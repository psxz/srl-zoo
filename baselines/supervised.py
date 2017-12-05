from __future__ import print_function, division, absolute_import

import json
import time
import argparse

import numpy as np
import torch as th
import torch.nn as nn
from sklearn.model_selection import train_test_split
from tqdm import tqdm

import plotting.representation_plot as plot_script
from models.base_learner import BaseLearner
from models.models import ConvolutionalNetwork, DenseNetwork
from plotting.representation_plot import plot_representation, plt
from preprocessing.data_loader import SupervisedDataLoader
from preprocessing.preprocess import INPUT_DIM
from utils import parseDataFolder, createFolder

# Python 2/3 compatibility
try:
    input = raw_input
except NameError:
    pass

DISPLAY_PLOTS = True
EPOCH_FLAG = 1  # Plot every 1 epoch
BATCH_SIZE = 32
TEST_BATCH_SIZE = 512


class SupervisedLearning(BaseLearner):
    """
    :param state_dim: (int)
    :param model_type: (str) one of "resnet" or "mlp"
    :param seed: (int)
    :param learning_rate: (float)
    :param cuda: (bool)
    """

    def __init__(self, state_dim, model_type="resnet", log_folder="logs/default",
                 seed=1, learning_rate=0.001, cuda=False):

        super(SupervisedLearning, self).__init__(state_dim, BATCH_SIZE, seed, cuda)

        if model_type == "resnet":
            self.model = ConvolutionalNetwork(self.state_dim, cuda)
        elif model_type == "mlp":
            self.model = DenseNetwork(INPUT_DIM, self.state_dim)
        else:
            raise ValueError("Unknown model: {}".format(model_type))
        print("Using {} model".format(model_type))

        if cuda:
            self.model.cuda()
        learnable_params = [param for param in self.model.parameters() if param.requires_grad]
        self.optimizer = th.optim.Adam(learnable_params, lr=learning_rate)
        self.log_folder = log_folder

    def learn(self, true_states, images_path, rewards):
        """
        Learn a state representation
        :param images_path: (numpy 1D array)
        :param true_states: (numpy tensor)
        :param rewards: (numpy 1D array)
        :return: (numpy tensor) the learned states for the given observations
        """
        true_states = true_states.astype(np.float32)
        x_indices = np.arange(len(true_states)).astype(np.int64)

        # Split into train/validation set
        x_train, x_val, y_train, y_val = train_test_split(x_indices, true_states,
                                                          test_size=0.33, random_state=self.seed)

        train_loader = SupervisedDataLoader(x_train, y_train, images_path, batch_size=self.batch_size)
        val_loader = SupervisedDataLoader(x_val, y_val, images_path, batch_size=TEST_BATCH_SIZE, is_training=False)
        # For plotting
        data_loader = SupervisedDataLoader(x_indices, true_states, images_path, batch_size=TEST_BATCH_SIZE,
                                           no_targets=True, is_training=False)

        # TRAINING -----------------------------------------------------------------------------------------------------
        criterion = nn.MSELoss()
        # criterion = F.smooth_l1_loss
        best_error = np.inf
        best_model_path = "{}/srl_supervised_model.pth".format(self.log_folder)

        self.model.train()
        start_time = time.time()
        for epoch in range(N_EPOCHS):
            # In each epoch, we do a full pass over the training data:
            train_loss, val_loss = 0, 0
            train_loader.resetAndShuffle()
            pbar = tqdm(total=len(train_loader))
            for batch_idx, (obs, target_states) in enumerate(train_loader):
                if self.cuda:
                    obs, target_states = obs.cuda(), target_states.cuda()

                pred_states = self.model(obs)
                self.optimizer.zero_grad()
                loss = criterion(pred_states, target_states)
                loss.backward()
                self.optimizer.step()
                train_loss += loss.data[0]
                pbar.update(1)
            pbar.close()

            train_loss /= len(train_loader)

            self.model.eval()
            val_loader.resetIterator()
            # Pass on the validation set
            for obs, target_states in val_loader:
                if self.cuda:
                    obs, target_states = obs.cuda(), target_states.cuda()

                pred_states = self.model(obs)
                loss = criterion(pred_states, target_states)
                val_loss += loss.data[0]

            val_loss /= len(val_loader)
            self.model.train()  # Restore train mode

            # Save best model
            if val_loss < best_error:
                best_error = val_loss
                th.save(self.model.state_dict(), best_model_path)

            # Then we print the results for this epoch:
            if (epoch + 1) % EPOCH_FLAG == 0:
                print("Epoch {:3}/{}".format(epoch + 1, N_EPOCHS))
                print("train_loss:{:.4f} val_loss:{:.4f}".format(train_loss, val_loss))
                print("{:.2f}s/epoch".format((time.time() - start_time) / (epoch + 1)))
                if DISPLAY_PLOTS:
                    # Optionally plot the current state space
                    plot_representation(self.predStatesWithDataLoader(data_loader), rewards, add_colorbar=epoch == 0,
                                        name="Learned State Representation (Training Data)")
        if DISPLAY_PLOTS:
            plt.close("Learned State Representation (Training Data)")

        # Load best model before predicting states
        self.model.load_state_dict(th.load(best_model_path))
        # return predicted states for training observations
        return self.predStatesWithDataLoader(data_loader)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Supervised Learning')
    parser.add_argument('--epochs', type=int, default=50, metavar='N',
                        help='number of epochs to train (default: 50)')
    parser.add_argument('--seed', type=int, default=1, metavar='S',
                        help='random seed (default: 1)')
    parser.add_argument('-bs', '--batch_size', type=int, default=32, help='batch_size (default: 32)')
    parser.add_argument('-lr', '--learning_rate', type=float, default=0.005, help='learning rate (default: 0.005)')
    parser.add_argument('--no-cuda', action='store_true', default=False, help='disables CUDA training')
    parser.add_argument('--no-plots', action='store_true', default=False, help='disables plots')
    parser.add_argument('--model_type', type=str, default="resnet", help='Model architecture (default: "resnet")')
    parser.add_argument('--data_folder', type=str, default="", help='Dataset folder', required=True)

    args = parser.parse_args()
    args.cuda = not args.no_cuda and th.cuda.is_available()
    DISPLAY_PLOTS = not args.no_plots
    plot_script.INTERACTIVE_PLOT = DISPLAY_PLOTS
    N_EPOCHS = args.epochs
    BATCH_SIZE = args.batch_size
    args.data_folder = parseDataFolder(args.data_folder)
    log_folder = "logs/{}/baselines/supervised".format(args.data_folder)
    createFolder(log_folder, "supervised folder already exist")

    folder_path = '{}/NearestNeighbors/'.format(log_folder)
    createFolder(folder_path, "NearestNeighbors folder already exist")

    print('Log folder: {}'.format(log_folder))

    print('Loading data ... ')
    rewards = np.load("data/{}/preprocessed_data.npz".format(args.data_folder))['rewards']

    # TODO: normalize true states
    ground_truth = np.load("data/{}/ground_truth.npz".format(args.data_folder))
    state_dim = ground_truth['arm_states'].shape[1]

    # Create partial exp_config for KNN plots
    with open('{}/exp_config.json'.format(log_folder), 'wb') as f:
        json.dump({"data_folder": args.data_folder, "state_dim": state_dim}, f)

    print('Learning a state representation ... ')
    srl = SupervisedLearning(state_dim, model_type=args.model_type, seed=args.seed,
                             log_folder=log_folder, learning_rate=args.learning_rate,
                             cuda=args.cuda)
    learned_states = srl.learn(ground_truth['arm_states'], ground_truth['images_path'], rewards)
    srl.saveStates(learned_states, ground_truth['images_path'], rewards, log_folder)

    name = "Learned State Representation - {} \n Supervised Learning".format(args.data_folder)
    path = "{}/learned_states.png".format(log_folder)
    plot_representation(learned_states, rewards, name, add_colorbar=True, path=path)

    if DISPLAY_PLOTS:
        input('\nPress any key to exit.')

import numpy as np
from utils import load_data
from fuel.datasets import IterableDataset
from fuel.streams import DataStream
import theano
from fuel.transformers import Transformer
floatX = theano.config.floatX


class SampleDrops(Transformer):
    def __init__(self, data_stream, drop_prob, hidden_dim,
                 is_for_test, **kwargs):
        super(SampleDrops, self).__init__(
            data_stream, **kwargs)
        self.drop_prob = drop_prob
        self.hidden_dim = hidden_dim
        self.is_for_test = is_for_test
        self.produces_examples = False

    def get_data(self, request=None):
        data = next(self.child_epoch_iterator)
        transformed_data = []
        transformed_data.append(data[0])
        transformed_data.append(data[1])
        T, B, _ = data[1].shape
        if self.is_for_test:
            drops = np.ones((T, B, self.hidden_dim)) * self.drop_prob
        else:
            drops = np.random.binomial(n=1, p=self.drop_prob,
                                       size=(T, B, self.hidden_dim))
        transformed_data.append(drops.astype(floatX))
        return transformed_data


def get_seq_mnist_streams(hidden_dim, batch_size=100, drop_prob=0.5):
    permutation = np.random.randint(0, 784, size=(784,))

    train_set, valid_set, test_set = load_data('mnist.pkl.gz')
    train_x = train_set[0].reshape((50000 / batch_size, batch_size, 784))
    train_x = np.swapaxes(train_x, 2, 1)
    train_x = train_x[:, :, :, np.newaxis]
    # Now the dimension is num_batches x 784 x batch_size x 1

    train_y = (np.zeros(train_set[0].shape) - 1)
    # label for each time-step is -1 and for the last one is the real label
    train_y[:, -1] = train_set[1]
    train_y = train_y.reshape((50000 / batch_size, batch_size, 784))
    train_y = np.swapaxes(train_y, 2, 1)
    train_y = train_y[:, :, :, np.newaxis]
    # Now the dimension is num_batches x 784 x batch_size x 1

    valid_x = valid_set[0].reshape((10000 / batch_size, batch_size, 784))
    valid_x = np.swapaxes(valid_x, 2, 1)
    valid_x = valid_x[:, :, :, np.newaxis]
    # Now the dimension is num_batches x 784 x batch_size x 1

    valid_y = (np.zeros(valid_set[0].shape) - 1)
    # label for each time-step is -1 and for the last one is the real label
    valid_y[:, -1] = valid_set[1]
    valid_y = valid_y.reshape((10000 / batch_size, batch_size, 784))
    valid_y = np.swapaxes(valid_y, 2, 1)
    valid_y = valid_y[:, :, :, np.newaxis]
    # Now the dimension is num_batches x 784 x batch_size x 1

    train_x = train_x[:, permutation]
    valid_x = valid_x[:, permutation]

    train = IterableDataset({'x': train_x.astype(floatX),
                             'y': train_y[:, -1, :, 0].astype('int32')})
    train_stream = DataStream(train)
    train_stream = SampleDrops(train_stream, drop_prob, hidden_dim, False)
    train_stream.sources = ('y', 'x', 'drops')

    train_stream.get_epoch_iterator().next()

    valid = IterableDataset({'x': valid_x.astype(floatX),
                             'y': valid_y[:, -1, :, 0].astype('int32')})
    valid_stream = DataStream(valid)
    valid_stream = SampleDrops(valid_stream, drop_prob, hidden_dim, True)
    valid_stream.sources = ('y', 'x', 'drops')

    return train_stream, valid_stream

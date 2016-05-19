import numpy as np
from utils import load_data
from fuel.datasets import IterableDataset
from fuel.streams import DataStream
import theano
from fuel.transformers import Transformer
import fuel
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


def get_dataset(which_set):
    MNIST = fuel.datasets.MNIST
    # jump through hoops to instantiate only once and only if needed
    _datasets = dict(
        train=MNIST(which_sets=["train"], subset=slice(None, 50000)),
        valid=MNIST(which_sets=["train"], subset=slice(50000, None)),
        test=MNIST(which_sets=["test"]))
    return _datasets[which_set]


def get_stream(which_set, batch_size, drop_prob,
               hidden_dim, for_evaluation, num_examples=None):
    np.random.seed(seed=1)
    permutation = np.random.randint(0, 784, size=(784,))
    dataset = get_dataset(which_set)
    if num_examples is None or num_examples > dataset.num_examples:
        num_examples = dataset.num_examples
    stream = fuel.streams.DataStream.default_stream(
        dataset,
        iteration_scheme=fuel.schemes.ShuffledScheme(num_examples, batch_size))
    ds = SampleDrops2(stream, drop_prob, hidden_dim,
                      for_evaluation, permutation)
    ds.sources = ('x', 'y', 'drops')
    return ds


class SampleDrops2(Transformer):
    def __init__(self, data_stream, drop_prob, hidden_dim,
                 is_for_test, permutation, **kwargs):
        super(SampleDrops2, self).__init__(
            data_stream, **kwargs)
        self.drop_prob = drop_prob
        self.hidden_dim = hidden_dim
        self.is_for_test = is_for_test
        self.produces_examples = False
        self.permutation = permutation

    def get_data(self, request=None):
        data = next(self.child_epoch_iterator)
        transformed_data = []
        transformed_data.append(
            np.swapaxes(data[0].reshape(data[0].shape[0], -1),
                        0, 1)[self.permutation, :, np.newaxis])
        transformed_data.append(data[1][:, 0])
        T, B, _ = transformed_data[0].shape
        if self.is_for_test:
            drops = np.ones((T, B, self.hidden_dim)) * self.drop_prob
        else:
            drops = np.random.binomial(n=1, p=self.drop_prob,
                                       size=(T, B, self.hidden_dim))
        transformed_data.append(drops.astype(floatX))
        return transformed_data


# PTB
_data_cache = dict()


def get_data(which_set):
    if which_set not in _data_cache:
        path = '/data/lisa/data/PennTreebankCorpus/char_level_penntree.npz'
        data = np.load(path)
        # put the entire thing on GPU in one-hot (takes
        # len(self.vocab) * len(self.data) * sizeof(floatX) bytes
        # which is about 1G for the training set and less for the
        # other sets)
        cudandarray = theano.sandbox.cuda.cuda_ndarray.cuda_ndarray.CudaNdarray
        # (doing it in numpy first because cudandarray doesn't accept
        # lists of indices)
        one_hot_data = np.eye(len(data["vocab"]), dtype=theano.config.floatX)[data[which_set]]
        _data_cache[which_set] = cudandarray(one_hot_data)
    return _data_cache[which_set]


class PTB(fuel.datasets.Dataset):
    provides_sources = ('features',)
    example_iteration_scheme = None

    def __init__(self, which_set, length, augment=False):
        self.which_set = which_set
        self.length = length
        self.augment = augment
        self.data = get_data(which_set)
        self.num_examples = int(len(self.data) / self.length)
        if self.augment:
            # -1 so we have one self.length worth of room for augmentation
            self.num_examples -= 1
        super(PTB, self).__init__()

    def open(self):
        offset = 0
        if self.augment:
            # choose an offset to get some data augmentation by
            # not always chopping the examples at the same point.
            offset = np.random.randint(self.length)
        # none of this should copy
        data = self.data[offset:]
        # reshape to nonoverlapping examples
        data = (data[:self.num_examples * self.length]
                .reshape((self.num_examples, self.length, self.data.shape[1])))
        # return the data so we will get it as the "state" argument to get_data
        return data

    def get_data(self, state, request):
        if isinstance(request, (tuple, list)):
            request = np.array(request, dtype=np.int64)
            return (state.take(request, 0),)
        return (state[request],)


class SampleDropsPTB(Transformer):
    def __init__(self, data_stream, drop_prob_s, drop_prob_c, hidden_dim,
                 is_for_test, **kwargs):
        super(SampleDropsPTB, self).__init__(
            data_stream, **kwargs)
        self.drop_prob_s = drop_prob_s
        self.drop_prob_c = drop_prob_c
        self.hidden_dim = hidden_dim
        self.is_for_test = is_for_test
        self.produces_examples = False

    def get_data(self, request=None):
        data = next(self.child_epoch_iterator)
        transformed_data = []
        # Now it is: T x B x F
        transformed_data.append(np.swapaxes(data[0], 0, 1))
        T, B, _ = transformed_data[0].shape
        if self.is_for_test:
            drops_s = np.ones((T, B, 1)) * self.drop_prob_s
        else:
            drops_s = np.random.binomial(n=1, p=self.drop_prob_s,
                                         size=(T, B, 1))

        if self.is_for_test:
            drops_c = np.ones((T, B, 1)) * self.drop_prob_s
        else:
            drops_c = np.random.binomial(n=1, p=self.drop_prob_c,
                                         size=(T, B, 1))
        drops = np.concatenate((drops_s, drops_c), axis=2)
        transformed_data.append(drops.astype(floatX))
        return transformed_data


def get_ptb_stream(which_set, batch_size, length, drop_prob_s, drop_prob_c,
                   hidden_dim, for_evaluation, num_examples=None,
                   augment=False):
    dataset = PTB(which_set, length=length, augment=augment)
    if num_examples is None or num_examples > dataset.num_examples:
        num_examples = dataset.num_examples
    stream = fuel.streams.DataStream.default_stream(
        dataset,
        iteration_scheme=fuel.schemes.ShuffledScheme(num_examples, batch_size))
    ds = SampleDropsPTB(stream, drop_prob_s, drop_prob_c, hidden_dim,
                        for_evaluation)
    ds.sources = ('x', 'drops')
    return ds

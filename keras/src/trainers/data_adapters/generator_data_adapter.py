import itertools

from keras.src import tree
from keras.src.trainers.data_adapters import data_adapter_utils
from keras.src.trainers.data_adapters.data_adapter import DataAdapter


class GeneratorDataAdapter(DataAdapter):
    """Adapter for Python generators."""

    def __init__(self, generator):
        first_batches, generator = peek_and_restore(generator)
        self.generator = generator
        self._first_batches = first_batches
        self._output_signature = None
        if not isinstance(first_batches[0], tuple):
            raise ValueError(
                "When passing a Python generator to a Keras model, "
                "the generator must return a tuple, either "
                "(input,) or (inputs, targets) or "
                "(inputs, targets, sample_weights). "
                f"Received: {first_batches[0]}"
            )

    def get_numpy_iterator(self):
        return data_adapter_utils.get_numpy_iterator(self.generator)

    def get_jax_iterator(self):
        from keras.src.backend.jax.core import convert_to_tensor

        def convert_to_jax(x):
            if data_adapter_utils.is_scipy_sparse(x):
                return data_adapter_utils.scipy_sparse_to_jax_sparse(x)
            elif data_adapter_utils.is_tensorflow_sparse(x):
                return data_adapter_utils.tf_sparse_to_jax_sparse(x)
            return convert_to_tensor(x)

        for batch in self.generator:
            yield tree.map_structure(convert_to_jax, batch)

    def get_tf_dataset(self):
        from keras.src.utils.module_utils import tensorflow as tf

        def convert_to_tf(x):
            if data_adapter_utils.is_scipy_sparse(x):
                x = data_adapter_utils.scipy_sparse_to_tf_sparse(x)
            elif data_adapter_utils.is_jax_sparse(x):
                x = data_adapter_utils.jax_sparse_to_tf_sparse(x)
            return x

        def get_tf_iterator():
            for batch in self.generator:
                batch = tree.map_structure(convert_to_tf, batch)
                yield batch

        if self._output_signature is None:
            self._output_signature = data_adapter_utils.get_tensor_spec(
                self._first_batches
            )
        ds = tf.data.Dataset.from_generator(
            get_tf_iterator,
            output_signature=self._output_signature,
        )
        ds = ds.prefetch(tf.data.AUTOTUNE)
        return ds

    def get_torch_dataloader(self):
        return data_adapter_utils.get_torch_dataloader(self.generator)

    @property
    def num_batches(self):
        return None

    @property
    def batch_size(self):
        return None


def peek_and_restore(generator):
    batches = list(
        itertools.islice(
            generator, data_adapter_utils.NUM_BATCHES_FOR_TENSOR_SPEC
        )
    )
    return batches, itertools.chain(batches, generator)

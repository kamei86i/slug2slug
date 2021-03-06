import os

from tensor2tensor.data_generators import problem
from tensor2tensor.data_generators import text_problems
from tensor2tensor.models import transformer
from tensor2tensor.models import lstm
from tensor2tensor.utils import registry

import config


@registry.register_hparams
def transformer_lang_gen():
    hparams = transformer.transformer_base()

    hparams.num_hidden_layers = 2
    hparams.hidden_size = 256
    hparams.filter_size = 512
    hparams.num_heads = 8
    hparams.attention_dropout = 0.6
    hparams.layer_prepostprocess_dropout = 0.6
    hparams.learning_rate = 0.05
    # hparams.batch_size = 64             # default: 4096
    hparams.max_input_seq_length = 50
    hparams.max_target_seq_length = 60
    # hparams.min_length_bucket = 10      # default: 0

    return hparams


@registry.register_hparams
def lstm_lang_gen():
    hparams = lstm.lstm_bahdanau_attention()

    hparams.num_hidden_layers = 2
    hparams.hidden_size = 256
    hparams.attention_layer_size = 256
    hparams.attention_dropout = 0.8
    hparams.layer_prepostprocess_dropout = 0.8
    hparams.learning_rate = 0.05
    # hparams.batch_size = 64             # default: 4096
    # hparams.max_input_seq_length = 50
    # hparams.max_target_seq_length = 60
    # hparams.min_length_bucket = 10      # default: 0

    return hparams


@registry.register_problem
class LangGen(text_problems.Text2TextProblem):
    """Generate a natural language utterance from a structured meaning representation (MR)."""

    @property
    def vocab_type(self):
        # return text_problems.VocabType.SUBWORD
        return text_problems.VocabType.TOKEN

    @property
    def oov_token(self):
        return 'UNK'

    # @property
    # def approx_vocab_size(self):
    #     return 2**12

    @property
    def is_generate_per_split(self):
        # If False, generate_data will shard the data into TRAIN and EVAL for us
        return True

    @property
    def dataset_splits(self):
        return [{
            'split': problem.DatasetSplit.TRAIN,
            'shards': 10,
        }, {
            'split': problem.DatasetSplit.EVAL,
            'shards': 1,
        }]

    def generate_samples(self, data_dir, tmp_dir, dataset_split):
        training_source_file = os.path.join(config.DATA_DIR, 'training_source.txt')
        training_target_file = os.path.join(config.DATA_DIR, 'training_target.txt')
        dev_source_file = os.path.join(config.DATA_DIR, 'dev_source.txt')
        dev_target_file = os.path.join(config.DATA_DIR, 'dev_target.txt')

        train = dataset_split == problem.DatasetSplit.TRAIN
        source_file = (training_source_file if train else dev_source_file)
        target_file = (training_target_file if train else dev_target_file)

        return text_problems.text2text_txt_iterator(source_file, target_file)

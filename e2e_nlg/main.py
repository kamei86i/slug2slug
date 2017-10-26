import argparse
import sys
import os
import io
import json
import platform
import pandas as pd
import numpy as np

import data_loader
import postprocessing


def main():
    parser = argparse.ArgumentParser(description='Perform a specific task (e.g. training, testing, prediction) with the defined model.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--train', nargs=2, help='takes as arguments the paths to the trainset and the devset')
    group.add_argument('--test', nargs=1, help='takes as argument the path to the testset')
    group.add_argument('--predict', nargs=1, help='takes as argument the path to the testset')
    group.add_argument('--beam_dump', nargs=1, help='takes as argument the path to the testset')

    args = parser.parse_args()

    if args.train is not None:
        if not os.path.isfile(args.train[0]) or not os.path.isfile(args.train[1]):
            print('Error: invalid file path.')
        else:
            train(args.train[0], args.train[1])
    elif args.test is not None:
        if not os.path.isfile(args.test[0]):
            print('Error: invalid file path.')
        else:
            test(args.test[0], predict_only=False)
    elif args.predict is not None:
        if not os.path.isfile(args.predict[0]):
            print('Error: invalid file path.')
        else:
            test(args.predict[0], predict_only=True)
    elif args.beam_dump is not None:
        if not os.path.isfile(args.beam_dump[0]):
            print('Error: invalid file path.')
        else:
            postprocessing.get_utterances_from_beam(args.beam_dump[0])
    else:
        print('Usage:\n')
        print('main.py')
        print('\t--train [path_to_trainset] [path_to_devset]')
        print('\t--test [path_to_testset]')
        print('\t--predict [path_to_testset]')
        print('\t--beam_dump [path_to_beams]')



def train(data_trainset, data_devset):
    training_source_file = 'data/training_source.txt'
    training_target_file = 'data/training_target.txt'
    dev_source_file = 'data/dev_source.txt'
    dev_target_file = 'data/dev_target.txt'
    vocab_source_file = 'data/vocab_source.txt'
    vocab_target_file = 'data/vocab_target.txt'

    print('Loading training data...', end=' ')
    sys.stdout.flush()

    if not os.path.isfile(training_source_file) or \
            not os.path.isfile(training_target_file) or \
            not os.path.isfile(dev_source_file) or \
            not os.path.isfile(dev_target_file):
        data_loader.load_training_data(data_trainset, data_devset, input_concat=False)

    print('DONE')
    print('Generating vocabulary...', end=' ')
    sys.stdout.flush()

    if not os.path.isfile(vocab_source_file) or not os.path.isfile(vocab_target_file):
        vocab_generator_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin/tools/generate_vocab.py')
        
        os.system('python ' + vocab_generator_path + ' < ' + training_source_file + ' > ' + vocab_source_file)
        os.system('python ' + vocab_generator_path + ' < ' + training_target_file + ' > ' + vocab_target_file)

    print('DONE')
    print('Training...')
    sys.stdout.flush()

    os.system('bash training_script.sh')

    print('DONE')


def test(data_testset, predict_only=True):
    test_source_file = 'data/test_source_dict.json'
    test_target_file = 'data/test_target.txt'
    vocab_file = 'data/vocab_proper_nouns.txt'
    predictions_file = 'predictions/predictions.txt'
    predictions_final_file = 'predictions/predictions_final.txt'
    predictions_reduced_file = 'metrics/predictions_reduced.txt'

    print('Loading test data...', end=' ')
    sys.stdout.flush()

    data_loader.load_test_data(data_testset, input_concat=False)
        
    print('DONE')
    print('Evaluating...')
    sys.stdout.flush()

    os.system('bash test_script.sh')

    with io.open(predictions_file, 'r', encoding='utf8') as f_predictions:
        with io.open(test_source_file, 'r', encoding='utf8') as f_test_source:
            with io.open(predictions_final_file, 'w', encoding='utf8') as f_predictions_final:
                mrs = json.load(f_test_source)
                predictions = f_predictions.read().splitlines()
                predictions_final = postprocessing.finalize_utterances(predictions, mrs)

                for prediction in predictions_final:
                    f_predictions_final.write(prediction + '\n')

                if not predict_only:
                    # create a file with a single prediction for each group of the same MRs
                    data_frame_test = pd.read_csv('data/testset.csv', header=0, encoding='utf8')
                    test_mrs = data_frame_test.mr.tolist()

                    with io.open(predictions_reduced_file, 'w', encoding='utf8') as f_predictions_reduced:
                        for i in range(len(test_mrs)):
                            if i == 0 or test_mrs[i] != test_mrs[i - 1]:
                                f_predictions_reduced.write(predictions_final[i] + '\n')

    if not predict_only:
        os.system('perl ../bin/tools/multi-bleu.perl ' + test_target_file + ' < ' + predictions_final_file)

    print('DONE')


if __name__ == "__main__":
    sys.exit(int(main() or 0))

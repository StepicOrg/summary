import argparse
import json
import logging
import os.path
import pickle
import sys

import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from recognition.video.recognizers import VideoRecognitionNaive, VideoRecognitionPySceneDetect
from recognition.video.image_uploaders import ImageSaverLocal

logging.basicConfig(format='[%(asctime)s]%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def parse_arguments():
    parser = argparse.ArgumentParser(description='Synopsis creator')

    input_parser = parser.add_mutually_exclusive_group(required=True)

    input_parser.add_argument('-f', '--file',
                              help='Path to input video.')

    input_parser.add_argument('-d', '--dataset',
                              help='Path to directory with dataset.')

    parser.add_argument('-o', '--output',
                        help='Path to output.',
                        default='output')

    save_keyframes_parser = parser.add_mutually_exclusive_group(required=False)
    save_keyframes_parser.add_argument('--save-keyframes', dest='save_keyframes', action='store_true')
    save_keyframes_parser.add_argument('--no-save-keyframes', dest='save_keyframes', action='store_false')
    parser.set_defaults(save_keyframes=True)

    args = parser.parse_args()

    return args


def create_dirs_if_not_exist(dir_paths):
    for dir_path in dir_paths:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

def process_one_file(filepath, save_keyframes, output):
    logger.info(filepath)
    naive_image_saver = None
    pyscene_image_saver = None
    if save_keyframes:
        naive_output_path = '{}/naive/{}.out'.format(output, os.path.basename(filepath))
        pyscene_output_path = '{}/pyscene/{}.out'.format(output, os.path.basename(filepath))
        create_dirs_if_not_exist([naive_output_path, pyscene_output_path])
        naive_image_saver = ImageSaverLocal(naive_output_path)
        pyscene_image_saver = ImageSaverLocal(pyscene_output_path)

    vr_naive = VideoRecognitionNaive(filepath, naive_image_saver)
    vr_pyscene = VideoRecognitionPySceneDetect(filepath, pyscene_image_saver)

    logger.info('start vr_naive')
    naive_keyframes = vr_naive.get_keyframes()
    logger.info('start vr_pyscene')
    pyscene_keyframes = vr_pyscene.get_keyframes()

    if save_keyframes:
        vr_naive.save_keyframes(naive_keyframes)
        vr_pyscene.save_keyframes(pyscene_keyframes)

    return naive_keyframes, pyscene_keyframes

def get_stats(true_intervals, results):
    tps = []

    for interval in true_intervals:
        for keyframe in results:
            if interval['start'] <= keyframe <= interval['end']:
                tps.append(keyframe)
                break

    precision = len(tps)/len(results) if results else 0
    recall = len(tps)/len(true_intervals) if true_intervals else 1
    n_missing = len(true_intervals) - len(tps)
    n_extra = len(results) - len(tps)

    stats = {'precision': precision, 'recall': recall, 'n_missing': n_missing, 'n_extra': n_extra}
    logger.info(stats)
    return stats


def plot_results(results, output):
    n_videos = len(results)
    n_recognizers = len(results[0]['stats_by_recognizers'])
    ind = [1, 2, 3, 4]
    tick_label = ['precision', 'recall', 'n_missing', 'n_extra']
    f, axarr = plt.subplots(n_recognizers, n_videos, figsize=(20, 10))
    for i, result in enumerate(results):
        max_n = max(list(map(lambda item: max(item['stats']['n_missing'], item['stats']['n_extra']),
                             result['stats_by_recognizers'])))
        for j, recognizer_stat in enumerate(result['stats_by_recognizers']):
            axarr[j, i].bar(ind[:2], [recognizer_stat['stats']['precision'], recognizer_stat['stats']['recall']], color='g')
            axarr[j, i].set_xticks(ind)
            axarr[j, i].set_xticklabels(tick_label)
            axarr[j, i].set_ylim(0, 1)
            axarr[j, i].tick_params('y', colors='g')

            if j == 0:
                axarr[j, i].set_title(result['name'], fontsize=14)
            if i == 0:
                axarr[j, i].set_ylabel(recognizer_stat['recognizer_name'], fontsize=14)

            ax2 = axarr[j, i].twinx()
            ax2.bar(ind[2:], [recognizer_stat['stats']['n_missing'], recognizer_stat['stats']['n_extra']], color='r')
            ax2.set_ylim(0, max_n)
            ax2.tick_params('y', colors='r')

    plt.tight_layout()
    plt.savefig('{}/result.png'.format(output))

def main():
    args = parse_arguments()

    if args.file:
        process_one_file(args.file, args.save_keyframes, args.output)
        return

    if args.dataset:
        dataset_path = args.dataset
        data_path = '{}/data.json'.format(dataset_path)
        with open(data_path, 'r') as f:
            data = json.load(f)

        results = []
        for video in data['videos']:
            video_path = '{}/{}'.format(dataset_path, video['name'])

            naive_keyframes, pyscene_keyframes = process_one_file(video_path, args.save_keyframes, args.output)
            naive_stats = get_stats(video['intervals'], naive_keyframes)
            pyscene_stats = get_stats(video['intervals'], pyscene_keyframes)
            results.append(
                {
                    'name': video['name'],
                    'intervals': video['intervals'],
                    'stats_by_recognizers': [
                        {
                            'recognizer_name': 'naive',
                            'keyframes': naive_keyframes,
                            'stats': naive_stats
                        },
                        {
                            'recognizer_name': 'pyscene',
                            'keyframes': pyscene_keyframes,
                            'stats': pyscene_stats
                        }
                    ]
                })
        logger.info(results)

        with open('{}/result.json'.format(args.output), 'w') as f:
            json.dump(results, f)

if __name__ == '__main__':
    main()

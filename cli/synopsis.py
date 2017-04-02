import argparse
import os.path
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from recognition.video.recognizers import VideoRecognitionNaive, VideoRecognitionPySceneDetect
from recognition.video.image_uploaders import ImageSaverLocal

def parse_arguments():
    parser = argparse.ArgumentParser(description='Synopsis creator')

    parser.add_argument('-f', '--file',
                        help='[REQUIRED] Path to input video.',
                        type=argparse.FileType('r'),
                        required=True)

    parser.add_argument('-o', '--output',
                        help='Path to output.',
                        default='output')

    args = parser.parse_args()

    return args


def create_dirs_if_not_exist(dir_paths):
    for dir_path in dir_paths:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

def main():
    args = parse_arguments()

    naive_output_path = '{}/naive'.format(args.output)
    pyscene_output_path = '{}/pyscene'.format(args.output)
    create_dirs_if_not_exist([naive_output_path, pyscene_output_path])

    vr_naive = VideoRecognitionNaive(args.file.name, ImageSaverLocal(naive_output_path))
    vr_pyscene = VideoRecognitionPySceneDetect(args.file.name, ImageSaverLocal(pyscene_output_path))

    vr_naive.get_keyframes_src_with_timestamp()
    vr_pyscene.get_keyframes_src_with_timestamp()

if __name__ == '__main__':
    main()

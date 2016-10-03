import os
import logging
import tempfile
import argparse
from collections import namedtuple

import requests
import subprocess
from requests.auth import HTTPBasicAuth

from recognize import VideoRecognition, AudioRecognition
from constants import (VIDEOS_DOWNLOAD_CHUNK_SIZE, VIDEOS_DOWNLOAD_MAX_SIZE, FFMPEG_EXTRACT_AUDIO,
                       IS_FRAME, IS_TEXT, STEPIK_BASE_URL)
from exceptions import CreateSynopsisError

logger = logging.getLogger(__name__)


def merge_audio_and_video(keyframes, recognized_audio):
    frames_ptr = 0
    audio_ptr = 0

    content = []

    last_time = 0
    for keyframe in keyframes:
        last_time, keyframe[1] = keyframe[1], last_time

    while frames_ptr < len(keyframes) and audio_ptr < len(recognized_audio):
        if keyframes[frames_ptr][1] <= recognized_audio[audio_ptr][0]:
            content.append({IS_FRAME: keyframes[frames_ptr][0]})
            frames_ptr += 1
        else:
            content.append({IS_TEXT: recognized_audio[audio_ptr][2]})
            audio_ptr += 1
    while frames_ptr < len(keyframes):
        content.append({IS_FRAME: keyframes[frames_ptr][0]})
        frames_ptr += 1
    while audio_ptr < len(recognized_audio):
        content.append({IS_TEXT: recognized_audio[audio_ptr][2]})
        audio_ptr += 1
    return content


def parse_arguments():
    parser = argparse.ArgumentParser(description='Stepik synopsis creator')

    parser.add_argument('-c', '--client_id',
                        help='your client_id from https://stepic.org/oauth2/applications/',
                        required=True)

    parser.add_argument('-s', '--client_secret',
                        help='your client_secret from https://stepic.org/oauth2/applications/',
                        required=True)

    parser.add_argument('-i', '--lesson_id',
                        help='lesson id',
                        required=True)

    parser.add_argument('-u', '--upload_care_pub_key',
                        help='upload care pub key',
                        required=True)

    parser.add_argument('-y', '--yandex_speech_kit_key',
                        help='yandex speech kit key',
                        required=True)

    parser.add_argument('-n', '--step_number',
                        help='step number starts from 1 (if not set then it will download the whole lesson)',
                        type=int,
                        default=None)

    args = parser.parse_args()

    return args


def make_synopsis_from_video(video, upload_care_pub_key, yandex_speech_kit_key):
    with tempfile.TemporaryDirectory() as tmpdir:
        videofile = os.path.join(tmpdir, 'tmp.mp4')

        with open(videofile, 'wb') as f:
            response = requests.get(video['urls'][0]['url'], stream=True)
            if response.status_code != 200:
                raise CreateSynopsisError('Failed to download video, Status code: {status_code}, id = {id}'
                                          .format(status_code=response.status_code, id=video.id))
            size = 0
            for chunk in response.iter_content(VIDEOS_DOWNLOAD_CHUNK_SIZE):
                size += f.write(chunk)
                if size > VIDEOS_DOWNLOAD_MAX_SIZE:
                    raise CreateSynopsisError('Failed to download video, too big video file, id = {id}'
                                              .format(id=video['id']))

            out_audio = os.path.join(tmpdir, 'tmp_audio.wav')
            command = FFMPEG_EXTRACT_AUDIO.format(input_video=videofile,
                                                  output_audio=out_audio)
            if not run_shell_command(command):
                raise CreateSynopsisError(command)

            ar = AudioRecognition(out_audio, yandex_speech_kit_key)
            recognized_audio = ar.recognize()

            vr = VideoRecognition(videofile, upload_care_pub_key)
            keyframes_src_with_timestamp = vr.get_keyframes_src_with_timestamp()

            content = merge_audio_and_video(keyframes_src_with_timestamp,
                                            recognized_audio)

            return content


def run_shell_command(command, timeout=4):
    try:
        exitcode = subprocess.call(command, shell=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.exception('Failed to run shell command: "{command}" with timeout {timeout}'
                         .format(command=command, timeout=timeout))
        return False
    if exitcode != 0:
        logger.error('Failed to run shell command: "{command}" with exitcode {exitcode}'
                     .format(command=command, exitcode=exitcode))
        return False
    return True


Args = namedtuple('Args', ['client_id',
                           'client_secret',
                           'upload_care_pub_key',
                           'yandex_speech_kit_key',
                           'lesson_id',
                           'step_number'])


class StepikClient(object):
    def __init__(self, client_id, client_secret):
        auth = HTTPBasicAuth(client_id, client_secret)
        response = requests.post(url='{base_url}/oauth2/token/'.format(base_url=STEPIK_BASE_URL),
                                 data={'grant_type': 'client_credentials'},
                                 auth=auth)

        self.token = response.json()['access_token']
        self.session = requests.Session()
        self.session.headers.update({'Authorization': 'Bearer ' + self.token})

    def get_steps(self, lesson_id, step_number):
        response = self.session.get('{base_url}/api/lessons/{id}'.format(base_url=STEPIK_BASE_URL,
                                                                         id=lesson_id))

        if response.status_code != 200:
            raise CreateSynopsisError('Filed to get lessons page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))

        lesson_page = response.json()

        if len(lesson_page['lessons']) == 0:
            raise CreateSynopsisError('wrong lesson id')

        lesson = lesson_page['lessons'][0]

        if step_number and not (1 <= int(step_number) <= len(lesson['steps'])):
            CreateSynopsisError('step number not in [1, num_of_steps_in_lesson]')

        return [lesson['steps'][int(step_number) - 1]] if step_number else lesson['steps']

    def get_step_block(self, step_id):
        response = self.session.get('{base_url}/api/steps/{id}'.format(base_url=STEPIK_BASE_URL,
                                                                       id=step_id))
        if response.status_code != 200:
            raise CreateSynopsisError('Filed to get steps page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))
        return response.json()['steps'][0]['block']


def send_response(status, msg):
    logger.info('recognize result: status = {}, message = {}'.format(status, msg))

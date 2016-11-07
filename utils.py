import os
import logging
import tempfile
import argparse
from collections import namedtuple

import mwapi
import requests
import subprocess
from requests.auth import HTTPBasicAuth

import settings
from recognize import VideoRecognition, AudioRecognition
from constants import (VIDEOS_DOWNLOAD_CHUNK_SIZE, VIDEOS_DOWNLOAD_MAX_SIZE, FFMPEG_EXTRACT_AUDIO,
                       IS_FRAME, IS_TEXT, STEPIK_BASE_URL, WIKI_BASE_URL, WIKI_API_PATH, LESSON_PAGE_TITLE_TEMPLATE,
                       LESSON_PAGE_TEXT_TEMPLATE, STEP_PAGE_TITLE_TEMPLATE, STEP_PAGE_TEXT_TEMPLATE,
                       STEP_PAGE_SUMMARY_TEMPLATE, LESSON_PAGE_SUMMARY_TEMPLATE)
from exceptions import CreateSynopsisError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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


Args = namedtuple('Args', ['stepik_client_id',
                           'stepik_client_secret',
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

    def get_lesson_info(self, lesson_id, step_number):
        response = self.session.get('{base_url}/api/lessons/{id}'.format(base_url=STEPIK_BASE_URL,
                                                                         id=lesson_id))

        if response.status_code != 200:
            raise CreateSynopsisError('Filed to get lessons page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))

        lesson_page = response.json()

        if len(lesson_page['lessons']) == 0:
            raise CreateSynopsisError('wrong lesson id')

        lesson = lesson_page['lessons'][0]
        title = lesson['title']

        if step_number and not (1 <= int(step_number) <= len(lesson['steps'])):
            CreateSynopsisError('step number not in [1, num_of_steps_in_lesson]')

        steps = [lesson['steps'][int(step_number) - 1]] if step_number else lesson['steps']
        # TODO: exclude steps that already have a synopsis (by StepikAPI)
        # TODO: get lesson_wiki_url (by StepikAPI)
        lesson_wiki_url = None
        return title, steps, lesson_wiki_url

    def get_step_block(self, step_id):
        response = self.session.get('{base_url}/api/steps/{id}'.format(base_url=STEPIK_BASE_URL,
                                                                       id=step_id))
        if response.status_code != 200:
            raise CreateSynopsisError('Filed to get steps page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))
        return response.json()['steps'][0]['block']


class WikiClient(object):
    def __init__(self, login, password):
        self.session = mwapi.Session(host=WIKI_BASE_URL, api_path=WIKI_API_PATH)
        self.session.login(login, password)
        self.token = self.session.get(action='query', meta='tokens')['query']['tokens']['csrftoken']

    def get_url_by_page_id(self, page_id):
        response = self.session.get(action='query', prop='info', pageids=page_id, inprop='url')
        url = response['query']['pages'][str(page_id)]['fullurl']
        return url

    def create_page_for_step(self, step_id, position, content, lesson_title, lesson_id):
        lesson_page_title = LESSON_PAGE_TITLE_TEMPLATE.format(title=lesson_title, id=lesson_id)
        text = STEP_PAGE_TEXT_TEMPLATE.format(content=content, lesson=lesson_page_title)
        title = STEP_PAGE_TITLE_TEMPLATE.format(position=position, id=step_id)
        summary = STEP_PAGE_SUMMARY_TEMPLATE.format(id=step_id)

        response = self.session.post(action='edit',
                                     title=title,
                                     section=0,
                                     summary=summary,
                                     text=text,
                                     token=self.token)

        return self._extract_url_from_response(response)

    def create_page_for_lesson(self, lesson_title, lesson_id):
        title = LESSON_PAGE_TITLE_TEMPLATE.format(title=lesson_title, id=lesson_id)
        text = LESSON_PAGE_TEXT_TEMPLATE.format(stepik_base=STEPIK_BASE_URL,
                                                title=lesson_title,
                                                id=lesson_id)
        summary = LESSON_PAGE_SUMMARY_TEMPLATE.format(id=lesson_id)

        response = self.session.post(action='edit',
                                     title=title,
                                     section=0,
                                     summary=summary,
                                     text=text,
                                     token=self.token)

        return self._extract_url_from_response(response)

    def _extract_url_from_response(self, response):
        try:
            if response['edit']['result'] == 'Success':
                page_id = response['edit']['pageid']
                url = self.get_url_by_page_id(page_id)
                return url
            else:
                msg = "Cant extract url from response, response = {}".format(response)
                raise CreateSynopsisError(msg)
        except KeyError:
            msg = "Cant extract url from response, response = {}".format(response)
            logger.exception(msg)
            raise CreateSynopsisError(msg)


def send_response(status, result):
    logger.info('recognize result: status = {}, message = {}'.format(status, result))
    if status:
        wiki_client = WikiClient(settings.WIKI_LOGIN, settings.WIKI_PASSWORD)
        lesson_id = result['lesson_id']
        lesson_wiki_url = (
            result['lesson_wiki_url'] or wiki_client.create_page_for_lesson(result['lesson_title'],
                                                                            result['lesson_id']))
        response = {'lesson_id': lesson_id,
                    'lesson_wiki_url': lesson_wiki_url,
                    'step_wiki_urls': []}

        lesson_title = result['lesson_title']
        for step_id, position, content in result['synopsis_by_steps']:
            url = wiki_client.create_page_for_step(step_id, position, content, lesson_title, lesson_id)
            response['step_wiki_urls'].append({step_id: url})

        # TODO: send result to Stepik
        logger.info(response)

import argparse
import json
import logging
import os
import subprocess
import tempfile

import mwapi
import pypandoc
import requests
from mwapi.errors import LoginError, APIError
from requests import RequestException
from requests.auth import HTTPBasicAuth

import settings
from constants import (VIDEOS_DOWNLOAD_CHUNK_SIZE, VIDEOS_DOWNLOAD_MAX_SIZE, FFMPEG_EXTRACT_AUDIO,
                       LESSON_PAGE_TITLE_TEMPLATE, LESSON_PAGE_TEXT_TEMPLATE,
                       STEP_PAGE_TITLE_TEMPLATE, STEP_PAGE_TEXT_TEMPLATE,
                       STEP_PAGE_SUMMARY_TEMPLATE, LESSON_PAGE_SUMMARY_TEMPLATE, ContentType, SynopsisState)
from exceptions import CreateSynopsisError
from recognize import VideoRecognition, AudioRecognition

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
            content.append(
                {
                    'type': ContentType.IMG,
                    'content': keyframes[frames_ptr][0]
                }
            )
            frames_ptr += 1
        else:
            content.append(
                {
                    'type': ContentType.TEXT,
                    'content': recognized_audio[audio_ptr][2]
                }
            )
            audio_ptr += 1

    while frames_ptr < len(keyframes):
        content.append(
            {
                'type': ContentType.IMG,
                'content': keyframes[frames_ptr][0]
            }
        )
        frames_ptr += 1

    while audio_ptr < len(recognized_audio):
        content.append(
            {
                'type': ContentType.TEXT,
                'content': recognized_audio[audio_ptr][2]
            }
        )
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


class StepikClient(object):
    def __init__(self, client_id, client_secret):
        auth = HTTPBasicAuth(client_id, client_secret)
        response = requests.post(url='{base_url}/oauth2/token/'.format(base_url=settings.STEPIK_BASE_URL),
                                 data={'grant_type': 'client_credentials'},
                                 auth=auth)

        self.token = response.json()['access_token']
        self.session = requests.Session()
        self.session.headers.update({'Authorization': 'Bearer ' + self.token})

    def get_lesson_info(self, lesson_id):
        response = self.session.get('{base_url}/api/lessons/{id}'.format(base_url=settings.STEPIK_BASE_URL,
                                                                         id=lesson_id))

        if response.status_code != 200:
            raise CreateSynopsisError('Filed to get lessons page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))

        lessons_page = response.json()
        if len(lessons_page['lessons']) == 0:
            raise CreateSynopsisError('wrong lesson id')

        return lessons_page['lessons'][0]

    def get_step_info(self, step_id):
        response = self.session.get('{base_url}/api/steps/{id}'.format(base_url=settings.STEPIK_BASE_URL,
                                                                       id=step_id))
        if response.status_code != 200:
            raise CreateSynopsisError('Filed to get steps page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))

        steps_page = response.json()
        if len(steps_page['steps']) == 0:
            raise CreateSynopsisError('wrong step id')

        return steps_page['steps'][0]

    def get_synopsis_step_info(self, step_info):
        if step_info['synopsis'] is None:
            raise CreateSynopsisError('No synopsis id for getting synopsis info')

        response = self.session.get('{base_url}/api/synopsis-steps/{pk}'.format(base_url=settings.STEPIK_BASE_URL,
                                                                                pk=step_info['synopsis']))
        if response.status_code != 200:
            raise CreateSynopsisError('Filed to get synopsis_step page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))

        synopsis_step_page = response.json()
        if len(synopsis_step_page['synopsis-steps']) == 0:
            raise CreateSynopsisError('wrong synopsis_step id')

        return synopsis_step_page['synopsis-steps'][0]

    def get_synopsis_lesson_info(self, synopsis_lesson_id):
        response = self.session.get('{base_url}/api/synopsis-lessons/{pk}'.format(base_url=settings.STEPIK_BASE_URL,
                                                                                  pk=synopsis_lesson_id))
        if response.status_code != 200:
            raise CreateSynopsisError('Filed to get synopsis_lesson page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))

        synopsis_lesson_page = response.json()
        if len(synopsis_lesson_page['synopsis-lessons']) == 0:
            raise CreateSynopsisError('wrong synopsis_lesson id')

        return synopsis_lesson_page['synopsis-lessons'][0]

    def get_lesson_by_step(self, step_id):
        step = self.get_step_info(step_id)
        return step['lesson']

    def get_step_block(self, step_id):
        step = self.get_step_info(step_id)
        return step['block']

    def get_lesson_wiki_url(self, lesson_info):
        if not lesson_info['synopsis']:
            return None

        synopsis = self.get_synopsis_lesson_info(lesson_info['synopsis'])
        return synopsis['url']

    def post_results(self, status, result, request=None):
        if status:
            for synopsis_lesson in result['synopsis_lessons']:
                if synopsis_lesson['pk']:
                    self._update_synopsis_lesson(synopsis_lesson)
                else:
                    self._create_synopsis_lesson(synopsis_lesson)

            for synopsis_step in result['synopsis_steps']:
                self._update_synopsis_step(synopsis_step)

    def _create_synopsis_lesson(self, synopsis_lesson):
        response = self.session.post(
            url='{base_url}/api/synopsis-lessons'.format(base_url=settings.STEPIK_BASE_URL),
            data=json.dumps(
                {
                    'synopsis-lessons':
                        {
                            'lesson': synopsis_lesson['lesson_id'],
                            'url': synopsis_lesson['url']
                        }
                }
            ),
            headers={'Content-Type': 'application/json'}
        )
        logger.info('{}; {}'.format(response.status_code, response.content))

    def _update_synopsis_lesson(self, synopsis_lesson):
        response = self.session.put(
            url='{base_url}/api/synopsis-lessons/{pk}'.format(base_url=settings.STEPIK_BASE_URL,
                                                              pk=synopsis_lesson['pk']),
            data=json.dumps(
                {
                    'synopsis-lessons':
                        {
                            'lesson': synopsis_lesson['lesson_id'],
                            'url': synopsis_lesson['url']
                        }
                }
            ),
            headers={'Content-Type': 'application/json'}
        )
        logger.info('{}; {}'.format(response.status_code, response.content))

    def _update_synopsis_step(self, synopsis_step):
        synopsis_info = synopsis_step['synopsis_info']
        response = self.session.put(
            url='{base_url}/api/synopsis-steps/{pk}'.format(base_url=settings.STEPIK_BASE_URL,
                                                            pk=synopsis_info['id']),
            data=json.dumps(
                {
                    'synopsis-steps':
                        {
                            'step': synopsis_info['step'],
                            'state': SynopsisState.EXIST,
                            'url': synopsis_step['url'],
                            'requester': synopsis_info['requester']
                        }
                }
            ),
            headers={'Content-Type': 'application/json'}
        )
        logger.info('{}; {}'.format(response.status_code, response.content))


class WikiClient(object):
    def __init__(self, login, password):
        self.session = mwapi.Session(host=settings.WIKI_BASE_URL, api_path=settings.WIKI_API_PATH)
        try:
            self.session.login(login, password)
            self.token = self.session.get(action='query', meta='tokens')['query']['tokens']['csrftoken']
        except (LoginError, APIError, RequestException) as e:
            msg = 'cant initialize WikiClient'
            logger.exception(msg)
            raise CreateSynopsisError('msg={}; error={}'.format(msg, e))

    def get_url_by_page_id(self, page_id):
        try:
            response = self.session.get(action='query', prop='info', pageids=page_id, inprop='url')
        except (APIError, RequestException) as e:
            raise CreateSynopsisError(str(e))
        url = response['query']['pages'][str(page_id)]['fullurl']
        return url

    def get_url_by_page_title(self, title):
        try:
            response = self.session.post(action='query', titles=title)
        except (APIError, RequestException) as e:
            raise CreateSynopsisError(str(e))

        page_id = int(list(response['query']['pages'])[0])
        if page_id < 0:
            return None

        return self.get_url_by_page_id(page_id)

    def get_or_create_page_for_step(self, step_synopsis, lesson_title, lesson_id):
        content = self._prepare_content(step_synopsis['content'])
        lesson_page_title = LESSON_PAGE_TITLE_TEMPLATE.format(title=lesson_title, id=lesson_id)
        text = STEP_PAGE_TEXT_TEMPLATE.format(content=content, lesson=lesson_page_title)
        title = STEP_PAGE_TITLE_TEMPLATE.format(position=step_synopsis['position'], id=step_synopsis['step_id'])
        summary = STEP_PAGE_SUMMARY_TEMPLATE.format(id=step_synopsis['step_id'])

        page_url = self.get_url_by_page_title(title)
        if page_url:
            return page_url

        try:
            response = self.session.post(action='edit',
                                         title=title,
                                         section=0,
                                         summary=summary,
                                         text=text,
                                         token=self.token,
                                         createonly=True)
        except RequestException as e:
            raise CreateSynopsisError(str(e))
        except APIError:
            logger.exception('mwapi.errors.APIError: articleexists: - its OK')
            return self.get_url_by_page_title(title)

        return self._extract_url_from_response(response)

    def get_or_create_page_for_lesson(self, lesson_title, lesson_id):
        title = LESSON_PAGE_TITLE_TEMPLATE.format(title=lesson_title, id=lesson_id)
        text = LESSON_PAGE_TEXT_TEMPLATE.format(stepik_base=settings.STEPIK_BASE_URL,
                                                title=lesson_title,
                                                id=lesson_id)
        summary = LESSON_PAGE_SUMMARY_TEMPLATE.format(id=lesson_id)

        page_url = self.get_url_by_page_title(title)
        if page_url:
            return page_url

        try:
            response = self.session.post(action='edit',
                                         title=title,
                                         section=0,
                                         summary=summary,
                                         text=text,
                                         token=self.token,
                                         createonly=True)
        except RequestException as e:
            raise CreateSynopsisError(str(e))
        except APIError:
            logger.exception('mwapi.errors.APIError: articleexists: - its OK')
            return self.get_url_by_page_title(title)

        return self._extract_url_from_response(response)

    def _extract_url_from_response(self, response):
        if response['edit']['result'] == 'Success':
            page_id = response['edit']['pageid']
            url = self.get_url_by_page_id(page_id)
            return url
        else:
            raise CreateSynopsisError("Cant extract url from response, response = {}"
                                      .format(response))

    @staticmethod
    def _prepare_content(content):
        result = []
        for item in content:
            if item['type'] == ContentType.TEXT:
                result.append(pypandoc.convert_text(item['content'], format='html', to='mediawiki'))
            elif item['type'] == ContentType.IMG:
                result.append('<img width="50%" src="{}">'.format(item['content']))
        return '\n\n'.join(result)


def post_result_on_wiki(result):
    wiki_client = WikiClient(settings.WIKI_LOGIN, settings.WIKI_PASSWORD)
    lesson = result['lesson']
    lesson_wiki_url = wiki_client.get_or_create_page_for_lesson(lesson['title'],
                                                                lesson['lesson_id'])
    response = {
        'synopsis_lessons': [
            {
                'lesson_id': lesson['lesson_id'],
                'url': lesson_wiki_url
            },
        ],
        'synopsis_steps': []
    }

    lesson_title = lesson['title']
    for step_synopsis in result['synopsis_by_steps']:
        url = wiki_client.get_or_create_page_for_step(step_synopsis, lesson_title, lesson['lesson_id'])
        response['synopsis_steps'].append(
            {
                'step_id': step_synopsis['step_id'],
                'url': url
            }
        )

    logger.info(response)
    return response

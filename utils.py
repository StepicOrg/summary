import argparse
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
                       STEP_PAGE_SUMMARY_TEMPLATE, LESSON_PAGE_SUMMARY_TEMPLATE, ContentType,
                       SynopsisType, COURSE_PAGE_TITLE_TEMPLATE, COURSE_PAGE_TEXT_TEMPLATE,
                       COURSE_PAGE_SUMMARY_TEMPLATE)
from exceptions import CreateSynopsisError
from recognize import VideoRecognition, AudioRecognition

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

_stepik_client = None
_wiki_client = None


def get_stepik_client():
    global _stepik_client
    if _stepik_client is None:
        _stepik_client = StepikClient(client_id=settings.STEPIK_CLIENT_ID,
                                      client_secret=settings.STEPIK_CLIENT_SECRET)
    return _stepik_client


def get_wiki_client():
    global _wiki_client
    if _wiki_client is None:
        _wiki_client = WikiClient(settings.WIKI_LOGIN, settings.WIKI_PASSWORD)
    return _wiki_client


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

    def get_course(self, course_id):
        response = self.session.get('{base_url}/api/courses/{id}'.format(base_url=settings.STEPIK_BASE_URL,
                                                                         id=course_id))
        if not response:
            raise CreateSynopsisError('Failed to get courses page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))

        return response.json()['courses'][0]

    def get_lesson(self, lesson_id):
        response = self.session.get('{base_url}/api/lessons/{id}'.format(base_url=settings.STEPIK_BASE_URL,
                                                                         id=lesson_id))
        if not response:
            raise CreateSynopsisError('Failed to get lessons page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))

        return response.json()['lessons'][0]

    def get_lessons_by_course(self, course_id):
        lessons = []
        cur_page = 1
        while True:
            response = self.session.get('{base_url}/api/lessons?course={course_id}&page={page}'
                                        .format(base_url=settings.STEPIK_BASE_URL,
                                                course_id=course_id,
                                                page=cur_page))
            if not response:
                raise CreateSynopsisError('Failed to get lessons page from stepik, status code = {status_code}'
                                          .format(status_code=response.status_code))
            lessons.extend(response.json()['lessons'])

            if not response.json()['meta']['has_next']:
                return lessons

            cur_page += 1

    def get_step(self, step_id):
        response = self.session.get('{base_url}/api/steps/{id}'.format(base_url=settings.STEPIK_BASE_URL,
                                                                       id=step_id))
        if not response:
            raise CreateSynopsisError('Failed to get steps page from stepik, status code = {status_code}'
                                      .format(status_code=response.status_code))

        return response.json()['steps'][0]


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

    def get_or_create_page_for_step(self, lesson, step, content):
        lesson_page_title = LESSON_PAGE_TITLE_TEMPLATE.format(title=lesson['title'], id=lesson['id'])
        text = STEP_PAGE_TEXT_TEMPLATE.format(content=self._prepare_content(content), lesson=lesson_page_title)
        title = STEP_PAGE_TITLE_TEMPLATE.format(position=step['position'], id=step['id'])
        summary = STEP_PAGE_SUMMARY_TEMPLATE.format(id=step['id'])

        page_url = self._get_or_create_page(title, text, summary)
        logger.info('page for step (step_id = %s, page_url = %s)', step['id'], page_url)
        return page_url

    def get_or_create_page_for_lesson(self, lesson):
        title = LESSON_PAGE_TITLE_TEMPLATE.format(title=lesson['title'], id=lesson['id'])
        text = LESSON_PAGE_TEXT_TEMPLATE.format(stepik_base=settings.STEPIK_BASE_URL,
                                                title=lesson['title'],
                                                id=lesson['id'])
        summary = LESSON_PAGE_SUMMARY_TEMPLATE.format(id=lesson['id'])

        page_url = self._get_or_create_page(title, text, summary)
        logger.info('page for lesson (lesson_id = %s, page_url = %s)', lesson['id'], page_url)
        return page_url

    def get_or_create_page_for_course(self, course):
        title = COURSE_PAGE_TITLE_TEMPLATE.format(title=course['title'], id=course['id'])
        text = COURSE_PAGE_TEXT_TEMPLATE.format(stepik_base=settings.STEPIK_BASE_URL,
                                                title=course['title'],
                                                id=course['id'])
        summary = COURSE_PAGE_SUMMARY_TEMPLATE.format(id=course['id'])

        page_url = self._get_or_create_page(title, text, summary)
        logger.info('page for course (course_id = %s, page_url = %s)', course['id'], page_url)
        return page_url

    def is_page_for_step_exist(self, step):
        title = STEP_PAGE_TITLE_TEMPLATE.format(position=step['position'], id=step['id'])
        return self._is_page_with_title_exist(title)

    def add_text_to_page(self, page_title, text, summary):
        try:
            self.session.post(action='edit',
                              title=page_title,
                              summary=summary,
                              appendtext=text,
                              token=self.token,
                              nocreate=True)
        except Exception as e:
            raise CreateSynopsisError(str(e))

    def get_page_categories(self, page_title):
        try:
            response = self.session.get(action='query',
                                        titles=page_title,
                                        prop='categories')
            pages = response['query']['pages']
            categories = list(map(lambda item: item['title'], list(pages.values())[0].get('categories', [])))
            return categories
        except Exception as e:
            raise CreateSynopsisError(str(e))

    def _get_or_create_page(self, title, text, summary):
        if self._is_page_with_title_exist(title):
            return self._get_url_by_page_title(title)

        return self._create_page(title, text, summary)

    def _create_page(self, title, text, summary):
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
            return self._get_url_by_page_title(title)

        page_url = self._extract_url_from_response(response)
        logger.info('created page with url %s', page_url)
        return page_url

    def _get_url_by_page_id(self, page_id):
        try:
            response = self.session.get(action='query', prop='info', pageids=page_id, inprop='url')
        except (APIError, RequestException) as e:
            raise CreateSynopsisError(str(e))
        url = response['query']['pages'][str(page_id)]['fullurl']
        return url

    def _get_url_by_page_title(self, title):
        try:
            response = self.session.post(action='query', titles=title)
        except (APIError, RequestException) as e:
            raise CreateSynopsisError(str(e))

        page_id = int(list(response['query']['pages'])[0])
        if page_id < 0:
            return None

        return self._get_url_by_page_id(page_id)

    def _extract_url_from_response(self, response):
        if response['edit']['result'] == 'Success':
            page_id = response['edit']['pageid']
            url = self._get_url_by_page_id(page_id)
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

    def _is_page_with_title_exist(self, title):
        return self._get_url_by_page_title(title) is not None


def save_synopsis_to_wiki(synopsis):
    wiki_client = get_wiki_client()
    lesson = synopsis['lesson']
    lesson_wiki_url = wiki_client.get_or_create_page_for_lesson(lesson)
    response = {
        'wiki_url_lesson':
            {
                'lesson': lesson,
                'url': lesson_wiki_url
            },
        'wiki_url_steps': []
    }

    for step_with_content in synopsis['steps']:
        step_wiki_url = wiki_client.get_or_create_page_for_step(lesson=lesson,
                                                                step=step_with_content['step'],
                                                                content=step_with_content['content'])
        response['wiki_url_steps'].append(
            {
                'step': step_with_content['step'],
                'url': step_wiki_url
            }
        )

    logger.info('wiki urls %s', response)
    return response


def add_lesson_to_course(course, lesson):
    wiki_client = get_wiki_client()

    course_url = wiki_client.get_or_create_page_for_course(course)
    lesson_url = wiki_client.get_or_create_page_for_lesson(lesson)

    logger.info('add lesson {lesson} to course {course}'.format(lesson=lesson_url, course=course_url))

    course_page_title = COURSE_PAGE_TITLE_TEMPLATE.format(title=course['title'], id=course['id'])
    lesson_page_title = LESSON_PAGE_TITLE_TEMPLATE.format(title=lesson['title'], id=lesson['id'])

    course_link = '[[{}]]'.format(course_page_title)
    lesson_categories = wiki_client.get_page_categories(lesson_page_title)
    if course_page_title not in lesson_categories:
        wiki_client.add_text_to_page(lesson_page_title, course_link, 'add lesson to course')


def validate_synopsis_request(data):
    if not len(data) == 2:
        return False

    if not data.get('type') in SynopsisType.ALL_TYPES:
        return False

    if not isinstance(data.get('pk'), int):
        return False

    if data['pk'] <= 0:
        return False

    return True

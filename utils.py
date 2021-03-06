import argparse
import logging
import os
import re
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
                       STEP_PAGE_SUMMARY_TEMPLATE, LESSON_PAGE_SUMMARY_TEMPLATE,
                       SynopsisType, COURSE_PAGE_TITLE_TEMPLATE, COURSE_PAGE_TEXT_TEMPLATE,
                       COURSE_PAGE_SUMMARY_TEMPLATE, SECTION_PAGE_TITLE_TEMPLATE, SECTION_PAGE_TEXT_TEMPLATE,
                       SECTION_PAGE_SUMMARY_TEMPLATE, SINGLE_DOLLAR_TO_MATH_PATTERN, SINGLE_DOLLAR_TO_MATH_REPLACE,
                       DOUBLE_DOLLAR_TO_MATH_PATTERN, DOUBLE_DOLLAR_TO_MATH_REPLACE)
from exceptions import CreateSynopsisError
from recognition.audio.constants import Language
from recognition.audio.recognizers import AudioRecognitionYandex
from recognition.constants import ContentType
from recognition.utils import merge_audio_and_video
from recognition.video.image_uploaders import ImageSaverUploadcare
from recognition.video.recognizers import VideoRecognitionCells

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


def make_synopsis_from_video(video):
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

            ar = AudioRecognitionYandex(audio_file_path=out_audio,
                                        lang=Language.RUSSIAN,
                                        key=settings.YANDEX_SPEECH_KIT_KEY)

            recognized_audio = ar.recognize()

            uploadcare_saver = ImageSaverUploadcare(pub_key=settings.UPLOAD_CARE_PUB_KEY)
            vr = VideoRecognitionCells(video_file_path=videofile,
                                       image_saver=uploadcare_saver)
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
        return self._get_object('courses', course_id)

    def get_section(self, section_id):
        return self._get_object('sections', section_id)

    def get_unit(self, unit_id):
        return self._get_object('units', unit_id)

    def get_lesson(self, lesson_id):
        return self._get_object('lessons', lesson_id)

    def get_step(self, step_id):
        return self._get_object('steps', step_id)

    def _get_object(self, object_type, object_id):
        response = self.session.get('{base_url}/api/{type}/{id}'.format(base_url=settings.STEPIK_BASE_URL,
                                                                        type=object_type,
                                                                        id=object_id))
        if not response:
            raise CreateSynopsisError('Failed to get {type} page from stepik, status code = {status_code}'
                                      .format(type=object_type, status_code=response.status_code))

        return response.json()[object_type][0]


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
        text = STEP_PAGE_TEXT_TEMPLATE.format(stepik_base=settings.STEPIK_BASE_URL,
                                              content=self._prepare_content(content),
                                              position=step['position'],
                                              lesson=lesson_page_title,
                                              lesson_id=lesson['id'])
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

    def get_or_create_page_for_section(self, section):
        title = SECTION_PAGE_TITLE_TEMPLATE.format(title=section['title'], id=section['id'])
        text = SECTION_PAGE_TEXT_TEMPLATE.format(title=section['title'], id=section['id'])
        summary = SECTION_PAGE_SUMMARY_TEMPLATE.format(id=section['id'])

        page_url = self._get_or_create_page(title, text, summary)
        logger.info('page for section (section_id = %s, page_url = %s)', section['id'], page_url)
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
                              appendtext='\n{}'.format(text),
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
                text = pypandoc.convert_text(item['content'], format='html', to='mediawiki')

                # replace $latex$ to <math>latex</math>
                text = re.sub(SINGLE_DOLLAR_TO_MATH_PATTERN, SINGLE_DOLLAR_TO_MATH_REPLACE, text)

                # replace $$latex$$ to <math>latex</math>
                text = re.sub(DOUBLE_DOLLAR_TO_MATH_PATTERN, DOUBLE_DOLLAR_TO_MATH_REPLACE, text)

                result.append(text)
            elif item['type'] == ContentType.IMG:
                result.append('<img width="50%" src="{}">'.format(item['content']))
        return '\n\n'.join(result)

    def _is_page_with_title_exist(self, title):
        return self._get_url_by_page_title(title) is not None


def save_synopsis_for_lesson_to_wiki(synopsis):
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


def add_section_to_course(section, course):
    wiki_client = get_wiki_client()

    section_url = wiki_client.get_or_create_page_for_section(section)
    course_url = wiki_client.get_or_create_page_for_course(course)

    logger.info('add section {section} to course {course}'.format(section=section_url,
                                                                  course=course_url))

    section_page_title = SECTION_PAGE_TITLE_TEMPLATE.format(title=section['title'], id=section['id'])
    course_page_title = COURSE_PAGE_TITLE_TEMPLATE.format(title=course['title'], id=course['id'])

    section_categories = wiki_client.get_page_categories(section_page_title)
    if course_page_title not in section_categories:
        course_link = '[[{title}|{position:>3}]]'.format(title=course_page_title,
                                                         position=section['position'])
        wiki_client.add_text_to_page(page_title=section_page_title,
                                     text=course_link,
                                     summary='add section to course')


def add_lesson_to_section(lesson, lesson_position, section):
    wiki_client = get_wiki_client()

    lesson_url = wiki_client.get_or_create_page_for_lesson(lesson)
    section_url = wiki_client.get_or_create_page_for_section(section)

    logger.info('add lesson {lesson} to section {section}'.format(lesson=lesson_url,
                                                                  section=section_url))

    lesson_page_title = LESSON_PAGE_TITLE_TEMPLATE.format(title=lesson['title'], id=lesson['id'])
    section_page_title = SECTION_PAGE_TITLE_TEMPLATE.format(title=section['title'], id=section['id'])

    lesson_categories = wiki_client.get_page_categories(lesson_page_title)
    if section_page_title not in lesson_categories:
        section_link = '[[{title}|{position:>3}]]'.format(title=section_page_title,
                                                          position=lesson_position)
        wiki_client.add_text_to_page(page_title=lesson_page_title,
                                     text=section_link,
                                     summary='add lesson to section')


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

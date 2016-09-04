import json
import logging

import requests
import concurrent.futures
from requests.auth import HTTPBasicAuth

from exceptions import CreateSynopsisError
from utils import (get_lesson_page, get_step_block, make_synopsis_from_video)
from constants import IS_TEXT, STEPIK_BASE_URL

pool = concurrent.futures.ProcessPoolExecutor()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def submit(args):
    pool.submit(task, args)


def task(args):
    logger.info('start task with args {}'.format(args))
    auth = HTTPBasicAuth(args.client_id, args.client_secret)
    try:
        resp = requests.post(url='{base_url}/oauth2/token/'.format(base_url=STEPIK_BASE_URL),
                             data={'grant_type': 'client_credentials'},
                             auth=auth)
    except Exception as err:
        send_response(False, err)
        return

    token = resp.json()['access_token']

    lesson_page = get_lesson_page(args.lesson_id, token)
    if len(lesson_page['lessons']) == 0:
        send_response(False, 'wrong lesson id')
        return

    lesson = lesson_page['lessons'][0]

    if args.step_number and args.step_number > len(lesson['steps']):
        send_response(False, 'wrong step number')
        return

    steps = [lesson['steps'][args.step_number]] if args.step_number else lesson['steps']

    result = {'lesson_id': args.lesson_id,
              'synopsis_by_steps': []}

    try:
        for step in steps:
            block = get_step_block(step, token)

            if block['text']:
                content = [{IS_TEXT: block['text']}, ]
            else:
                content = make_synopsis_from_video(video=block['video'],
                                                   upload_care_pub_key=args.upload_care_pub_key,
                                                   yandex_speech_kit_key=args.yandex_speech_kit_key)

            result['synopsis_by_steps'].append({step: content})
    except CreateSynopsisError as err:
        send_response(False, err)

    result_json = json.dumps(result)
    send_response(True, result_json)


def send_response(status, msg):
    logger.info('recognize result: status = {}, message = {}'.format(status, msg))

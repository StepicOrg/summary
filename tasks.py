import concurrent.futures
import json
import logging

from constants import IS_TEXT
from exceptions import CreateSynopsisError
from utils import StepikClient, make_synopsis_from_video, send_response

pool = concurrent.futures.ProcessPoolExecutor()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def submit_create_synopsis_task(args):
    pool.submit(create_synopsis_task, args)


def create_synopsis_task(args):
    logger.info('start task with args {}'.format(args))

    stepik_client = StepikClient(args.client_id, args.client_secret)

    result = {'lesson_id': args.lesson_id,
              'synopsis_by_steps': []}

    try:
        steps = stepik_client.get_steps(args.lesson_id, args.step_number)
        for step in steps:
            block = stepik_client.get_step_block(step)
            if block['text']:
                content = [{IS_TEXT: block['text']}, ]
            else:
                content = make_synopsis_from_video(video=block['video'],
                                                   upload_care_pub_key=args.upload_care_pub_key,
                                                   yandex_speech_kit_key=args.yandex_speech_kit_key)
            result['synopsis_by_steps'].append({step: content})
    except CreateSynopsisError as err:
        send_response(False, err)
        return

    result_json = json.dumps(result)
    send_response(True, result_json)

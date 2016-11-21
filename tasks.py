import concurrent.futures
import logging

import settings
from constants import IS_TEXT
from exceptions import CreateSynopsisError
from utils import make_synopsis_from_video, post_result_on_wiki

pool = concurrent.futures.ProcessPoolExecutor()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def submit_create_synopsis_task(args):
    pool.submit(create_synopsis_task, args)


def create_synopsis_task(args):
    logger.info('start task with args {}'.format(args))

    try:
        lesson_info = args.stepik_client.get_lesson_info(args.lesson_id, args.step_number)

        result = {
            'lesson_title': lesson_info['title'],
            'lesson_id': args.lesson_id,
            'lesson_wiki_url': lesson_info['lesson_wiki_url'],
            'synopsis_by_steps': []
        }

        for position, step_id in enumerate(lesson_info['steps'], start=1):
            block = args.stepik_client.get_step_block(step_id)
            if block['text']:
                content = [
                    {
                        'type': IS_TEXT,
                        'content': block['text']
                    },
                ]
            else:
                content = make_synopsis_from_video(video=block['video'],
                                                   upload_care_pub_key=settings.UPLOAD_CARE_PUB_KEY,
                                                   yandex_speech_kit_key=settings.YANDEX_SPEECH_KIT_KEY)

            result['synopsis_by_steps'].append(
                {
                    'step_id': step_id,
                    'position': args.step_number or position,
                    'content': content
                }
            )
            response_for_stepik = post_result_on_wiki(result=result)
            args.stepik_client.post_results(status=True, result=response_for_stepik)
    except CreateSynopsisError as err:
        args.stepik_client.post_results(status=False, result=err)
        return

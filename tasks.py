import concurrent.futures
import logging

import settings
from constants import ContentType, SynopsisType
from exceptions import CreateSynopsisError
from utils import make_synopsis_from_video, save_synopsis_to_wiki

pool = concurrent.futures.ProcessPoolExecutor()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def submit_create_synopsis_task(stepik_client, data):
    pool.submit(create_synopsis_task, stepik_client, data)


def create_synopsis_task(stepik_client, data):
    logger.info('start task with args %s', data)
    try:
        if data['type'] == SynopsisType.LESSON:
            lesson_id = data['pk']
            lesson = stepik_client.get_lesson(lesson_id)
            step_ids = lesson['steps']
        else:
            step_id = data.get('pk')
            lesson_id = stepik_client.get_step(step_id)['lesson']
            lesson = stepik_client.get_lesson(lesson_id)
            step_ids = [step_id]

        if len(step_ids) == 0:
            raise CreateSynopsisError('No steps for creation of synopsis')

        synopsis = {
            'lesson': lesson,
            'steps': []
        }
        logger.info('num of steps = %d', len(step_ids))
        for step_id in step_ids:
            step = stepik_client.get_step(step_id)
            logger.info('step = %s', step)
            block = step['block']
            if block['text']:
                content = [
                    {
                        'type': ContentType.TEXT,
                        'content': block['text']
                    },
                ]
            else:
                content = make_synopsis_from_video(video=block['video'],
                                                   upload_care_pub_key=settings.UPLOAD_CARE_PUB_KEY,
                                                   yandex_speech_kit_key=settings.YANDEX_SPEECH_KIT_KEY)

            synopsis['steps'].append(
                {
                    'step': step,
                    'content': content,
                }
            )
        save_synopsis_to_wiki(synopsis=synopsis)
    except CreateSynopsisError:
        logger.exception('Failed to create or save synopsis')
        return

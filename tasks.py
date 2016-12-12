import concurrent.futures
import logging

import settings
from constants import ContentType, SynopsisType
from exceptions import CreateSynopsisError
from utils import make_synopsis_from_video, post_result_on_wiki

pool = concurrent.futures.ProcessPoolExecutor()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def submit_create_synopsis_task(stepik_client, data):
    pool.submit(create_synopsis_task, stepik_client, data)


def create_synopsis_task(stepik_client, data):
    logger.info('start task with args {}'.format(data))
    try:
        if data.get('type') == SynopsisType.LESSON:
            lesson_id = data.get('pk')
            lesson_info = stepik_client.get_lesson_info(lesson_id)
            steps = lesson_info['steps']
        elif data.get('type') == SynopsisType.STEP:
            step_id = data.get('pk')
            lesson_id = stepik_client.get_lesson_by_step(step_id)
            lesson_info = stepik_client.get_lesson_info(lesson_id)
            steps = [step_id]
        else:
            raise CreateSynopsisError('Wrong data format')
        steps = list(map(stepik_client.get_step_info, steps))

        if len(steps) == 0:
            raise CreateSynopsisError('No steps for creation of synopsis')

        result = {
            'lesson': {
                'title': lesson_info['title'],
                'lesson_id': lesson_id,
            },
            'synopsis_by_steps': []
        }
        logger.info('num of steps = {}'.format(len(steps)))
        for step in steps:
            logger.info('step = {}'.format(step))
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

            result['synopsis_by_steps'].append(
                {
                    'step_id': step['id'],
                    'position': step['position'],
                    'content': content,
                }
            )
        post_result_on_wiki(result=result)
    except CreateSynopsisError:
        logger.exception('CreateSynopsisError')
        return

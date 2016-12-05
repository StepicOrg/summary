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

        steps = map(lambda item: stepik_client.get_step_info(item), steps)
        steps = list(map(lambda item: {'step_info': item,
                                       'synopsis_info': stepik_client.get_synopsis_step_info(item)},
                         steps))

        if len(steps) == 0:
            raise CreateSynopsisError('No steps for creation of synopsis')

        result = {
            'lesson': {
                'title': lesson_info['title'],
                'lesson_id': lesson_id,
                'lesson_wiki_url': stepik_client.get_lesson_wiki_url(lesson_info),
                'synopsis_id': lesson_info['synopsis']
            },
            'synopsis_by_steps': []
        }

        for step in steps:
            step_info = step['step_info']
            block = step_info['block']
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
                    'step_id': step_info['id'],
                    'position': step_info['position'],
                    'content': content,
                    'synopsis_info': step['synopsis_info']
                }
            )
        response_for_stepik = post_result_on_wiki(result=result)
        stepik_client.post_results(status=True, result=response_for_stepik)
    except CreateSynopsisError as error:
        stepik_client.post_results(status=False, result={'error': str(error)}, request=data)
        return

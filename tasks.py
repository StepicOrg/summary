import concurrent.futures
import logging

import settings
from constants import ContentType, SynopsisType, EMPTY_STEP_TEXT
from exceptions import CreateSynopsisError
from utils import (make_synopsis_from_video, save_synopsis_to_wiki, add_lesson_to_course,
                   get_stepik_client, get_wiki_client)

pool = concurrent.futures.ProcessPoolExecutor()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def submit_create_synopsis_task(data):
    pool.submit(create_synopsis_task, data)


def create_synopsis_task(data):
    logger.info('start task with args %s', data)
    try:
        stepik_client = get_stepik_client()
        if data['type'] == SynopsisType.COURSE:
            course_id = data['pk']
            lessons = stepik_client.get_lessons_by_course(course_id)
            course = stepik_client.get_course(course_id)
            for lesson in lessons:
                synopsis = create_synopsis_for_lesson(lesson)
                save_synopsis_to_wiki(synopsis)
                add_lesson_to_course(course, lesson)

        elif data['type'] == SynopsisType.LESSON:
            lesson_id = data['pk']
            lesson = stepik_client.get_lesson(lesson_id)
            synopsis = create_synopsis_for_lesson(lesson)
            save_synopsis_to_wiki(synopsis)
        else:
            step_id = data['pk']
            step = stepik_client.get_step(step_id)
            lesson = stepik_client.get_lesson(step['lesson'])
            synopsis = {
                'lesson': lesson,
                'steps': [
                    create_synopsis_for_step(step)
                ]
            }
            save_synopsis_to_wiki(synopsis)

        logger.info('task with args %s completed', data)
    except CreateSynopsisError:
        logger.exception('task with args %s failed', data)
        return


def create_synopsis_for_lesson(lesson):
    stepik_client = get_stepik_client()
    synopsis = {
        'lesson': lesson,
        'steps': []
    }

    for step_id in lesson['steps']:
        step = stepik_client.get_step(step_id)
        synopsis['steps'].append(create_synopsis_for_step(step))

    logger.info('synopsis creation for lesson (id = %s) ended', lesson['id'])
    return synopsis


def create_synopsis_for_step(step):
    wiki_client = get_wiki_client()

    if wiki_client.is_page_for_step_exist(step):
        return {
            'step': step,
            'content': []
        }

    block = step['block']
    if block['text']:
        step_type = 'text'
        content = [
            {
                'type': ContentType.TEXT,
                'content': block['text']
            },
        ]
    elif block['video']:
        step_type = 'video'
        content = make_synopsis_from_video(video=block['video'],
                                           upload_care_pub_key=settings.UPLOAD_CARE_PUB_KEY,
                                           yandex_speech_kit_key=settings.YANDEX_SPEECH_KIT_KEY)
    else:
        step_type = 'empty'
        content = [
            {
                'type': ContentType.TEXT,
                'content': EMPTY_STEP_TEXT
            },
        ]

    logger.info('synopsis creation for step (id = %s, type = %s) ended', step['id'], step_type)
    return {
        'step': step,
        'content': content,
    }

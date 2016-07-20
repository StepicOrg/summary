import os

import django

from constants import PATH_FOR_IMGS, SUMMARY_FILENAME, SUMMARY_TEMPLATE
from django.template.loader import get_template
from django.template import Context
from django.conf import settings

settings.configure(TEMPLATE_DIRS=('../templates',))
django.setup()


def mkdir_and_cd(filename, suffix):
    dir_name = os.path.join(os.getcwd(), '{}_{}'.format(os.path.splitext(filename)[0], suffix))
    if not os.path.exists(dir_name):
        os.mkdir(dir_name)
    os.chdir(dir_name)


class Shape:
    width = None
    height = None

    def __init__(self, width, height):
        self.width = width
        self.height = height


class Human:
    x_min = None
    x_max = None
    w = None

    def __init__(self, x_min, x_max, w):
        self.x_min = x_min
        self.x_max = x_max
        self.w = w

    @staticmethod
    def union(lhs, rhs):
        x_min = min(lhs.x_min, rhs.x_min)
        x_max = max(lhs.x_max, rhs.x_max)
        w = x_max - x_min
        return Human(x_min=x_min, x_max=x_max, w=w)


def make_summary(keyframes, recognized_audio):
    frames_ptr = 0
    audio_ptr = 0

    content = []
    is_frame = 1
    is_text = 2

    last_time = 0
    for i in range(len(keyframes)):
        last_time, keyframes[i][1] = keyframes[i][1], last_time

    while frames_ptr < len(keyframes) and audio_ptr < len(recognized_audio):
        if keyframes[frames_ptr][1] <= recognized_audio[audio_ptr][0]:
            content.append((is_frame, '{dir}/{filename}'.format(dir=PATH_FOR_IMGS,
                                                                filename=keyframes[frames_ptr][0])))
            frames_ptr += 1
        else:
            content.append((is_text, recognized_audio[audio_ptr][2]))
            audio_ptr += 1
    while frames_ptr < len(keyframes):
        content.append((is_frame, '{dir}/{filename}'.format(dir=PATH_FOR_IMGS,
                                                            filename=keyframes[frames_ptr][0])))
        frames_ptr += 1
    while audio_ptr < len(recognized_audio):
        content.append((is_text, recognized_audio[audio_ptr][2]))
        audio_ptr += 1

    with open(SUMMARY_FILENAME, 'w') as file:
        t = get_template(SUMMARY_TEMPLATE)
        c = Context({'content': content})
        html = t.render(c)
        file.write(html)

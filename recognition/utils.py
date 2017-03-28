from typing import Iterable, List, Tuple, Dict

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3 import Retry

from .constants import ContentType


def get_session_with_retries(number_of_retries: int = 5,
                             backoff_factor: float = 0.2,
                             status_forcelist: Iterable[int] = {500, 502, 503, 504},
                             prefix: str = 'https://') -> requests.Session:
    session = requests.session()
    retries = Retry(total=number_of_retries,
                    backoff_factor=backoff_factor,
                    status_forcelist=status_forcelist)
    session.mount(prefix, HTTPAdapter(max_retries=retries))
    return session


def merge_audio_and_video(keyframes: List[list],
                          recognized_audio: List[Tuple[float, float, str]]) -> List[Dict]:
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

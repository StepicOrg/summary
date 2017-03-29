import io
import math
from typing import List, NamedTuple
from xml.etree import ElementTree

from pydub import AudioSegment

from exceptions import CreateSynopsisError
from .constants import (YANDEX_SPEECH_KIT_REQUEST_URL, AUDIO_IS_NOT_RECOGNIZED, MS_IN_SEC, SEC_IN_MIN,
                        RECOGNIZE_TEXT_TEMPLATE, Language)
from .settings import YANDEX_SPEECH_KIT_KEY

RecognizedChunk = NamedTuple('RecognizedChunk', [('start', float), ('end', float), ('text', str)])


class AudioRecognitionBase(object):
    def __init__(self, audio_file_path: str, lang: Language):
        from ..utils import get_session_with_retries
        self.audio_file_path = audio_file_path
        self.lang = lang
        self.session = get_session_with_retries()

    def recognize(self) -> List[RecognizedChunk]:
        raise NotImplementedError()


class AudioRecognitionYandex(AudioRecognitionBase):
    audio_segment = None

    def __init__(self, audio_file_path: str, lang: Language):
        super().__init__(audio_file_path, lang)
        self.audio_segment = AudioSegment.from_file(audio_file_path)

    def recognize(self) -> List[RecognizedChunk]:
        lang = None
        if self.lang == Language.RUSSIAN:
            lang = 'ru-RU'
        elif self.lang == Language.ENGLISH:
            lang = 'en-EN'
        recognized_audio = []
        for start, end, chunk in self._chunks():
            url = YANDEX_SPEECH_KIT_REQUEST_URL.format(key=YANDEX_SPEECH_KIT_KEY,
                                                       lang=lang)
            response = self.session.post(url=url,
                                         data=chunk,
                                         headers={'Content-Type': 'audio/x-mpeg-3'})
            if not response:
                raise CreateSynopsisError('Failed to recognize audio, status code: {status_code}'
                                          .format(status_code=response.status_code))

            root = ElementTree.fromstring(response.text)
            text = root[0].text if root.attrib['success'] == '1' else AUDIO_IS_NOT_RECOGNIZED

            recognized_audio.append(self._recognize_text_format(start, end, text))
        return recognized_audio

    def _chunks(self):
        arr = [x if not math.isinf(x) else 0 for x in
               map(lambda item: -item.dBFS, self.audio_segment)]

        ptr = 0
        max_len_of_chunk = 19500

        while len(arr) > ptr + max_len_of_chunk:
            left = ptr + int(max_len_of_chunk * 0.75)
            right = ptr + max_len_of_chunk
            chunk = io.BytesIO()
            ind = arr.index(max(arr[left:right]), left, right)
            self.audio_segment[ptr:ind].export(chunk, format='mp3')
            yield (ptr, ind, chunk)
            ptr = ind
        chunk = io.BytesIO()
        ind = len(arr) - 1
        self.audio_segment[ptr:ind].export(chunk, format='mp3')
        yield (ptr, ind, chunk)

    @staticmethod
    def _recognize_text_format(start, end, text) -> RecognizedChunk:
        min_start, sec_start = divmod(start // MS_IN_SEC, SEC_IN_MIN)
        min_end, sec_end = divmod(end // MS_IN_SEC, SEC_IN_MIN)

        text = RECOGNIZE_TEXT_TEMPLATE.format(min_start=min_start,
                                              sec_start=sec_start,
                                              min_end=min_end,
                                              sec_end=sec_end,
                                              text=text)

        return RecognizedChunk(start=start/MS_IN_SEC, end=end/MS_IN_SEC, text=text)

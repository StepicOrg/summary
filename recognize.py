import io
import logging
import math
from xml.etree import ElementTree

import cv2
import numpy as np
import peakutils
from pydub import AudioSegment

from constants import (TIME_BETWEEN_KEYFRAMES, FRAME_PERIOD, BOTTOM_LINE_COEF, SCALE_FACTOR,
                       THRESHOLD_FOR_PEAKS_DETECTION, MAX_KEYFRAME_PER_SEC, THRESHOLD_DELTA,
                       MIN_SIZE_COEF, CENTER_LEFT_BORDER, CENTER_RIGHT_BORDER,
                       UPLOADCARE_URL_TO_UPLOAD, MS_IN_SEC, AUDIO_IS_NOT_RECOGNIZED, SEC_IN_MIN,
                       RECOGNIZE_TEXT_TEMPLATE, YANDEX_SPEECH_KIT_REQUEST_URL)
from exceptions import CreateSynopsisError

logger = logging.getLogger(__name__)


class VideoRecognition(object):
    cap = None
    cascade = None
    num_of_frames = None
    diffs = None
    peaks = None
    peak = None
    bottom_line = None
    humans = None
    fps = None
    shape = None
    frames_between_keyframes = None
    keyframes_src_with_timestamp = None
    uploadcare_pub_key = None
    session = None

    def __init__(self, video_file, uploadcare_pub_key, haar_cascade=None):
        from recognition.utils import get_session_with_retries
        self.uploadcare_pub_key = uploadcare_pub_key

        self.cap = cv2.VideoCapture(video_file)
        if not self.cap.isOpened():
            raise CreateSynopsisError('VideoRecognition error, wrong video filename "{filename}"'
                                      .format(filename=video_file))

        if haar_cascade is None:
            haar_cascade = '/home/synopsis/static/HS.xml'

        self.cascade = cv2.CascadeClassifier(haar_cascade)
        if self.cascade.empty():
            raise CreateSynopsisError('VideoRecognition error, wrong haar cascade filename "{filename}"'
                                      .format(filename=haar_cascade))

        self.shape = Shape(width=int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                           height=int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self.num_of_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        self.frames_between_keyframes = (TIME_BETWEEN_KEYFRAMES * self.fps) // FRAME_PERIOD

        self.diffs = []
        self.peaks = []
        self.humans = []
        self.keyframes_src_with_timestamp = []

        self.session = get_session_with_retries()

    def get_keyframes_src_with_timestamp(self):
        self.compute_diffs()
        self.find_peaks()
        self.upload_keyframes()
        return self.keyframes_src_with_timestamp

    def compute_diffs(self):
        old_frame = self._get_next_frame()
        new_frame = self._get_next_frame()
        count = 0
        while (not (new_frame is None)) and count < self.num_of_frames:
            self.diffs.append(self._frame_diff(old_frame=old_frame,
                                               new_frame=new_frame))
            old_frame = new_frame
            new_frame = self._get_next_frame()
            count += FRAME_PERIOD
        self.bottom_line = float(np.mean(self.diffs) * BOTTOM_LINE_COEF)

    def find_peaks(self):
        threshold = THRESHOLD_FOR_PEAKS_DETECTION
        first_try = True
        max_num_of_keyframe = MAX_KEYFRAME_PER_SEC * self.num_of_frames / self.fps
        max_num_of_keyframe = max(max_num_of_keyframe, 1)
        while ((len(self.peaks) > max_num_of_keyframe or first_try)
               and threshold <= 1):
            self.peaks = peakutils.indexes(np.array(self.diffs),
                                           thres=threshold,
                                           min_dist=self.frames_between_keyframes)
            if (len(self.peaks) == 0
                or len(self.diffs) - self.peaks[-1] > self.frames_between_keyframes):
                self.peaks = np.append(self.peaks, [len(self.diffs) - 1])
            self.peaks = list(
                filter(lambda peak: not self._last_sec_video_is_bad(peak), self.peaks))
            threshold += THRESHOLD_DELTA
            first_try = False

    def upload_keyframes(self):
        self.cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)
        i = 0
        peaks_ptr = 0
        frames_buffer = [0] * int(self.fps * 1)
        frames_buffer_ptr = 0
        while self.cap.isOpened() and peaks_ptr < len(self.peaks):
            ret, frame = self.cap.read()
            if not ret:
                break
            frames_buffer[frames_buffer_ptr] = frame
            frames_buffer_ptr += 1
            frames_buffer_ptr %= len(frames_buffer)
            if i == self.peaks[peaks_ptr] * FRAME_PERIOD:
                ind_in_buffer = (frames_buffer_ptr + len(frames_buffer)) % len(frames_buffer)
                img_src = self._upload_image(frames_buffer[ind_in_buffer])
                self.keyframes_src_with_timestamp.append([img_src, i / self.fps])
                peaks_ptr += 1
            i += 1
        return self.keyframes_src_with_timestamp

    def _get_next_frame(self):
        frame = None
        for i in range(FRAME_PERIOD):
            ret, frame = self.cap.read()
            if not ret:
                return
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    def _frame_diff(self, old_frame, new_frame):
        if len(self.humans) == 0:
            self.humans.append(self._find_human(old_frame))
        self.humans.append(self._find_human(new_frame))

        human_old_frame = self.humans[-2]
        human_new_frame = self.humans[-1]

        old_frame_copy = old_frame.copy()
        new_frame_copy = new_frame.copy()

        human = Human.union(human_old_frame, human_new_frame)

        x_min, x_max, w = human.x_min, human.x_max, human.w
        num_of_pixels = self.shape.height * self.shape.width
        if w != 0:
            x_l = int(x_min - w * 0.15 if x_min - w * 0.15 >= 0 else 0)
            x_r = int(x_max + w * 0.15 if x_max + w * 0.15 < self.shape.width else self.shape.width)
            for frame in [old_frame_copy, new_frame_copy]:
                cv2.rectangle(frame, (x_l, 0), (x_r, self.shape.height), (0, 0, 0), cv2.FILLED)

            abs_diff = cv2.absdiff(old_frame_copy, new_frame_copy)
            num_of_pixels -= self.shape.height * (x_r - x_l)
        else:
            abs_diff = cv2.absdiff(old_frame, new_frame)

        return float(abs_diff.sum() / (num_of_pixels or 1))

    def _find_human(self, frame):
        rectangles = self.cascade.detectMultiScale(frame,
                                                   scaleFactor=SCALE_FACTOR,
                                                   minSize=(self.shape.height // MIN_SIZE_COEF,
                                                            self.shape.height // MIN_SIZE_COEF))
        if len(rectangles) == 0:
            return Human(0, 0, 0)
        x_min = min([x for x, _, _, _ in rectangles] or [self.shape.width])
        x_max = max([x + w for x, _, w, _ in rectangles] or [0])
        return Human(x_min=x_min, x_max=x_max, w=x_max - x_min)

    def _union_rectangles(self, lhs, rhs):
        if len(lhs) == 0 and len(rhs) == 0:
            return 0, 0, 0
        x_min = min(min([x for x, _, _, _ in lhs] or [self.shape.width - 1]),
                    min([x for x, _, _, _ in rhs] or [self.shape.width - 1]))
        x_max = max(max([x + w for x, _, w, _ in lhs] or [0]),
                    max([x + w for x, _, w, _ in rhs] or [0]))
        return x_min, x_max, x_max - x_min

    def _last_sec_video_is_bad(self, ind):
        if ind < self.frames_between_keyframes:
            return True
        video_frame = 0
        human_in_center_frames = 0
        for i in range(1, self.frames_between_keyframes):
            if self.diffs[ind - i] > self.bottom_line:
                video_frame += 1

            human = self.humans[ind - i]
            if human.w > 0:
                center = human.x_min + human.w / 2
                if CENTER_LEFT_BORDER * self.shape.width <= center <= CENTER_RIGHT_BORDER * self.shape.width:
                    human_in_center_frames += 1
        return max(video_frame, human_in_center_frames) > self.frames_between_keyframes // 2

    def _upload_image(self, image):
        data = {'UPLOADCARE_PUB_KEY': self.uploadcare_pub_key,
                'UPLOADCARE_STORE': 1}

        image_bytes = io.BytesIO(cv2.imencode('.png', image)[1].tostring())

        response = self.session.post(url=UPLOADCARE_URL_TO_UPLOAD,
                                     files={'file': image_bytes},
                                     data=data)
        if not response:
            raise CreateSynopsisError('Failed to upload image, status code: {status_code}'
                                      .format(status_code=response.status_code))

        return 'https://ucarecdn.com/{uuid}/'.format(uuid=response.json()['file'])


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


class AudioRecognition(object):
    _audio_segment = None
    yandex_speech_kit_key = None
    lang = None
    session = None

    def __init__(self, file, yandex_speech_kit_key, lang='ru-RU'):
        from recognition.utils import get_session_with_retries
        self._audio_segment = AudioSegment.from_file(file)
        self.yandex_speech_kit_key = yandex_speech_kit_key
        self.lang = lang
        self.session = get_session_with_retries()

    def chunks(self):
        arr = [x if not math.isinf(x) else 0 for x in
               map(lambda item: -item.dBFS, self._audio_segment)]

        ptr = 0
        max_len_of_chunk = 19500

        while len(arr) > ptr + max_len_of_chunk:
            left = ptr + int(max_len_of_chunk * 0.75)
            right = ptr + max_len_of_chunk
            chunk = io.BytesIO()
            ind = arr.index(max(arr[left:right]), left, right)
            self._audio_segment[ptr:ind].export(chunk, format='mp3')
            yield (ptr, ind, chunk)
            ptr = ind
        chunk = io.BytesIO()
        ind = len(arr) - 1
        self._audio_segment[ptr:ind].export(chunk, format='mp3')
        yield (ptr, ind, chunk)

    def recognize(self):
        recognized_audio = []
        for start, end, chunk in self.chunks():
            url = YANDEX_SPEECH_KIT_REQUEST_URL.format(key=self.yandex_speech_kit_key,
                                                       lang=self.lang)
            response = self.session.post(url=url,
                                         data=chunk,
                                         headers={'Content-Type': 'audio/x-mpeg-3'})
            if not response:
                raise CreateSynopsisError('Failed to recognize audio, status code: {status_code}'
                                          .format(status_code=response.status_code))

            root = ElementTree.fromstring(response.text)
            text = root[0].text if root.attrib['success'] == '1' else AUDIO_IS_NOT_RECOGNIZED

            recognized_audio.append(AudioRecognition._recognize_text_format(start, end, text))
        return recognized_audio

    @staticmethod
    def _recognize_text_format(start, end, text):
        min_start, sec_start = divmod(start // MS_IN_SEC, SEC_IN_MIN)
        min_end, sec_end = divmod(end // MS_IN_SEC, SEC_IN_MIN)

        text = RECOGNIZE_TEXT_TEMPLATE.format(min_start=min_start,
                                              sec_start=sec_start,
                                              min_end=min_end,
                                              sec_end=sec_end,
                                              text=text)

        return start / MS_IN_SEC, end / MS_IN_SEC, text

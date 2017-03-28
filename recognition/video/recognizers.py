import io
from typing import Iterable, List

import cv2
import numpy as np
import peakutils

from exceptions import CreateSynopsisError
from .constants import (TIME_BETWEEN_KEYFRAMES, FRAME_PERIOD, BOTTOM_LINE_COEF, SCALE_FACTOR, MIN_SIZE_COEF,
                        THRESHOLD_FOR_PEAKS_DETECTION, MAX_KEYFRAME_PER_SEC, THRESHOLD_DELTA, CENTER_LEFT_BORDER,
                        CENTER_RIGHT_BORDER)
from .image_uploaders import ImageUploaderBase


class VideoRecognitionBase(object):
    image_uploader = None
    cap = None
    fps = None

    def __init__(self, video_file_path: str, image_uploader: ImageUploaderBase):
        self.image_uploader = image_uploader
        self.cap = cv2.VideoCapture(video_file_path)
        self.fps = int(self.cap.get(cv2.CAP_PROP_FPS))

        if not self.cap.isOpened():
            raise CreateSynopsisError('VideoRecognition error, wrong video filename "{filename}"'
                                      .format(filename=video_file_path))

    def get_keyframes_src_with_timestamp(self) -> List[list]:
        keyframe_positions = self.get_keyframes()
        keyframes_src_with_timestamp = self._upload_keyframes(keyframe_positions)
        return keyframes_src_with_timestamp

    def get_keyframes(self) -> List[int]:
        raise NotImplementedError()

    def _upload_keyframes(self, keyframe_positions: Iterable[int]) -> List[list]:
        self.cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)

        frame_ptr = 0
        _, frame = self.cap.read()
        keyframe_positions = sorted(keyframe_positions)
        keyframes_src_with_timestamp = []
        for keyframe_position in keyframe_positions:
            while self.cap.isOpened() and frame_ptr != keyframe_position:
                ret, frame = self.cap.read()
                frame_ptr += 1
                if not ret:
                    raise CreateSynopsisError('Wrong keyframe_position = {}'.format(keyframe_position))

            image_bytes = io.BytesIO(cv2.imencode('.png', frame)[1].tostring())
            image_src = self.image_uploader.upload(image_bytes)
            keyframes_src_with_timestamp.append([image_src, keyframe_position / self.fps])
        return keyframes_src_with_timestamp


class VideoRecognitionNaive(VideoRecognitionBase):
    cascade = None
    num_of_frames = None
    diffs = None
    peaks = None
    bottom_line = None
    humans = None
    shape = None
    frames_between_keyframes = None

    def __init__(self, video_file_path: str, image_uploader: ImageUploaderBase):
        super().__init__(video_file_path, image_uploader)

        haar_cascade = '/home/synopsis/recognition/video/static/HS.xml'
        self.cascade = cv2.CascadeClassifier(haar_cascade)
        if self.cascade.empty():
            raise CreateSynopsisError('VideoRecognition error, wrong haar cascade filename "{filename}"'
                                      .format(filename=haar_cascade))

        self.shape = self._Shape(width=int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                                 height=int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self.num_of_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        self.frames_between_keyframes = (TIME_BETWEEN_KEYFRAMES * self.fps) // FRAME_PERIOD

        self.diffs = []
        self.peaks = []
        self.humans = []

    def get_keyframes(self) -> List[int]:
        self._compute_diffs()
        self._find_peaks()
        return list(map(lambda peak: max(0, peak * FRAME_PERIOD - int(self.fps)), self.peaks))

    def _compute_diffs(self):
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

    def _find_peaks(self):
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

        human = self._Human.union(human_old_frame, human_new_frame)

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
            return self._Human(0, 0, 0)
        x_min = min([x for x, _, _, _ in rectangles] or [self.shape.width])
        x_max = max([x + w for x, _, w, _ in rectangles] or [0])
        return self._Human(x_min=x_min, x_max=x_max, w=x_max - x_min)

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

    class _Shape:
        width = None
        height = None

        def __init__(self, width, height):
            self.width = width
            self.height = height

    class _Human:
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
            return VideoRecognitionNaive._Human(x_min=x_min, x_max=x_max, w=w)

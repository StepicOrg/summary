import io
from enum import Enum
from typing import Iterable, List

import cv2
import logging
import numpy as np
import peakutils
import scenedetect

from exceptions import CreateSynopsisError
from .utils import Rectangle, image_diff_abs, get_rectangle_with_human_dlib
from .constants import (TIME_BETWEEN_KEYFRAMES, FRAME_PERIOD, BOTTOM_LINE_COEF, SCALE_FACTOR, MIN_SIZE_COEF,
                        THRESHOLD_FOR_PEAKS_DETECTION, MAX_KEYFRAME_PER_SEC, THRESHOLD_DELTA, CENTER_LEFT_BORDER,
                        CENTER_RIGHT_BORDER)
from .image_uploaders import ImageSaverBase

logging.basicConfig(format='[%(asctime)s]%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class VideoRecognitionBase(object):
    def __init__(self, video_file_path: str, image_saver: ImageSaverBase = None):
        self.image_saver = image_saver
        # noinspection PyArgumentList
        self.cap = cv2.VideoCapture(video_file_path)
        self.fps = int(self.cap.get(cv2.CAP_PROP_FPS))

        if not self.cap.isOpened():
            raise CreateSynopsisError('VideoRecognition error, wrong video filename "{filename}"'
                                      .format(filename=video_file_path))

    def get_keyframes_src_with_timestamp(self) -> List[list]:
        keyframe_positions = self.get_keyframes()
        keyframes_src_with_timestamp = self.save_keyframes(keyframe_positions)
        return keyframes_src_with_timestamp

    def get_keyframes(self) -> List[int]:
        raise NotImplementedError()

    def save_keyframes(self, keyframe_positions: Iterable[int]) -> List[list]:
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
            image_src = self.image_saver.save(image_bytes, keyframe_position)
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

    def __init__(self, video_file_path: str,
                 image_saver: ImageSaverBase = None,
                 threshold: float = THRESHOLD_FOR_PEAKS_DETECTION):
        super().__init__(video_file_path, image_saver)
        self.threshold = threshold

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
        return list(map(lambda peak: int(max(1, peak * FRAME_PERIOD - self.fps)), self.peaks))

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
        threshold = self.threshold
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


class VideoRecognitionPySceneDetect(VideoRecognitionBase):
    def __init__(self, video_file_path: str,
                 image_saver: ImageSaverBase = None,
                 threshold: float = None):
        super().__init__(video_file_path, image_saver)
        self.threshold = round(threshold * 255)

    def get_keyframes(self) -> List[int]:
        scene_detectors = scenedetect.detectors.get_available()
        args = self.Args(detection_method='content', threshold=self.threshold)

        scene_manager = scenedetect.manager.SceneManager(args, scene_detectors)
        scenedetect.detect_scenes(self.cap, scene_manager)

        result = scene_manager.scene_list
        if len(result) == 0:
            result.append(int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)))

        result = list(map(lambda item: max(1, item - self.fps), result))

        return result

    class Args(object):
        def __init__(self, detection_method, threshold=None):
            self.min_percent = 95
            self.min_scene_len = 15
            self.detection_method = detection_method
            self.threshold = threshold
            self.downscale_factor = 1
            self.frame_skip = 0
            self.save_images = False
            self.start_time = None
            self.end_time = None
            self.duration = None
            self.quiet_mode = True
            self.stats_file = None


class VideoRecognitionCells(VideoRecognitionBase):
    def __init__(self, video_file_path: str,
                 image_saver: ImageSaverBase = None,
                 n_cells_width: int = 16,
                 n_cells_height: int = 9,
                 frame_period: int = 3,
                 min_length_sec: float = 1,
                 resize_coef: float = 0.5,
                 back_down_sec: float = 0.5,
                 image_diff=image_diff_abs,
                 max_frames_per_min=4,
                 cell_threshold_coef: float = 4,
                 peak_threshold: float = 0.4,
                 threshold_coef: float = 4,
                 humans=None):
        super().__init__(video_file_path, image_saver)
        self.n_cells_width = n_cells_width
        self.n_cells_height = n_cells_height
        self.frame_period = frame_period
        self.min_length_sec = min_length_sec
        self.resize_coef = resize_coef
        self.image_diff = image_diff
        self.max_frames_per_min = max_frames_per_min
        self.cell_threshold_coef = cell_threshold_coef
        self.peak_threshold = peak_threshold
        self.threshold_coef = threshold_coef
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) * resize_coef)
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) * resize_coef)
        self.min_length_frames = int((min_length_sec * self.fps) // self.frame_period)
        self.back_down_frames = int((back_down_sec * self.fps) // self.frame_period)
        self.humans = humans
        self.segments = []
        self.peaks = []
        self.post_processed_peaks = []

        self.cells = self._get_cells()

    def get_keyframes(self) -> List[int]:
        logger.info('self._compute_humans()')
        self._compute_humans()
        logger.info('self._compute_segments()')
        self._compute_segments()
        logger.info('self._compute_cells_diffs()')
        self._compute_cells_diffs()
        logger.info('self._compute_cells_thresholds()')
        self._compute_cells_thresholds()
        logger.info('self._compute_relative_cells_diffs()')
        self._compute_relative_cells_diffs()
        logger.info('self._compute_diffs()')
        self._compute_diffs()
        logger.info('self._compute_threshold()')
        self._compute_threshold()
        logger.info('self._compute_peaks()')
        self._compute_peaks()
        logger.info('self._post_processing_segments()')
        self._post_processing_segments()
        logger.info('self._post_processing()')
        self._post_processing()
        return list(map(lambda item: (item + 1) * self.frame_period - 1, self.post_processed_peaks))

    def _compute_humans(self):
        if self.humans is not None:
            return

        self.humans = []
        self.cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)
        frame = self._get_next_frame()
        while frame is not None:
            self.humans.append(get_rectangle_with_human_dlib(frame))
            frame = self._get_next_frame()

    def _compute_segments(self):
        def frame_type(h) -> VideoRecognitionCells.SegmentType:
            if self._is_human_in_center(h):
                return self.SegmentType.HUMAN_CENTER
            elif h.is_empty():
                return self.SegmentType.EMPTY
            else:
                return self.SegmentType.HUMAN_SIDE

        segments = []
        for ind, human in enumerate(self.humans):
            cur_frame_type = frame_type(human)
            if cur_frame_type == self.SegmentType.HUMAN_CENTER:
                continue

            if len(segments) == 0 or segments[-1].kind != cur_frame_type:
                segments.append(self.Segment(kind=cur_frame_type))

            segments[-1].frame_numbers.append(ind)

        segments = list(filter(lambda s: len(s.frame_numbers) >= self.min_length_frames,
                               segments))

        if len(segments) == 0:
            return

        self.segments.append(segments[0])
        for segment in segments[1:]:
            if self.segments[-1].kind != segment.kind:
                self.segments.append(segment)
            else:
                self.segments[-1].frame_numbers.extend(segment.frame_numbers)

    def _compute_cells_diffs(self):
        self.cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)
        frame_ptr = 0
        for segment in self.segments:
            lhs_frame = self._get_next_frame_by_ptr(frame_ptr, segment.frame_numbers[0])
            frame_ptr = segment.frame_numbers[0] + 1
            for i in range(1, len(segment.frame_numbers)):
                rhs_frame = self._get_next_frame_by_ptr(frame_ptr, segment.frame_numbers[i])
                frame_ptr = segment.frame_numbers[i] + 1
                diff = self._get_frame_diff(lhs_frame, rhs_frame)
                segment.absolute_cells_diffs.append(diff)
                lhs_frame = rhs_frame

    def _get_next_frame_by_ptr(self, cur_ptr, target_frame):
        if cur_ptr > target_frame:
            logger.warning('cur_ptr > target_frame')
            return None
        frame = self._get_next_frame()
        while cur_ptr != target_frame:
            frame = self._get_next_frame()
            cur_ptr += 1

        return frame

    def _get_frame_diff(self, lhs_frame, rhs_frame, human=None) -> List[list]:
        result = [[0 for _ in range(self.n_cells_width)]
                  for _ in range(self.n_cells_height)]

        for i in range(self.n_cells_height):
            for j in range(self.n_cells_width):
                if human is not None and Rectangle.is_intersect(human, self.cells[i][j]):
                    result[i][j] = 0
                else:
                    p1, p2 = self.cells[i][j].get_points()
                    result[i][j] = self.image_diff(lhs_frame[p1[1]:p2[1], p1[0]:p2[0]],
                                                   rhs_frame[p1[1]:p2[1], p1[0]:p2[0]])
        return result

    def _compute_cells_thresholds(self):
        for segment in self.segments:
            segment.cells_thresholds = [[0 for _ in range(self.n_cells_width)]
                                        for _ in range(self.n_cells_height)]
            for i in range(self.n_cells_height):
                for j in range(self.n_cells_width):
                    cell_diffs = list(map(lambda item: item[i][j], segment.absolute_cells_diffs))
                    mean = np.mean(cell_diffs)
                    sd = np.std(cell_diffs)
                    segment.cells_thresholds[i][j] = mean + self.cell_threshold_coef * sd

    def _compute_relative_cells_diffs(self):
        for segment in self.segments:
            for absolute_cells_diff in segment.absolute_cells_diffs:
                relative_cells_diff = self._absolute_to_relative_cells_diff(absolute_cells_diff,
                                                                            segment.cells_thresholds)
                segment.relative_cells_diffs.append(relative_cells_diff)

    def _absolute_to_relative_cells_diff(self, absolute_cells_diff, cells_thresholds):
        relative_cells_diff = [[0 for _ in range(self.n_cells_width)]
                               for _ in range(self.n_cells_height)]
        for i in range(self.n_cells_height):
            for j in range(self.n_cells_width):
                relative_cells_diff[i][j] = 1 if (absolute_cells_diff[i][j] > cells_thresholds[i][j]) else 0
        return relative_cells_diff

    def _compute_diffs(self):
        for segment in self.segments:
            for relative_cells_diff in segment.relative_cells_diffs:
                segment.diffs.append(self._cells_diff_to_frame_diff(relative_cells_diff))

    def _cells_diff_to_frame_diff(self, relative_cells_diff):
        diff = 0
        for i in range(self.n_cells_height):
            for j in range(self.n_cells_width):
                diff += relative_cells_diff[i][j]
        return diff

    def _compute_threshold(self):
        for segment in self.segments:
            mean = np.mean(segment.diffs)
            sd = np.std(segment.diffs)
            segment.threshold = mean + self.threshold_coef * sd

    def _compute_peaks(self):
        for segment in self.segments:
            last_peak = 0
            peak_indices = peakutils.peak.indexes(segment.diffs, self.peak_threshold)
            for peak_ind in peak_indices:
                if segment.diffs[peak_ind] > self.n_cells_height * self.n_cells_width * 0.15:
                    if peak_ind - last_peak > self.min_length_frames:
                        segment.peaks.append(segment.frame_numbers[peak_ind])
                    last_peak = peak_ind
        if len(self.segments) != 0:
            if len(self.segments[-1].peaks) == 0:
                self.segments[-1].peaks.append(self.segments[-1].frame_numbers[-1])
            else:
                last_peak_ind = self.segments[-1].frame_numbers.index(self.segments[-1].peaks[-1])
                last_ind = len(self.segments[-1].frame_numbers) - 1
                if last_ind - last_peak_ind > self.min_length_frames:
                    self.segments[-1].peaks.append(self.segments[-1].frame_numbers[-1])

    def _post_processing_segments(self):
        self.cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)
        frame_ptr = 0
        for segment in self.segments:
            post_processed_peaks = []
            for peak in segment.peaks:
                peak_ind = segment.frame_numbers.index(peak)
                new_ind = max(0, peak_ind - self.back_down_frames)
                post_processed_peaks.append(segment.frame_numbers[new_ind])

            if len(post_processed_peaks) > 1:
                last_frame_ind = post_processed_peaks[0]
                segment.post_processed_peaks.append(last_frame_ind)

                last_frame = self._get_next_frame_by_ptr(frame_ptr, last_frame_ind)
                frame_ptr = last_frame_ind + 1

                for i in range(1, len(post_processed_peaks)):
                    rhs_frame_ind = post_processed_peaks[i]
                    rhs_frame = self._get_next_frame_by_ptr(frame_ptr, rhs_frame_ind)
                    frame_ptr = rhs_frame_ind + 1
                    absolute_cells_diff = self._get_frame_diff(last_frame, rhs_frame)
                    relative_cells_diff = self._absolute_to_relative_cells_diff(absolute_cells_diff,
                                                                                segment.cells_thresholds)
                    diff = self._cells_diff_to_frame_diff(relative_cells_diff)
                    if diff > segment.threshold:
                        last_frame_ind = rhs_frame_ind
                        last_frame = rhs_frame
                        segment.post_processed_peaks.append(last_frame_ind)

            else:
                segment.post_processed_peaks = post_processed_peaks

    def _process_joints(self) -> List[int]:
        self.cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)
        frame_ptr = 0

        res = []
        for i in range(1, len(self.segments)):
            lhs_frame_ind = self.segments[i - 1].frame_numbers[-1]
            rhs_frame_ind = self.segments[i].frame_numbers[0]
            lhs_frame = self._get_next_frame_by_ptr(frame_ptr, lhs_frame_ind)
            frame_ptr = lhs_frame_ind + 1
            rhs_frame = self._get_next_frame_by_ptr(frame_ptr, rhs_frame_ind)
            frame_ptr = rhs_frame_ind + 1
            union_human = Rectangle.union(self.humans[lhs_frame_ind], self.humans[rhs_frame_ind])
            absolute_cells_diff = self._get_frame_diff(lhs_frame, rhs_frame, union_human)

            if self.segments[i - 1].kind == self.SegmentType.EMPTY:
                cells_thresholds = self.segments[i - 1].cells_thresholds
                threshold = self.segments[i - 1].threshold
            else:
                cells_thresholds = self.segments[i].cells_thresholds
                threshold = self.segments[i].threshold

            relative_cells_diff = self._absolute_to_relative_cells_diff(absolute_cells_diff, cells_thresholds)
            frame_diff = self._cells_diff_to_frame_diff(relative_cells_diff)

            if frame_diff > threshold:
                res.append(lhs_frame_ind)

        return res

    def _post_processing(self):
        self.peaks.extend(list(map(lambda p: max(0, p - self.back_down_frames), self._process_joints())))
        for segment in self.segments:
            self.peaks.extend(segment.post_processed_peaks)

        if len(self.peaks) == 0:
            return

        self.peaks = sorted(self.peaks)
        last_peak = 0
        for peak in self.peaks:
            if peak - last_peak > self.min_length_frames:
                self.post_processed_peaks.append(peak)
            last_peak = peak

    def _is_human_in_center(self, human) -> bool:
        if human.is_empty():
            return False

        if human.w * human.h > (2 / 3) * self.width * self.height:
            return True

        human_center = human.x + human.w / 2
        left_border = self.width * 0.4
        right_border = self.width * 0.6

        return left_border <= human_center <= right_border

    def _get_cells(self) -> List[List[Rectangle]]:
        cell_width = int(self.width / self.n_cells_width)
        cell_height = int(self.height / self.n_cells_height)

        if self.width % self.n_cells_width != 0:
            self.n_cells_width += 1

        if self.height % self.n_cells_height != 0:
            self.n_cells_height += 1

        cells = [[] for _ in range(self.n_cells_height)]

        for row_ind, row in enumerate(cells):
            for col_ind in range(self.n_cells_width):
                row.append(Rectangle(x=col_ind * cell_width,
                                     y=row_ind * cell_height,
                                     w=min(cell_width, self.width - col_ind * cell_width),
                                     h=min(cell_height, self.height - row_ind * cell_height)))

        return cells

    def _get_next_frame(self):
        frame = None
        for i in range(self.frame_period):
            ret, frame = self.cap.read()
            if not ret:
                return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.resize(frame, (0, 0), fx=self.resize_coef, fy=self.resize_coef)

    class Segment(object):
        def __init__(self, kind, frame_numbers: List[int] = None):
            self.frame_numbers = frame_numbers or []
            self.kind = kind
            self.absolute_cells_diffs = []
            self.cells_thresholds = []
            self.relative_cells_diffs = []
            self.diffs = []
            self.threshold = None
            self.peaks = []
            self.post_processed_peaks = []

        def __str__(self):
            return 'Segment kind={}'.format(self.kind)

    class SegmentType(Enum):
        EMPTY = 1
        HUMAN_SIDE = 2
        HUMAN_CENTER = 3

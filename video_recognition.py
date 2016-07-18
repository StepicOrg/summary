import sys
import os
import cv2
import matplotlib.pyplot as plt

from utills import mkdir_and_cd, Shape, Human
from constants import (EVERY_Nth_FRAME, BOTTOM_LINE_COEF, TIME_BETWEEN_KEYFRAMES, THRESHOLD_FOR_PEAKS_DETECTION,
                       MAX_KEYFRAME_PER_SEC, THRESHOLD_DELTA, SCALE_FACTOR,
                       MIN_SIZE_COEF, CENTER_LEFT_BORDER, CENTER_RIGHT_BORDER, PATH_FOR_IMGS, IMG_NAME_TEMPLATE,
                       DIFFS_PNG_NAME)
import numpy as np
import peakutils


class VideoRecognition:
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

    def __init__(self, args):
        if len(args) < 3 or len(args) > 4:
            print('wrong args')
            print('Example: ')
            print('  python3 summary.py video_file_name.mp4 cascade_file_name.xml [num_of_frames]')
            sys.exit()

        self.cap = cv2.VideoCapture(args[1])
        if not self.cap.isOpened():
            print('wrong video_file_name')
            sys.exit()

        self.cascade = cv2.CascadeClassifier(args[2])
        if self.cascade.empty():
            print('wrong cascade_file_name')
            sys.exit()

        self.shape = Shape(width=int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                           height=int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self.num_of_frames = int(args[3]) if len(args) == 4 else int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        self.frames_between_keyframes = (TIME_BETWEEN_KEYFRAMES * self.fps) // EVERY_Nth_FRAME

        self.diffs = []
        self.peaks = []
        self.humans = []

        mkdir_and_cd(args[1], 'summary')

    def compute_diffs(self):
        old_frame = self._get_next_frame()
        new_frame = self._get_next_frame()
        count = 0
        while (not (new_frame is None)) and count < self.num_of_frames:
            if count % (EVERY_Nth_FRAME * 100) == 0:
                print(count * 100 // self.num_of_frames, '%')
            self.diffs.append(self._frame_diff(old_frame=old_frame,
                                               new_frame=new_frame))
            old_frame = new_frame
            new_frame = self._get_next_frame()
            count += EVERY_Nth_FRAME
        self.bottom_line = float(np.mean(self.diffs) * BOTTOM_LINE_COEF)

    def _get_next_frame(self):
        frame = None
        for i in range(EVERY_Nth_FRAME):
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

        H = Human.union(human_old_frame, human_new_frame)

        x_min, x_max, w = H.x_min, H.x_max, H.w
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

    def find_peaks(self):
        threshold = THRESHOLD_FOR_PEAKS_DETECTION
        first_try = True
        max_num_of_keyframe = MAX_KEYFRAME_PER_SEC * self.num_of_frames / self.fps
        max_num_of_keyframe = max(max_num_of_keyframe, 1)
        while (len(self.peaks) > max_num_of_keyframe or first_try) \
                and threshold <= 1:
            self.peaks = peakutils.indexes(np.array(self.diffs),
                                           thres=threshold,
                                           min_dist=self.frames_between_keyframes)
            if len(self.peaks) == 0 or len(self.diffs) - self.peaks[-1] > self.frames_between_keyframes:
                self.peaks = np.append(self.peaks, [len(self.diffs) - 1])
            self.peaks = list(filter(lambda peak: not self._last_sec_video_is_bad(peak), self.peaks))
            threshold += THRESHOLD_DELTA
            first_try = False

    def _last_sec_video_is_bad(self, ind):
        if ind < self.frames_between_keyframes:
            return True
        video_frame = 0
        human_in_center_frames = 0
        for i in range(1, self.frames_between_keyframes):
            if self.diffs[ind - i] > self.bottom_line:
                video_frame += 1

            H = self.humans[ind - i]
            if H.w > 0:
                center = H.x_min + H.w / 2
                if CENTER_LEFT_BORDER * self.shape.width <= center <= CENTER_RIGHT_BORDER * self.shape.width:
                    human_in_center_frames += 1
        return max(video_frame, human_in_center_frames) > self.frames_between_keyframes // 2

    def crate_summary(self):
        self.cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)
        old_dir = os.getcwd()
        new_dir = os.path.join(old_dir, PATH_FOR_IMGS)
        if not os.path.exists(new_dir):
            os.mkdir(new_dir)
        os.chdir(new_dir)

        i = 0
        peaks_ptr = 0
        keyframes_with_timestamp = []
        frames_buffer = [0] * int(self.fps * 1)
        frames_buffer_ptr = 0
        while self.cap.isOpened() and peaks_ptr < len(self.peaks):
            ret, frame = self.cap.read()
            if not ret:
                break
            frames_buffer[frames_buffer_ptr] = frame
            frames_buffer_ptr += 1
            frames_buffer_ptr %= len(frames_buffer)
            if i == self.peaks[peaks_ptr] * EVERY_Nth_FRAME:
                name = IMG_NAME_TEMPLATE.format(number=i)
                keyframes_with_timestamp.append([name, i / self.fps])
                ind_in_buffer = (frames_buffer_ptr + len(frames_buffer)) % len(frames_buffer)
                cv2.imwrite(name, frames_buffer[ind_in_buffer])
                peaks_ptr += 1
            i += 1
        os.chdir(old_dir)
        return keyframes_with_timestamp

    def plot_graphs(self):
        fig = plt.figure()
        xs = range(len(self.diffs))
        humans = [int(bool(H.w)) * max(self.diffs) / 2 for H in self.humans]
        xs_h = range(len(humans))

        plt.plot(xs, self.diffs, 'b-',
                 xs, [np.mean(self.diffs)] * len(xs), 'g-',
                 xs, [self.bottom_line] * len(xs), 'g--',
                 xs_h, humans, 'r-',
                 self.peaks, [max(self.diffs) / 2] * len(self.peaks), 'g^')
        fig.savefig(DIFFS_PNG_NAME)

'''
try:
    with open('diffs', 'rb') as f:
        s.diffs = pickle.load(f)
        s.bottom_line = float(np.mean(s.diffs) * BOTTOM_LINE_COEF)
    with open('humans', 'rb') as f:
        s.humans = pickle.load(f)
except FileNotFoundError:
    s.compute_diffs()
    with open('diffs', 'wb') as f:
        pickle.dump(s.diffs, f)
    with open('humans', 'wb') as f:
        pickle.dump(s.humans, f)
'''

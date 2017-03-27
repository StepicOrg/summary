import io
from typing import Iterable, Tuple

import cv2

from exceptions import CreateSynopsisError
from .image_uploaders import ImageUploaderBase, Url


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

    def upload_keyframes(self, keyframe_positions: Iterable[int]) -> Iterable[Tuple[Url, float]]:
        frame_ptr = 0
        self.cap.set(cv2.CAP_PROP_POS_AVI_RATIO, frame_ptr)

        keyframe_positions = sorted(keyframe_positions)
        keyframes_src_with_timestamp = []
        for keyframe_position in keyframe_positions:
            while self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret:
                    raise CreateSynopsisError('Wrong keyframe_position = {}'.format(keyframe_position))

                if frame_ptr == keyframe_position:
                    image_bytes = io.BytesIO(cv2.imencode('.png', frame)[1].tostring())
                    image_src = self.image_uploader.upload(image_bytes)
                    keyframes_src_with_timestamp.append((image_src, keyframe_position / self.fps))
        return keyframes_src_with_timestamp

    def get_keyframes(self) -> Iterable[int]:
        raise NotImplementedError()

    def get_keyframes_src_with_timestamp(self):
        keyframe_positions = self.get_keyframes()
        keyframes_src_with_timestamp = self.upload_keyframes(keyframe_positions)
        return keyframes_src_with_timestamp


class VideoRecognitionNaive(VideoRecognitionBase):
    def get_keyframes(self) -> Iterable[int]:
        pass

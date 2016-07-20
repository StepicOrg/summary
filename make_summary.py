import os
import sys
import subprocess

from constants import FFMPEG_EXTRACT_AUDIO, BOTTOM_LINE_COEF
from utils import make_summary
from video_recognition import VideoRecognition as VR
from audio_recognition import AudioRecognition as AR

import numpy as np
import pickle
vr = VR(sys.argv)

try:
    with open('diffs', 'rb') as f:
        vr.diffs = pickle.load(f)
        vr.bottom_line = float(np.mean(vr.diffs) * BOTTOM_LINE_COEF)
    with open('humans', 'rb') as f:
        vr.humans = pickle.load(f)
except FileNotFoundError:
    vr.compute_diffs()
    with open('diffs', 'wb') as f:
        pickle.dump(vr.diffs, f)
    with open('humans', 'wb') as f:
        pickle.dump(vr.humans, f)

vr.find_peaks()
vr.plot_graphs()
keyframes = vr.crate_summary()

file_name = os.path.splitext(sys.argv[1])[0]
command = FFMPEG_EXTRACT_AUDIO.format(input_video='../{}'.format(sys.argv[1]),
                                      output_audio=file_name)
status_code = subprocess.call(command, shell=True)
print('ffmpeg status_code = ', status_code)

ar = AR("{}.wav".format(file_name))

try:
    with open('recognized_audio', 'rb') as f:
        recognized_audio = pickle.load(f)
except FileNotFoundError:
    recognized_audio = ar.recognize()
    with open('recognized_audio', 'wb') as f:
        pickle.dump(recognized_audio, f)

make_summary(keyframes, recognized_audio)

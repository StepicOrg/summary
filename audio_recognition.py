import os

from pydub import AudioSegment
import math
import requests
import xml.etree.ElementTree as ET

from constants import REQUEST_URL
from utils import mkdir_and_cd


class AudioRecognition:
    file_name = None
    _audio_segment = None

    def __init__(self, file_name):
        self.file_name = file_name
        self._audio_segment = AudioSegment.from_file(file_name)

    def recognize(self):
        old_dir = os.getcwd()
        mkdir_and_cd(self.file_name, 'audio_chunks')
        audio_chunks = self._split_to_chunks()
        audio_chunk_names = self._save_audio_chunks(audio_chunks)
        recognized_audio = self._recognize_chunks(audio_chunk_names)
        os.chdir(old_dir)
        return recognized_audio

    def _split_to_chunks(self):
        arr = [x if not math.isinf(x) else 0 for x in
               map(lambda item: -item.dBFS, self._audio_segment)]
        ptr = 0
        max_len_of_chunk = 19500
        audio_chunks = []
        while len(arr) > ptr + max_len_of_chunk:
            left = ptr + int(max_len_of_chunk * 0.75)
            right = ptr + max_len_of_chunk
            ind = arr.index(max(arr[left:right]), left, right)
            audio_chunks.append((ptr, ind))
            ptr = ind
        audio_chunks.append((ptr, len(arr) - 1))
        return audio_chunks

    def _save_audio_chunks(self, audio_chunks):
        audio_chunk_names = []
        for i, (start, end) in enumerate(audio_chunks):
            name = 'audio_chunk_{}.mp3'.format(i)
            print("exporting", name)
            self._audio_segment[start:end].export(name, format='mp3')
            audio_chunk_names.append((start, end, name))
        return audio_chunk_names

    @staticmethod
    def _recognize_chunks(audio_chunk_names):
        recognized_audio = []
        for (start, end, name) in audio_chunk_names:
            text = ''
            with open(name, 'rb') as f:
                response = requests.post(REQUEST_URL, data=f, headers={'Content-Type': 'audio/x-mpeg-3'})
                print('status_code = ', response.status_code)
                if response.status_code == 200:
                    xml = response.text
                    root = ET.fromstring(xml)
                    if root.attrib['success'] == '1':
                        text = root[0].text
            recognized_audio.append((start/1000, end/1000, text))
        return recognized_audio

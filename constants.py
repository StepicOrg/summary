EVERY_Nth_FRAME = 3
BOTTOM_LINE_COEF = 3

TIME_BETWEEN_KEYFRAMES = 4
THRESHOLD_FOR_PEAKS_DETECTION = 0.08
THRESHOLD_DELTA = 0.02
MAX_KEYFRAME_PER_MIN = 4

MAX_KEYFRAME_PER_SEC = MAX_KEYFRAME_PER_MIN / 60
SUMMARY_TEMPLATE = 'summary.html'
SUMMARY_FILENAME = 'summary.html'

# for detectMultiScale
SCALE_FACTOR = 1.05
MIN_SIZE_COEF = 5

CENTER_LEFT_BORDER = 0.4
CENTER_RIGHT_BORDER = 0.6

PATH_FOR_IMGS = 'img'
IMG_NAME_TEMPLATE = '{number}.png'

DIFFS_PNG_NAME = 'diffs.png'

# YandexSpeechKit
from secret import key, UUID

URL = 'https://asr.yandex.net/asr_xml'
topic = 'notes'
lang = 'ru-RU'
REQUEST_URL = '{url}?uuid={UUID}&key={key}&topic={topic}&lang={lang}'.format(url=URL,
                                                                             UUID=UUID,
                                                                             key=key,
                                                                             topic=topic,
                                                                             lang=lang)

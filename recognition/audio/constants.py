class Language(object):
    RUSSIAN = 0
    ENGLISH = 1

YANDEX_SPEECH_KIT_REQUEST_URL = 'https://asr.yandex.net/asr_xml?uuid=ead56f704a7311e6beb89e71128cae77' \
                                '&key={key}&topic=notes&lang={lang}'

RECOGNIZE_TEXT_TEMPLATE = '[{min_start:02}:{sec_start:02} - {min_end:02}:{sec_end:02}] {text}'
AUDIO_IS_NOT_RECOGNIZED = '* Audio is not recognized *'
MS_IN_SEC = 1000
SEC_IN_MIN = 60
FFMPEG_EXTRACT_AUDIO = 'ffmpeg -loglevel quiet -y -i "{input_video}" -ab 160k -ac 2 -ar 44100 -vn "{output_audio}"'

import textwrap

FRAME_PERIOD = 3
BOTTOM_LINE_COEF = 3

TIME_BETWEEN_KEYFRAMES = 4
THRESHOLD_FOR_PEAKS_DETECTION = 0.08
THRESHOLD_DELTA = 0.02
MAX_KEYFRAME_PER_MIN = 4
MAX_KEYFRAME_PER_SEC = MAX_KEYFRAME_PER_MIN / 60

SCALE_FACTOR = 1.05
MIN_SIZE_COEF = 5

CENTER_LEFT_BORDER = 0.4
CENTER_RIGHT_BORDER = 0.6

IMG_NAME_TEMPLATE = '{number}.png'
UPLOADCARE_URL_TO_UPLOAD = 'https://upload.uploadcare.com/base/'

YANDEX_SPEECH_KIT_REQUEST_URL = 'https://asr.yandex.net/asr_xml?uuid=ead56f704a7311e6beb89e71128cae77' \
                                '&key={key}&topic=notes&lang={lang}'

RECOGNIZE_TEXT_TEMPLATE = '[{min_start:02}:{sec_start:02} - {min_end:02}:{sec_end:02}] {text}'
AUDIO_IS_NOT_RECOGNIZED = '* Audio is not recognized *'
MS_IN_SEC = 1000
SEC_IN_MIN = 60
FFMPEG_EXTRACT_AUDIO = 'ffmpeg -loglevel quiet -y -i "{input_video}" -ab 160k -ac 2 -ar 44100 -vn "{output_audio}"'
WKHTMLTOPDF = 'wkhtmltopdf "{in_html}" "{out_pdf}"'
GHOSTSCRIPT = 'gs -sDEVICE=pdfwrite -dNOPAUSE -dBATCH -dSAFER -sOutputFile="{out_file}" {in_files}'

VIDEOS_DOWNLOAD_MAX_SIZE = 500 * 1024 * 1024
VIDEOS_DOWNLOAD_CHUNK_SIZE = 1024 * 1024


class ContentType(object):
    IMG = 1
    TEXT = 2


class SynopsisType(object):
    STEP = 1
    LESSON = 2
    COURSE = 3

    ALL_TYPES = (STEP, LESSON, COURSE)

COURSE_PAGE_TITLE_TEMPLATE = "Category:{title} ({id})"
COURSE_PAGE_TEXT_TEMPLATE = textwrap.dedent("""\
                              Page for course "{title}" with id = {id}
                              {stepik_base}/course/{id}
                              [[Category:Courses]]
                              """)
COURSE_PAGE_SUMMARY_TEMPLATE = 'Create page for course id={id}'

LESSON_PAGE_TITLE_TEMPLATE = "Category:{title} ({id})"
LESSON_PAGE_TEXT_TEMPLATE = textwrap.dedent("""\
                              Page for lesson "{title}" with id = {id}
                              {stepik_base}/lesson/{id}
                              [[Category:Lessons]]
                              """)
LESSON_PAGE_SUMMARY_TEMPLATE = 'Create page for lesson id={id}'

STEP_PAGE_TITLE_TEMPLATE = 'Step {position} ({id})'
STEP_PAGE_TEXT_TEMPLATE = textwrap.dedent("""\
                            {content}
                            [[Category:Steps]]
                            [[{lesson}]]
                            """)
STEP_PAGE_SUMMARY_TEMPLATE = 'Create page for step id={id}'

EMPTY_STEP_TEXT = 'Empty step'

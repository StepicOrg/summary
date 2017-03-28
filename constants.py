import textwrap

FFMPEG_EXTRACT_AUDIO = 'ffmpeg -loglevel quiet -y -i "{input_video}" -ab 160k -ac 2 -ar 44100 -vn "{output_audio}"'
WKHTMLTOPDF = 'wkhtmltopdf "{in_html}" "{out_pdf}"'
GHOSTSCRIPT = 'gs -sDEVICE=pdfwrite -dNOPAUSE -dBATCH -dSAFER -sOutputFile="{out_file}" {in_files}'

VIDEOS_DOWNLOAD_MAX_SIZE = 5 * 1024 * 1024 * 1024
VIDEOS_DOWNLOAD_CHUNK_SIZE = 1024 * 1024


class SynopsisType(object):
    STEP = 1
    LESSON = 2
    SECTION = 3
    COURSE = 4

    ALL_TYPES = (STEP, LESSON, SECTION, COURSE)

COURSE_PAGE_TITLE_TEMPLATE = "Category:{title} (C-{id})"
COURSE_PAGE_TEXT_TEMPLATE = textwrap.dedent("""\
                              Page for course "{title}" with id = {id}

                              {stepik_base}/course/{id}

                              {{{{#categorytree:{{{{PAGENAME}}}}}}}}
                              [[Category:Courses]]
                              """)
COURSE_PAGE_SUMMARY_TEMPLATE = 'Create page for course id={id}'

SECTION_PAGE_TITLE_TEMPLATE = "Category:{title} (M-{id})"
SECTION_PAGE_TEXT_TEMPLATE = textwrap.dedent("""\
                              Page for module "{title}" with id = {id}

                              {{{{#categorytree:{{{{PAGENAME}}}}}}}}
                              [[Category:Modules]]
                              """)
SECTION_PAGE_SUMMARY_TEMPLATE = 'Create page for section id={id}'

LESSON_PAGE_TITLE_TEMPLATE = "Category:{title} (L-{id})"
LESSON_PAGE_TEXT_TEMPLATE = textwrap.dedent("""\
                              Page for lesson "{title}" with id = {id}

                              {stepik_base}/lesson/{id}

                              {{{{#categorytree:{{{{PAGENAME}}}}}}}}
                              [[Category:Lessons]]
                              """)
LESSON_PAGE_SUMMARY_TEMPLATE = 'Create page for lesson id={id}'

STEP_PAGE_TITLE_TEMPLATE = 'Step {position} (S-{id})'
STEP_PAGE_TEXT_TEMPLATE = textwrap.dedent("""\
                            Step on Stepik: {stepik_base}/lesson/{lesson_id}/step/{position}

                            {content}

                            [[Category:Steps]]
                            [[{lesson}|{position:>3}]]
                            """)
STEP_PAGE_SUMMARY_TEMPLATE = 'Create page for step id={id}'

EMPTY_STEP_TEXT = 'Empty step'

SINGLE_DOLLAR_TO_MATH_PATTERN = r'(?<![\\\$])(?:\$)((?:[^\\\$]|\\.)+)(?:\$)(?!\$)'
SINGLE_DOLLAR_TO_MATH_REPLACE = r'<math>\1</math>'
DOUBLE_DOLLAR_TO_MATH_PATTERN = r'(?<![\\\$])(?:\$\$)((?:[^\\\$]|\\.)+)(?:\$\$)(?!\$)'
DOUBLE_DOLLAR_TO_MATH_REPLACE = r'\n\n<math>\1</math>\n\n'

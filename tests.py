import json
import os
from unittest import TestCase
from unittest.mock import patch

import re
import requests
from tornado.testing import AsyncHTTPTestCase

from constants import (ContentType, SynopsisType, SINGLE_DOLLAR_TO_MATH_PATTERN,
                       SINGLE_DOLLAR_TO_MATH_REPLACE, DOUBLE_DOLLAR_TO_MATH_PATTERN,
                       DOUBLE_DOLLAR_TO_MATH_REPLACE)
from utils import save_synopsis_for_lesson_to_wiki
from webserver import make_app

app = make_app()
app.listen(8888)
os.environ['ASYNC_TEST_TIMEOUT'] = '200'


class FunctionalTest(AsyncHTTPTestCase):
    def assertPhraseInSynopsis(self, phrase, synopsis):
        for step_with_content in synopsis['steps']:
            for content_item in step_with_content['content']:
                if content_item['type'] == ContentType.TEXT and phrase in content_item['content']:
                    return
        assert False

    def assertSynopsisHasImg(self, synopsis):
        for step_with_content in synopsis['steps']:
            for content_item in step_with_content['content']:
                if content_item['type'] == ContentType.IMG:
                    return
        assert False

    class NewPool(object):
        @staticmethod
        def submit(fun, *args):
            fun(*args)

    def get_app(self):
        return app

    @patch('tasks.pool', new=NewPool())
    @patch('tasks.save_synopsis_to_wiki')
    # LONG test, ~1min
    def test_recognize(self, new_save_synopsis_to_wiki):
        real_step_id = 6950
        post_args = {
            'type': SynopsisType.STEP,
            'pk': real_step_id
        }
        self.fetch('/synopsis', method='POST', body=json.dumps(post_args))

        self.assertTrue(new_save_synopsis_to_wiki.called)

        args = new_save_synopsis_to_wiki.call_args[1]
        synopsis = args['synopsis']

        self.assertPhraseInSynopsis('мультипарадигменный', synopsis)
        self.assertPhraseInSynopsis('низкоуровневый', synopsis)
        self.assertPhraseInSynopsis('статически типизированный', synopsis)
        self.assertPhraseInSynopsis('компилируемый', synopsis)

        self.assertSynopsisHasImg(synopsis)

    @patch('tasks.pool', new=NewPool())
    @patch('tasks.save_synopsis_to_wiki')
    def test_with_correct_args(self, new_save_synopsis_to_wiki):
        real_lesson_id = 532
        real_step_id = 2827
        post_args = {
            'type': SynopsisType.STEP,
            'pk': real_step_id,
        }
        self.fetch('/synopsis', method='POST', body=json.dumps(post_args))
        args = new_save_synopsis_to_wiki.call_args[1]
        synopsis = args['synopsis']

        result = save_synopsis_for_lesson_to_wiki(synopsis=synopsis)

        self.assertEquals(real_lesson_id, result['wiki_url_lesson']['lesson']['id'])

        lesson_page_url = result['wiki_url_lesson']['url']
        self.assertIsNotNone(lesson_page_url)
        lesson_page = requests.get(url=lesson_page_url)
        self.assertEquals(200, lesson_page.status_code)
        self.assertIn('Характеристики языка C++', lesson_page.text)

        self.assertEquals(1, len(result['wiki_url_steps']))
        step_id = result['wiki_url_steps'][0]['step']['id']
        step_wiki_url = result['wiki_url_steps'][0]['url']
        self.assertEquals(real_step_id, step_id)

        step_page = requests.get(url=step_wiki_url)
        self.assertEquals(200, step_page.status_code)
        self.assertIn('Байки о сложности C++', step_page.text)


class RegexTest(TestCase):
    def check_all_regex_cases(self, cases, pattern, replace):
        for case in cases:
            result = re.sub(pattern, replace, case['text'])
            self.assertEqual(result, case['result'])

    def test_single_dollar_regex(self):
        cases = [
            {
                'text': '$x$',
                'result': '<math>x</math>'
            },
            {
                'text': '$x$ $y$',
                'result': '<math>x</math> <math>y</math>'
            },
            {
                'text': '$x$ $y$ $z$',
                'result': '<math>x</math> <math>y</math> <math>z</math>'
            },
            {
                'text': '$ x \$ y $',
                'result': '<math> x \$ y </math>'
            },
            {
                'text': '$ x $ y $',
                'result': '<math> x </math> y $'
            },
            {
                'text': '$$x$$',
                'result': '$$x$$'
            },
            {
                'text': '$$x$$ $$y$$',
                'result': '$$x$$ $$y$$'
            },
            {
                'text': '$x$$y$',
                'result': '$x$$y$'
            },
            {
                'text': '$$x$',
                'result': '$$x$'
            },
            {
                'text': '$x$$',
                'result': '$x$$'
            },
            {
                'text': '\$x$',
                'result': '\$x$'
            },
            {
                'text': '$x\$',
                'result': '$x\$'
            },
        ]

        self.check_all_regex_cases(cases=cases,
                                   pattern=SINGLE_DOLLAR_TO_MATH_PATTERN,
                                   replace=SINGLE_DOLLAR_TO_MATH_REPLACE)

    def test_double_dollar_regex(self):
        cases = [
            {
                'text': '$$x$$',
                'result': '\n\n<math>x</math>\n\n'
            },
            {
                'text': '$$x$$ $$y$$',
                'result': '\n\n<math>x</math>\n\n \n\n<math>y</math>\n\n'
            },
            {
                'text': '$$x$$ $$y$$ $$z$$',
                'result': '\n\n<math>x</math>\n\n \n\n<math>y</math>\n\n \n\n<math>z</math>\n\n'
            },
            {
                'text': '$$ x \$ y $$',
                'result': '\n\n<math> x \$ y </math>\n\n'
            },
            {
                'text': '$$ x $$ y $$',
                'result': '\n\n<math> x </math>\n\n y $$'
            },
            {
                'text': '$$x$$$$y$$',
                'result': '$$x$$$$y$$'
            },
            {
                'text': '$$$x$$',
                'result': '$$$x$$'
            },
            {
                'text': '$$x$$$',
                'result': '$$x$$$'
            },
            {
                'text': '\$$x$$',
                'result': '\$$x$$'
            },
            {
                'text': '$\$x$$',
                'result': '$\$x$$'
            },
            {
                'text': '$$x\$$',
                'result': '$$x\$$'
            },
            {
                'text': '$$x$\$',
                'result': '$$x$\$'
            },
        ]

        self.check_all_regex_cases(cases=cases,
                                   pattern=DOUBLE_DOLLAR_TO_MATH_PATTERN,
                                   replace=DOUBLE_DOLLAR_TO_MATH_REPLACE)

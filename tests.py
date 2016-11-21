import os
from unittest.mock import patch

import requests
from tornado.testing import AsyncHTTPTestCase
from urllib3.request import urlencode

from constants import ContentType
from webserver import make_app

app = make_app()
app.listen(8888)
os.environ['ASYNC_TEST_TIMEOUT'] = '200'


class FunctionalTest(AsyncHTTPTestCase):
    def assertPhraseInResult(self, phrase, result):
        for step_synopsis in result['synopsis_by_steps']:
            for content_item in step_synopsis['content']:
                if content_item['type'] == ContentType.TEXT and phrase in content_item['content']:
                    return
        assert False

    def assertResultHasImg(self, result):
        for step_synopsis in result['synopsis_by_steps']:
            for content_item in step_synopsis['content']:
                if content_item['type'] == ContentType.IMG:
                    return
        assert False

    class NewPool(object):
        @staticmethod
        def submit(fun, args):
            fun(args)

    def get_app(self):
        return app

    @patch('tasks.pool', new=NewPool())
    @patch('tasks.post_result_on_wiki')
    # LONG test, ~1min
    def test_recognize(self, new_post_result_on_wiki):
        post_args = {
            'lesson_id': '532',
            'step_number': '2'
        }
        self.fetch('/', method='POST', body=urlencode(post_args))

        self.assertTrue(new_post_result_on_wiki.called)

        args = new_post_result_on_wiki.call_args[1]
        result = args['result']

        self.assertPhraseInResult('мультипарадигменный', result)
        self.assertPhraseInResult('низкоуровневый', result)
        self.assertPhraseInResult('статически типизированный', result)
        self.assertPhraseInResult('компилируемый', result)

        self.assertResultHasImg(result)

    @patch('tasks.pool', new=NewPool())
    @patch('utils.StepikClient.post_results')
    def test_with_correct_args(self, new_post_results):
        post_args = {
            'lesson_id': '532',
            'step_number': '3'
        }
        self.fetch('/', method='POST', body=urlencode(post_args))
        args = new_post_results.call_args[1]
        status = args['status']
        result = args['result']

        self.assertTrue(status)

        self.assertEquals(1, len(result['lesson_wiki_urls']))
        self.assertEquals(post_args['lesson_id'], result['lesson_wiki_urls'][0]['pk'])

        lesson_page_url = result['lesson_wiki_urls'][0]['wiki_url']
        self.assertIsNotNone(lesson_page_url)
        lesson_page = requests.get(url=lesson_page_url)
        self.assertEquals(200, lesson_page.status_code)
        self.assertIn('Характеристики языка C++', lesson_page.text)

        self.assertEquals(1, len(result['step_wiki_urls']))
        step_id = result['step_wiki_urls'][0]['pk']
        step_wiki_url = result['step_wiki_urls'][0]['wiki_url']
        self.assertEquals(2827, step_id)

        step_page = requests.get(url=step_wiki_url)
        self.assertEquals(200, step_page.status_code)
        self.assertIn('Байки о сложности C++', step_page.text)

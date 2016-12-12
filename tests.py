import json
import os
from unittest.mock import patch

import requests
from tornado.testing import AsyncHTTPTestCase

from constants import ContentType, SynopsisType
from webserver import make_app

app = make_app()
app.listen(8888)
os.environ['ASYNC_TEST_TIMEOUT'] = '200'


class FunctionalTest(AsyncHTTPTestCase):
    def assertPhraseInResult(self, phrase, synopsis):
        for step_with_content in synopsis['steps']:
            for content_item in step_with_content['content']:
                if content_item['type'] == ContentType.TEXT and phrase in content_item['content']:
                    return
        assert False

    def assertResultHasImg(self, synopsis):
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

        self.assertPhraseInResult('мультипарадигменный', synopsis)
        self.assertPhraseInResult('низкоуровневый', synopsis)
        self.assertPhraseInResult('статически типизированный', synopsis)
        self.assertPhraseInResult('компилируемый', synopsis)

        self.assertResultHasImg(synopsis)

    @patch('tasks.pool', new=NewPool())
    @patch('utils.StepikClient.post_results')
    def test_with_correct_args(self, new_post_results):
        real_lesson_id = 532
        real_step_id = 2827
        post_args = {
            'type': SynopsisType.STEP,
            'pk': real_step_id,
        }
        self.fetch('/', method='POST', body=json.dumps(post_args))
        args = new_post_results.call_args[1]
        status = args['status']
        result = args['result']

        self.assertTrue(status)

        self.assertEquals(1, len(result['lesson_wiki_urls']))
        self.assertEquals(real_lesson_id, result['lesson_wiki_urls'][0]['pk'])

        lesson_page_url = result['lesson_wiki_urls'][0]['wiki_url']
        self.assertIsNotNone(lesson_page_url)
        lesson_page = requests.get(url=lesson_page_url)
        self.assertEquals(200, lesson_page.status_code)
        self.assertIn('Характеристики языка C++', lesson_page.text)

        self.assertEquals(1, len(result['step_wiki_urls']))
        step_id = result['step_wiki_urls'][0]['pk']
        step_wiki_url = result['step_wiki_urls'][0]['wiki_url']
        self.assertEquals(real_step_id, step_id)

        step_page = requests.get(url=step_wiki_url)
        self.assertEquals(200, step_page.status_code)
        self.assertIn('Байки о сложности C++', step_page.text)

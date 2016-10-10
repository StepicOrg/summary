import json
import os
from unittest.mock import patch

from tornado.testing import AsyncHTTPTestCase
from urllib3.request import urlencode

from constants import IS_TEXT, IS_FRAME
from webserver import make_app

app = make_app()
app.listen(8888)
os.environ['ASYNC_TEST_TIMEOUT'] = '200'


class FunctionalTest(AsyncHTTPTestCase):
    def assertPhraseInResult(self, phrase, result):
        for synopsis_for_step in result['synopsis_by_steps']:
            for step_id, synopsis in synopsis_for_step.items():
                for content_obj in synopsis:
                    for content_type, content in content_obj.items():
                        if content_type == IS_TEXT and phrase in content:
                            return
        assert False

    def assertResultHasImg(self, result):
        for synopsis_for_step in result['synopsis_by_steps']:
            for step_id, synopsis in synopsis_for_step.items():
                for content_obj in synopsis:
                    for content_type, content in content_obj.items():
                        if content_type == IS_FRAME:
                            return
        assert False

    class NewPool(object):
        @staticmethod
        def submit(fun, args):
            fun(args)

    def get_app(self):
        return app

    @patch('tasks.pool', new=NewPool())
    @patch('tasks.send_response')
    def test_with_correct_args(self, new_send_response):
        post_args = {
            'lesson_id': '532',
            'step_number': '2'
        }
        self.fetch('/', method='POST', body=urlencode(post_args))
        status, result_json = new_send_response.call_args[0]
        result = json.loads(result_json)

        self.assertTrue(status)

        self.assertPhraseInResult('мультипарадигменный', result)
        self.assertPhraseInResult('низкоуровневый', result)
        self.assertPhraseInResult('статически типизированный', result)
        self.assertPhraseInResult('компилируемый', result)

        self.assertResultHasImg(result)

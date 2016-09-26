import os
from unittest.mock import patch

from tornado.testing import AsyncHTTPTestCase
from urllib3.request import urlencode

from secret import CLIENT_ID, CLIENT_SECRET, UPLOAD_CARE_PUB_KEY, YANDEX_SPEECH_KIT_KEY
from webserver import make_app

app = make_app()
app.listen(8888)
os.environ['ASYNC_TEST_TIMEOUT'] = '200'


class FunctionalTest(AsyncHTTPTestCase):
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
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'upload_care_pub_key': UPLOAD_CARE_PUB_KEY,
            'yandex_speech_kit_key': YANDEX_SPEECH_KIT_KEY,
            'lesson_id': '532',
            'step_number': '2'
        }
        self.fetch('/', method='POST', body=urlencode(post_args))
        status, _ = list(new_send_response.call_args)
        self.assertTrue(status)

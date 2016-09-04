import logging

import tornado.ioloop
import tornado.web

from tasks import submit
from utils import Args

logger = logging.getLogger(__name__)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        raise tornado.web.HTTPError(403)

    def post(self, *args, **kwargs):
        try:
            step_number = self.get_argument('step_number')
        except:
            step_number = None

        arguments = Args(client_id=self.get_argument('client_id'),
                         client_secret=self.get_argument('client_secret'),
                         upload_care_pub_key=self.get_argument('upload_care_pub_key'),
                         yandex_speech_kit_key=self.get_argument('yandex_speech_kit_key'),
                         lesson_id=self.get_argument('lesson_id'),
                         step_number=step_number)

        submit(arguments)
        self.set_status(200)


def make_app():
    return tornado.web.Application([
        (r'/', MainHandler),
    ])


if __name__ == '__main__':
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()

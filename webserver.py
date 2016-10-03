import logging

import tornado.ioloop
import tornado.web

import settings
from tasks import submit_create_synopsis_task
from utils import Args, send_response

logger = logging.getLogger(__name__)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        raise tornado.web.HTTPError(403)

    def post(self, *args, **kwargs):
        try:
            step_number = self.get_argument('step_number', default=None)
            step_number = int(step_number) if step_number else None
            arguments = Args(client_id=settings.CLIENT_ID,
                             client_secret=settings.CLIENT_SECRET,
                             upload_care_pub_key=settings.UPLOAD_CARE_PUB_KEY,
                             yandex_speech_kit_key=settings.YANDEX_SPEECH_KIT_KEY,
                             lesson_id=self.get_argument('lesson_id'),
                             step_number=step_number)
        except (tornado.web.MissingArgumentError, ValueError) as err:
            send_response(False, err)
            return

        submit_create_synopsis_task(arguments)
        self.set_status(200)


def make_app():
    return tornado.web.Application([
        (r'/', MainHandler),
    ])


if __name__ == '__main__':
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()

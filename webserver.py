import logging

import tornado.escape
import tornado.ioloop
import tornado.web

import settings
from tasks import submit_create_synopsis_task
from utils import StepikClient, validate_synopsis_request

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stepik_client = None


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        raise tornado.web.HTTPError(403)

    def post(self, *args, **kwargs):
        try:
            logger.info(self.request.body)
            data = tornado.escape.json_decode(self.request.body)
            if not validate_synopsis_request(data):
                self.set_status(400)
                return
        except (TypeError, ValueError):
            self.set_status(400)
            return

        submit_create_synopsis_task(stepik_client, data)
        self.set_status(200)


def make_app():
    global stepik_client
    stepik_client = StepikClient(client_id=settings.STEPIK_CLIENT_ID,
                                 client_secret=settings.STEPIK_CLIENT_SECRET)
    return tornado.web.Application([
        (r'/synopsis', MainHandler),
    ])


if __name__ == '__main__':
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()

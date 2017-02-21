import logging

import tornado.escape
import tornado.ioloop
import tornado.web

import settings
from tasks import submit_create_synopsis_task
from utils import StepikClient, validate_synopsis_request

logging.basicConfig(format='[%(asctime)s]%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        raise tornado.web.HTTPError(403)

    def post(self, *args, **kwargs):
        try:
            logger.info('received request: %s\nbody: %s', self.request, self.request.body)
            data = tornado.escape.json_decode(self.request.body)
            if not validate_synopsis_request(data):
                logger.error('invalid request data')
                self.set_status(400)
                return
        except (TypeError, ValueError):
            logger.error('request must be in json format')
            self.set_status(400)
            return

        submit_create_synopsis_task(data)
        self.set_status(200)


def make_app():
    return tornado.web.Application([
        (r'/synopsis', MainHandler),
    ])


if __name__ == '__main__':
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()

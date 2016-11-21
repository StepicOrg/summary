import logging

import tornado.ioloop
import tornado.web

import settings
from tasks import submit_create_synopsis_task
from utils import Args, StepikClient

logger = logging.getLogger(__name__)
stepik_client = None


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        raise tornado.web.HTTPError(403)

    def post(self, *args, **kwargs):
        try:
            step_number = self.get_argument('step_number', default=None)
            step_number = int(step_number) if step_number else None
            arguments = Args(stepik_client=stepik_client,
                             lesson_id=self.get_argument('lesson_id'),
                             step_number=step_number)
        except (tornado.web.MissingArgumentError, ValueError) as err:
            stepik_client.post_results(False, err)
            return

        submit_create_synopsis_task(arguments)
        self.set_status(200)


def make_app():
    global stepik_client
    stepik_client = StepikClient(client_id=settings.STEPIK_CLIENT_ID,
                                 client_secret=settings.STEPIK_CLIENT_SECRET)
    return tornado.web.Application([
        (r'/', MainHandler),
    ])


if __name__ == '__main__':
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()

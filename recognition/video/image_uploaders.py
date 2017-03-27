import io

from constants import UPLOADCARE_URL_TO_UPLOAD
from exceptions import CreateSynopsisError
from recognition.utils import get_session_with_retries
from settings import UPLOAD_CARE_PUB_KEY

Url = str


class ImageUploaderBase(object):
    session = None

    def __init__(self):
        self.session = get_session_with_retries()

    def upload(self, image: io.BytesIO) -> Url:
        raise NotImplementedError()


class ImageUploaderUploadcare(ImageUploaderBase):
    def upload(self, image: io.BytesIO) -> Url:
        data = {
            'UPLOADCARE_PUB_KEY': UPLOAD_CARE_PUB_KEY,
            'UPLOADCARE_STORE': 1
        }

        response = self.session.post(url=UPLOADCARE_URL_TO_UPLOAD,
                                     files={'file': image},
                                     data=data)

        if not response:
            raise CreateSynopsisError('Failed to upload image, status code: {status_code}'
                                      .format(status_code=response.status_code))

        return 'https://ucarecdn.com/{uuid}/'.format(uuid=response.json()['file'])

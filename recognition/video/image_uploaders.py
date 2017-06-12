import io

from exceptions import CreateSynopsisError
from .constants import UPLOADCARE_URL_TO_UPLOAD
from ..utils import get_session_with_retries


class ImageSaverBase(object):
    def save(self, image: io.BytesIO, position: int) -> str:
        raise NotImplementedError()


class ImageSaverUploadcare(ImageSaverBase):
    def __init__(self, pub_key):
        super().__init__()
        self.session = get_session_with_retries()
        self.pub_key = pub_key

    def save(self, image: io.BytesIO, position: int) -> str:
        data = {
            'UPLOADCARE_PUB_KEY': self.pub_key,
            'UPLOADCARE_STORE': 1
        }

        response = self.session.post(url=UPLOADCARE_URL_TO_UPLOAD,
                                     files={'file': image},
                                     data=data)

        if not response:
            raise CreateSynopsisError('Failed to upload image, status code: {status_code}'
                                      .format(status_code=response.status_code))

        return 'https://ucarecdn.com/{uuid}/'.format(uuid=response.json()['file'])


class ImageSaverLocal(ImageSaverBase):
    def __init__(self, base_path):
        super().__init__()
        self.base_path = base_path

    def save(self, image: io.BytesIO, position: int) -> str:
        filename = '{}/{}.png'.format(self.base_path, position)
        with open(filename, 'wb') as file:
            file.write(image.getvalue())
        return filename

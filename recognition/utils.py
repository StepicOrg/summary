from typing import Iterable

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3 import Retry


def get_session_with_retries(number_of_retries: int = 5,
                             backoff_factor: float = 0.2,
                             status_forcelist: Iterable[int] = {500, 502, 503, 504},
                             prefix: str ='https://') -> requests.Session:
    session = requests.session()
    retries = Retry(total=number_of_retries,
                    backoff_factor=backoff_factor,
                    status_forcelist=status_forcelist)
    session.mount(prefix, HTTPAdapter(max_retries=retries))
    return session

import json
import requests
from requests.auth import HTTPBasicAuth
from utils import (get_lesson_page, parse_arguments, get_step_block, make_synopsis_from_video)
from constants import IS_TEXT, STEPIK_BASE_URL


def main():
    args = parse_arguments()

    auth = HTTPBasicAuth(args.client_id, args.client_secret)
    resp = requests.post(url='{base_url}/oauth2/token/'.format(base_url=STEPIK_BASE_URL),
                         data={'grant_type': 'client_credentials'},
                         auth=auth)
    token = json.loads(resp.text)['access_token']

    lesson_page = get_lesson_page(args.lesson_id, token)
    if len(lesson_page['lessons']) == 0:
        print('wrong lesson id')
        return

    lesson = lesson_page['lessons'][0]

    if args.step_number and args.step_number > len(lesson['steps']):
        print('wrong step number')
        return

    steps = [lesson['steps'][args.step_number]] if args.step_number else lesson['steps']

    result = {'lesson_id': args.lesson_id,
              'synopsis_by_steps': []}

    for step in steps:
        block = get_step_block(step, token)

        if block['text']:
            content = [{IS_TEXT: block['text']}, ]
        else:
            content = make_synopsis_from_video(video=block['video'],
                                               upload_care_pub_key=args.upload_care_pub_key,
                                               yandex_speeck_kit_key=args.yandex_speeck_kit_key)

        result['synopsis_by_steps'].append({step: content})

    result_json = json.dumps(result, ensure_ascii=False).encode('utf-8')

    with open('result.txt', 'wb') as f:
        f.write(result_json)


if __name__ == "__main__":
    main()

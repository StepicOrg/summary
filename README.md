## Summary
Autogenerating summary from video course

## How to use it:

- `git clone https://github.com/StepicOrg/summary.git`

-   - `cd summary`
    - `docker build -t synopsis -f Dockerfile .`
    - `docker run -w=/home/synopsis -ti synopsis python3 make_synopsis.py -c=CLIENT_ID -s=CLIENT_SECRET -i=LESSON_ID -u=UPLOADCARE_KEY -y=YANDEX_SPEECH_KIT_KEY [-n=STEP_NUMBER]`
    - `docker cp $(docker ps -alq):/home/synopsis/result.txt result.txt`

- check `result.txt`

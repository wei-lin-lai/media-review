# Media Review

A Python script that uses Gemini to review AI-generated videos and photos, then posts the results to Discord.

I made this for the HEX training API assignment. At work we generate a lot of video and images with AI, and someone has to watch every clip and look for problems like broken hands, flicker or warped logos. This script does a first pass so the team knows where to look.

It has two modes:

- **video**: Gemini watches a video and lists the problems it finds, with timecodes and how to fix them. You can also add notes from a person (a supervisor or teammate) in a text file, and they get merged into the same list.
- **photos**: You point it at a folder and type what you're looking for, like "blurry". Gemini checks each photo, and the ones that match get copied into a separate folder.

The results show up in the terminal, get saved in `reports/`, and get posted to a Discord channel.

## APIs used

- **Gemini (Vertex AI)** to review the videos and photos. Uses a Google Cloud service account file.
- **Discord webhook** to post the results to a channel.

I'm using Discord for now. Later this should send comments to Frame.io instead, once we have API access.

## Installation (Mac)

Clone the repo:

```bash
git clone https://github.com/wei-lin-lai/media-review.git
cd media-review
```

Make a virtual environment and turn it on:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` at the start of the line. If you open a new terminal, run the `source` line again.

Install the packages:

```bash
pip install -r requirements.txt
```

## Keys

Make a folder called `keys` and put two files in it:

```
keys/
├── service.json
└── discord.json
```

- `service.json` is the Google Cloud service account file.
- `discord.json` holds your Discord webhook URL. Copy `example_discord.json`, rename it to `discord.json`, and paste your URL in.

To get a webhook URL in Discord: go to the channel settings, then Integrations > Webhooks > New Webhook > Copy Webhook URL.

The `keys` folder is in `.gitignore`, so it won't get uploaded. Don't share these files.

## How to run

Video:

```bash
python media_review.py video videos/shot01.mp4
```

Video with notes from a person:

```bash
python media_review.py video videos/shot01.mp4 example_notes.txt
```

You can also add the prompt that was used to make the video, and Gemini will check if the video matches it:

```bash
python media_review.py video videos/shot01.mp4 example_notes.txt "a woman pours coffee in a sunny kitchen"
```

Photos:

```bash
python media_review.py photos photos/ "blurry"
python media_review.py photos photos/ "someone has their eyes closed"
```

Photo types that work: `.jpg`, `.jpeg`, `.png`, `.webp`

## Notes file

One note per line, written like this:

```
00:02 | Supervisor | logo on the cup should face the camera
00:05 | the left hand looks too small
```

The name is optional. If there's no name, it shows up as "Reviewer". Lines starting with `#` are ignored. See `example_notes.txt`.

## What you get

Video:
- The list of problems and notes in the terminal, sorted by time
- `reports/<video name>_review.txt` and `.json`
- A Discord message with the list and the `.txt` file attached

Photos:
- The matching photos in the terminal, with how confident Gemini is and why
- Copies of those photos in `reports/<folder name>_flagged/` (the originals stay where they are)
- `reports/<folder name>_review.txt` and `.json`
- A Discord message with the results

## Things to know

- Files over 20 MB get skipped. Most short AI clips and photos are way under that.
- Photo mode sends one request per photo, so try a small folder first.
- Gemini isn't perfect. It can miss things or flag stuff that's fine, which is why the notes from people are there too.
- The model name is at the top of `media_review.py` if you need to change it.
- `videos/`, `photos/` and `reports/` are in `.gitignore`, so footage doesn't get uploaded.

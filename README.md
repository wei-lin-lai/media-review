# Media Review

A Python workflow that reviews AI generated videos (from Veo, Seedance, etc.) and photos.

**Video mode**
1. **AI check:** Gemini watches the video and lists problems (deformed hands, flicker, warped logos, things that don't match the prompt), each with a timecode and a suggested fix.
2. **Reviewer notes:** a supervisor or teammate can add their own notes with a timecode in a text file. Their notes go into the same list as the AI notes.
3. **Output:** one list of what to change before re-generating.

**Photo mode**
1. You give it a folder of photos and type what you are looking for, for example `"blurry"` or `"eyes closed"`.
2. Gemini checks every photo and answers match or no match, with a confidence score and a short reason.
3. **Output:** the matching photos are copied into a separate folder, with a list of why each one was picked.

Results from both modes are printed in the terminal, saved to `reports/`, and posted to a Discord channel.

## APIs

| API | What it does | Needs |
|---|---|---|
| Gemini on Vertex AI | Reviews the video or photos | Google Cloud service account (`keys/service.json`) with Vertex AI enabled. Billed to that Google Cloud project. |
| Discord webhook | Posts the results to a channel | A webhook URL from the channel settings (`keys/discord.json`). Free. Keep the URL private. |

Discord is used for testing. The plan is to send video reviews to Frame.io as timecoded comments once Frame.io API access is available. The sending step is its own function (`send_to_discord`), so it can be swapped out.

## Installation (Mac)

1. Clone the repo and go into the folder:

```bash
git clone <repo url>
cd media-review
```

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` at the start of the terminal line. Run `source .venv/bin/activate` again every time you open a new terminal.

3. Install the packages:

```bash
pip install -r requirements.txt
```

## Keys

Make a `keys` folder in the project folder. It is listed in `.gitignore`, so it will not be uploaded.

```
keys/
├── service.json
└── discord.json
```

- `service.json`: the Google Cloud service account file. The project ID is read from this file.
- `discord.json`: copy `example_discord.json`, rename it to `discord.json`, and paste your webhook URL.

To get a Discord webhook URL: open the channel settings, go to **Integrations > Webhooks > New Webhook**, then **Copy Webhook URL**. You need the Manage Webhooks permission on the server.

## Usage

```bash
python media_review.py video <video file> [notes file] ["prompt used for the video"]
python media_review.py photos <photo folder> "what to look for"
```

### Video examples

```bash
# AI review only
python media_review.py video videos/shot01.mp4

# AI review + reviewer notes
python media_review.py video videos/shot01.mp4 example_notes.txt

# AI review + reviewer notes + check against the original prompt
python media_review.py video videos/shot01.mp4 example_notes.txt "a woman pours coffee in a sunny kitchen, slow push in"
```

### Reviewer notes format

One note per line, `time | name | comment`. The name is optional. Lines starting with `#` are skipped.

```
00:02 | Supervisor | logo on the cup should face the camera
00:05 | the left hand looks too small
```

### Photo examples

```bash
python media_review.py photos photos/ "blurry"
python media_review.py photos photos/ "someone has their eyes closed"
python media_review.py photos photos/ "the product logo is not visible"
```

Supported photo types: `.jpg`, `.jpeg`, `.png`, `.webp`

## Output

**Video mode**
- Terminal: the full list, sorted by time
- `reports/<video name>_review.txt`: the same list as a text file
- `reports/<video name>_review.json`: the same data as JSON (for the node in Part 2)
- Discord: a short summary with the full `.txt` report attached

**Photo mode**
- Terminal: the matching photos with confidence and reason
- `reports/<folder name>_flagged/`: copies of the matching photos (the originals are not moved)
- `reports/<folder name>_review.txt` and `.json`: the results
- Discord: a short summary with the full `.txt` report attached

## Notes and limits

- Files are sent inside the request (base64). Google recommends keeping the whole request under 20 MB, so files larger than 20 MB are skipped. Short generated clips and normal photos are usually much smaller.
- Photo mode sends one request per photo. Test with a small folder first.
- The model is set at the top of `media_review.py` (`MODEL = "gemini-3.8-flash"`). Change it there if needed.
- Gemini can miss problems or flag things that are fine. The reviewer notes and the confidence score are there so people can make the final call.
- Do not commit client footage. `videos/`, `photos/` and `reports/` are in `.gitignore`.

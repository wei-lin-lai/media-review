import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import json
import base64
import mimetypes
import os
import shutil
import sys

# ------------------------------------------------------------
# Media Review
# Reviews AI generated videos and photos.
#
# Video mode: Gemini lists every problem with a timecode and a fix.
#             Reviewer notes (with timecodes) are added to the same list.
# Photo mode: You type what to look for (for example "blurry" or "overexposed or too dark").
#             Gemini checks every photo in a folder and the matching
#             photos are copied into a separate folder.
#
# APIs:   1. Gemini on Vertex AI (reviews the media)
#         2. Discord webhook (sends the results to a channel)
# Output: results printed in the terminal, saved to reports/,
#         and posted to Discord
#
# Run:
#   python media_review.py video videos/shot01.mp4
#   python media_review.py video videos/shot01.mp4 notes.txt
#   python media_review.py video videos/shot01.mp4 notes.txt "a woman pours coffee in a sunny kitchen"
#   python media_review.py photos photos/ "blurry"
# ------------------------------------------------------------

MODEL = "gemini-3.8-flash"      # copy the exact ID from Model Garden
LOCATION = "global"
MAX_FILE_MB = 20                 # inline file limit (see README)
PHOTO_TYPES = [".jpg", ".jpeg", ".png", ".webp"]

USAGE = ("Usage:\n"
         "  python media_review.py video <video file> [notes.txt] [\"prompt used for the video\"]\n"
         "  python media_review.py photos <photo folder> \"what to look for\"")


# Google login

def get_google_token():
    creds = service_account.Credentials.from_service_account_file(
        "keys/service.json",
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    creds.refresh(Request())
    return creds.token, creds.project_id


# API 1: send a file + prompt to Gemini

def ask_gemini(token, project_id, file_path, prompt, response_schema):
    my_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    gemini_url = (f"https://aiplatform.googleapis.com/v1/projects/{project_id}"
                  f"/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent")

    # read the file and turn it into base64 text so it can go inside the JSON body
    with open(file_path, "rb") as file:
        file_base64 = base64.b64encode(file.read()).decode("utf-8")

    # some file types are not known by older Python versions, so set them by hand
    extra_types = {".webp": "image/webp", ".mov": "video/mov", ".webm": "video/webm"}
    extension = os.path.splitext(file_path)[1].lower()
    mime_type = extra_types.get(extension) or mimetypes.guess_type(file_path)[0] or "video/mp4"

    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"inlineData": {"mimeType": mime_type, "data": file_base64}},
                {"text": prompt}
            ]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": response_schema
        }
    }

    r = requests.post(gemini_url, headers=my_headers, json=body)

    if r.status_code != 200:
        print(f"Gemini error {r.status_code}: {r.text}")
        return None

    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def file_too_big(file_path):
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        print(f"Skipping {os.path.basename(file_path)}: {size_mb:.1f} MB (limit is {MAX_FILE_MB} MB)")
        return True
    return False


############################################################## 
# VIDEO MODE
############################################################## 

def read_reviewer_notes(notes_path):
    # Each line looks like:  00:05 | Kat | the hand has six fingers
    # The name is optional:  00:05 | the hand has six fingers
    notes = []
    if notes_path is None:
        return notes

    with open(notes_path, "r") as file:
        for line in file:
            line = line.strip()
            if line == "" or line.startswith("#"):
                continue

            parts = [p.strip() for p in line.split("|")]
            if len(parts) == 3:
                time, reviewer, comment = parts
            elif len(parts) == 2:
                time, comment = parts
                reviewer = "Reviewer"
            else:
                print(f"Skipping note (wrong format): {line}")
                continue

            notes.append({
                "start": time,
                "end": time,
                "source": reviewer,
                "severity": "note",
                "category": "reviewer note",
                "problem": comment,
                "fix": ""
            })
    return notes


def review_video(video_path, brief):
    token, project_id = get_google_token()

    prompt = ("You are a senior VFX supervisor reviewing an AI generated video before it goes to a client. "
              "Watch the whole video and list every problem that should be fixed or re-generated: "
              "deformed hands, fingers, faces or bodies; objects that morph, appear or disappear; flicker or jitter; "
              "impossible physics; warped or misspelled text and logos; continuity errors; unstable camera motion; "
              "lighting or color shifts. For each problem give the start and end time as MM:SS, a category, "
              "a severity (high = must fix before client, medium = should fix, low = minor polish), "
              "what is wrong, and a practical fix. Do not invent problems. If the video is clean, return an empty list.")
    if brief:
        prompt += f" The prompt used to generate this video was: {brief}. Also flag anything that does not match it."

    # the shape of the answer we want back from Gemini
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "summary": {"type": "STRING"},
            "issues": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {"type": "STRING"},
                        "end": {"type": "STRING"},
                        "category": {"type": "STRING"},
                        "severity": {"type": "STRING", "enum": ["high", "medium", "low"]},
                        "problem": {"type": "STRING"},
                        "fix": {"type": "STRING"}
                    },
                    "required": ["start", "end", "category", "severity", "problem", "fix"]
                }
            }
        },
        "required": ["summary", "issues"]
    }

    print("Sending video to Gemini...")
    review = ask_gemini(token, project_id, video_path, prompt, response_schema)
    if review is None:
        sys.exit()

    # mark every Gemini issue so we can tell it apart from human notes
    for issue in review["issues"]:
        issue["source"] = "Gemini"

    return review


def time_to_seconds(time):
    # "01:15" -> 75
    try:
        minutes, seconds = time.split(":")[-2:]
        return int(minutes) * 60 + int(float(seconds))
    except ValueError:
        return 0


def build_video_report(video_path, review, notes):
    all_items = review["issues"] + notes
    all_items.sort(key=lambda item: time_to_seconds(item["start"]))

    high_count = len([i for i in review["issues"] if i["severity"] == "high"])

    return {
        "mode": "video",
        "name": os.path.basename(video_path),
        "summary": review["summary"],
        "status": "needs revision" if high_count > 0 else "looks good",
        "ai_issue_count": len(review["issues"]),
        "reviewer_note_count": len(notes),
        "items": all_items
    }


def video_report_to_text(report):
    lines = [
        f"Video Review: {report['name']}",
        f"Status: {report['status']}",
        f"Gemini issues: {report['ai_issue_count']}   Reviewer notes: {report['reviewer_note_count']}",
        "",
        f"Summary: {report['summary']}",
        ""
    ]
    if len(report["items"]) == 0:
        lines.append("No issues found.")

    for number, item in enumerate(report["items"], start=1):
        if item["start"] == item["end"]:
            time = item["start"]
        else:
            time = f"{item['start']}-{item['end']}"
        lines.append(f"{number}. [{time}] ({item['source']}, {item['severity']}) {item['problem']}")
        if item["fix"]:
            lines.append(f"   Fix: {item['fix']}")
    return "\n".join(lines)


def video_discord_message(report):
    lines = [
        f"**Video Review: {report['name']}**",
        f"Status: **{report['status']}**",
        f"Gemini issues: {report['ai_issue_count']} | Reviewer notes: {report['reviewer_note_count']}",
        f"{report['summary']}",
        ""
    ]

    # list every item so people can see who said what without opening the file
    for number, item in enumerate(report["items"], start=1):
        if item["start"] == item["end"]:
            time = item["start"]
        else:
            time = f"{item['start']}-{item['end']}"

        if item["source"] == "Gemini":
            who = f"🤖 Gemini ({item['severity']})"
        else:
            who = f"👤 {item['source']}"

        lines.append(f"{number}. `{time}` {who}: {item['problem']}")

    return "\n".join(lines)


############################################################## 
# PHOTO MODE
############################################################## 

def review_photos(folder, look_for):
    token, project_id = get_google_token()

    prompt = (f"Look at this photo. Does it match this description: \"{look_for}\"? "
              "Answer match true or false, a confidence from 0 to 100, and a short reason.")

    response_schema = {
        "type": "OBJECT",
        "properties": {
            "match": {"type": "BOOLEAN"},
            "confidence": {"type": "INTEGER"},
            "reason": {"type": "STRING"}
        },
        "required": ["match", "confidence", "reason"]
    }

    photo_names = sorted([f for f in os.listdir(folder)
                          if os.path.splitext(f)[1].lower() in PHOTO_TYPES])

    if len(photo_names) == 0:
        print(f"No photos found in {folder} (looking for {', '.join(PHOTO_TYPES)})")
        sys.exit()

    # copy matching photos into reports/<folder name>_flagged/
    flagged_folder = f"reports/{os.path.basename(os.path.normpath(folder))}_flagged"
    os.makedirs(flagged_folder, exist_ok=True)

    results = []
    for number, name in enumerate(photo_names, start=1):
        path = os.path.join(folder, name)
        if file_too_big(path):
            continue

        print(f"Checking photo {number}/{len(photo_names)}: {name}")
        answer = ask_gemini(token, project_id, path, prompt, response_schema)
        if answer is None:
            continue

        answer["photo"] = name
        results.append(answer)

        if answer["match"]:
            shutil.copy(path, flagged_folder)

    flagged = [r for r in results if r["match"]]

    return {
        "mode": "photos",
        "name": os.path.basename(os.path.normpath(folder)),
        "look_for": look_for,
        "checked_count": len(results),
        "flagged_count": len(flagged),
        "flagged_folder": flagged_folder,
        "items": results
    }


def photo_report_to_text(report):
    lines = [
        f"Photo Review: {report['name']}",
        f"Looking for: {report['look_for']}",
        f"Checked: {report['checked_count']}   Matches: {report['flagged_count']}",
        f"Matching photos copied to: {report['flagged_folder']}",
        ""
    ]
    flagged = [r for r in report["items"] if r["match"]]
    if len(flagged) == 0:
        lines.append("No matching photos found.")

    for number, item in enumerate(flagged, start=1):
        lines.append(f"{number}. {item['photo']} ({item['confidence']}%) {item['reason']}")
    return "\n".join(lines)


def photo_discord_message(report):
    flagged = [r["photo"] for r in report["items"] if r["match"]]
    return (f"**Photo Review: {report['name']}**\n"
            f"Looking for: **{report['look_for']}**\n"
            f"Checked: {report['checked_count']} | Matches: {report['flagged_count']}\n"
            f"{', '.join(flagged)}")


############################################################## 
# SAVE AND SEND (used by both modes)
############################################################## 

def save_report(report, text):
    os.makedirs("reports", exist_ok=True)
    name = os.path.splitext(report["name"])[0]

    json_path = f"reports/{name}_review.json"
    with open(json_path, "w") as file:
        json.dump(report, file, indent=2)

    txt_path = f"reports/{name}_review.txt"
    with open(txt_path, "w") as file:
        file.write(text)

    return txt_path


# API 2: send the results to Discord 

def send_to_discord(message, txt_path):
    with open("keys/discord.json", "r") as file:
        webhook_url = json.load(file)["webhook_url"]

    # Discord messages can be up to 2000 characters, so keep the message short
    # and attach the full report as a file
    message = message[:1900]

    with open(txt_path, "rb") as file:
        r = requests.post(
            webhook_url,
            data={"payload_json": json.dumps({"content": message})},
            files={"files[0]": (os.path.basename(txt_path), file)}
        )

    if r.status_code in (200, 204):
        print("Sent to Discord.")
    else:
        print(f"Discord error {r.status_code}: {r.text}")


############################################################## 
# RUN
############################################################## 

if __name__ == "__main__":
    # sys.argv[1] is the mode (video or photos), sys.argv[2] is the file or folder
    if len(sys.argv) < 3:
        print(USAGE)
        sys.exit()

    mode = sys.argv[1]

    if mode == "video":
        video_path = sys.argv[2]
        notes_path = sys.argv[3] if len(sys.argv) > 3 else None
        brief = sys.argv[4] if len(sys.argv) > 4 else ""

        if not os.path.isfile(video_path):
            print(f"Video not found: {video_path}")
            sys.exit()
        if file_too_big(video_path):
            sys.exit()

        notes = read_reviewer_notes(notes_path)
        review = review_video(video_path, brief)
        report = build_video_report(video_path, review, notes)
        text = video_report_to_text(report)
        message = video_discord_message(report)

    elif mode == "photos":
        if len(sys.argv) < 4:
            print("Please add what to look for, for example: python media_review.py photos photos/ \"blurry\"")
            sys.exit()

        folder = sys.argv[2]
        look_for = sys.argv[3]

        if not os.path.isdir(folder):
            print(f"Folder not found: {folder}")
            sys.exit()

        report = review_photos(folder, look_for)
        text = photo_report_to_text(report)
        message = photo_discord_message(report)

    else:
        print(USAGE)
        sys.exit()

    print()
    print(text)
    print()

    txt_path = save_report(report, text)
    print(f"Saved: {txt_path}")
    send_to_discord(message, txt_path)

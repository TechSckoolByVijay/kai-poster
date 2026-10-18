"""Cloud poster: publish the next queued Kai Short to YouTube Shorts and Instagram Reels (GitHub Actions).

Queue = queue/NNN_EP.json in this repo (posted in filename order) + the matching NNN_EP.mp4 attached to the
GitHub release "queue". Each run does a fresh upload of ONE video, at most MAX_PER_DAY per day (IST).
On success the .json moves to posted/, the release asset is deleted, and posted_log.csv gets a row;
the workflow commits those changes. A platform that fails is retried on the next run (the other is not re-posted).

Env (from repo secrets/variables): YT_TOKEN_JSON, IG_TOKEN, YT_PRIVACY (private until the YouTube audit passes),
MAX_PER_DAY (default 1), GH_TOKEN (for gh release download/delete-asset). TZ=Asia/Kolkata.
Local check: python post.py --check  (validates the json queue only)
"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).parent
QUEUE, POSTED, LOG = HERE / "queue", HERE / "posted", HERE / "posted_log.csv"
IG_API = "https://graph.instagram.com/v23.0"
RELEASE = "queue"
AI_NOTE = "🤖 AI-generated presenter. Real terminal demos."


def log_rows():
    if not LOG.exists():
        return []
    return [p for p in (l.split(",", 3) for l in LOG.read_text(encoding="utf-8").splitlines()[1:]) if len(p) == 4]


def log(name, platform, result):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')},{name},{platform},{json.dumps(result)}\n")


def already_posted(name, platform):
    return any(r[1] == name and r[2] == platform and "FAILED" not in r[3] for r in log_rows())


def posted_today():
    today = dt.date.today().isoformat()
    return {r[1] for r in log_rows() if r[0][:10] == today and "FAILED" not in r[3]}


def post_youtube(mp4, m, privacy):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"]))
    if not creds.valid:
        creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds)
    desc = m["yt_description"]
    if "#shorts" not in desc.lower():
        desc = (desc + "\n\n#Shorts").strip()
    req = yt.videos().insert(
        part="snippet,status",
        body={"snippet": {"title": m["yt_title"][:100], "description": desc, "tags": m.get("yt_tags", []), "categoryId": "27"},
              # "Altered or synthetic content" disclosure: Kai is a realistic AI-generated presenter
              "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}},
        media_body=MediaFileUpload(str(mp4), chunksize=-1, resumable=True, mimetype="video/mp4"))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return f"https://youtube.com/shorts/{resp['id']}"


def post_instagram(mp4, caption, token):
    if AI_NOTE not in caption:
        caption = f"{caption}\n\n{AI_NOTE}"
    # Instagram Login tokens can't do direct file uploads: Instagram fetches the video from a public URL,
    # here the asset on this (public) repo's "queue" release, which is deleted after posting.
    repo = os.environ.get("GITHUB_REPOSITORY", "TechSckoolByVijay/kai-poster")
    url = f"https://github.com/{repo}/releases/download/{RELEASE}/{mp4.name}"
    r = requests.post(f"{IG_API}/me/media", data={"media_type": "REELS", "video_url": url, "caption": caption,
                                                   "is_ai_generated": "true", "access_token": token})
    if not r.ok:
        raise RuntimeError(r.text)
    cid = r.json()["id"]
    for _ in range(60):
        s = requests.get(f"{IG_API}/{cid}", params={"fields": "status_code,status", "access_token": token}).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing failed: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timed out")
    r = requests.post(f"{IG_API}/me/media_publish", data={"creation_id": cid, "access_token": token})
    if not r.ok:
        raise RuntimeError(r.text)
    return r.json()["id"]


def comment_instagram(media_id, text, token):
    """Kai's first comment (question + reason to follow). Pinning is manual: the API can't pin."""
    r = requests.post(f"{IG_API}/{media_id}/comments", data={"message": text, "access_token": token}, timeout=30)
    if not r.ok:
        raise RuntimeError(r.text)
    return r.json().get("id")


def summary(lines):
    """Notes on the GitHub run page (Actions > run): the YouTube link + the comment to paste when publishing."""
    f = os.environ.get("GITHUB_STEP_SUMMARY")
    if f:
        with open(f, "a", encoding="utf-8") as out:
            out.write("\n".join(lines) + "\n")


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    items = sorted(QUEUE.glob("*.json"))
    if a.check:
        for j in items:
            json.loads(j.read_text(encoding="utf-8"))["yt_title"]
        print(f"{len(items)} queued")
        return
    if not items:
        print("Queue empty.")
        return
    meta = items[0]
    name = meta.with_suffix(".mp4").name
    limit = int(os.environ.get("MAX_PER_DAY", "1"))
    done = posted_today()
    if name not in done and len(done) >= limit:
        print(f"Already posted {len(done)} today ({', '.join(sorted(done))}); limit {limit}.")
        return
    m = json.loads(meta.read_text(encoding="utf-8"))
    print(f"Next: {name}  |  {m['yt_title']}")
    if a.dry_run:
        return
    mp4 = HERE / name
    gh("release", "download", RELEASE, "-p", name, "-O", str(mp4), "--clobber")

    ok = True
    if already_posted(name, "youtube"):
        print("YouTube: already posted earlier, skipping")
    else:
        try:
            res = post_youtube(mp4, m, os.environ.get("YT_PRIVACY", "private"))
            print("YouTube:", res); log(name, "youtube", res)
            summary([f"### {name}", f"YouTube (set Public in Studio, then paste the comment): {res}", "",
                     "```", m.get("first_comment", ""), "```"])
        except Exception as e:
            ok = False; print("YouTube FAILED:", e); log(name, "youtube", f"FAILED {e}")
    if already_posted(name, "instagram"):
        print("Instagram: already posted earlier, skipping")
    elif not os.environ.get("IG_TOKEN"):
        print("Instagram: skipped (no IG_TOKEN)")
    else:
        try:
            mid = post_instagram(mp4, m.get("ig_caption", ""), os.environ["IG_TOKEN"])
            res = f"instagram media id {mid}"
            print("Instagram:", res); log(name, "instagram", res)
            if m.get("first_comment"):
                try:
                    cid = comment_instagram(mid, m["first_comment"], os.environ["IG_TOKEN"])
                    print("Instagram first comment:", cid); log(name, "instagram_comment", f"comment id {cid}")
                except Exception as e:   # the Reel is live; a missing comment must not block the queue
                    print("Instagram comment FAILED:", e); log(name, "instagram_comment", f"FAILED {e}")
        except Exception as e:
            ok = False; print("Instagram FAILED:", e); log(name, "instagram", f"FAILED {e}")

    if ok:
        POSTED.mkdir(exist_ok=True)
        shutil.move(str(meta), POSTED / meta.name)
        gh("release", "delete-asset", RELEASE, name, "--yes")
    else:
        print("Left in queue; the failed platform is retried on the next run.")
        sys.exit(1)


if __name__ == "__main__":
    main()

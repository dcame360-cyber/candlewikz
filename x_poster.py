#!/usr/bin/env python3
"""
x_poster.py — post the candlewikz card to X (Twitter).

Strategy: try to upload the image and post it WITH the card. If X blocks the
media upload (the known 403 on some pay-per-use accounts), automatically fall
back to a TEXT-ONLY post so the run still succeeds. Either way you get a post.

NEVER includes a link in the post body (URL posts cost ~13x more).

Required GitHub secrets: X_CLIENT_ID, X_CLIENT_SECRET, X_REFRESH_TOKEN
Dependencies: requests
"""

import os
import base64
import requests

IMG_PATH = "output/latest.png"
CAPTION_PATH = "output/caption.txt"

TOKEN_URL  = "https://api.x.com/2/oauth2/token"
UPLOAD_URL = "https://api.x.com/2/media/upload"
TWEET_URL  = "https://api.x.com/2/tweets"
CAPTION_LIMIT = 270


def refresh_access_token():
    client_id = os.environ["X_CLIENT_ID"]
    client_secret = os.environ["X_CLIENT_SECRET"]
    refresh_token = os.environ["X_REFRESH_TOKEN"]
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    r = requests.post(
        TOKEN_URL,
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token",
              "refresh_token": refresh_token,
              "client_id": client_id},
        timeout=30,
    )
    if r.status_code != 200:
        raise SystemExit(f"Token refresh failed {r.status_code}: {r.text}")
    return r.json()["access_token"]


def try_upload_image(access_token):
    """Returns a media_id, or None if X forbids the upload."""
    try:
        with open(IMG_PATH, "rb") as f:
            files = {"media": ("latest.png", f, "image/png")}
            r = requests.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                data={"media_category": "tweet_image"},
                files=files,
                timeout=60,
            )
    except Exception as e:
        print(f"[media] upload exception: {e}")
        return None

    if r.status_code in (200, 201):
        data = r.json()
        mid = (data.get("id")
               or data.get("media_id_string")
               or data.get("data", {}).get("id")
               or data.get("data", {}).get("media_key"))
        if mid:
            print("[media] upload OK")
            return str(mid)
        print(f"[media] upload OK but no id in response: {data}")
        return None

    print(f"[media] upload not available ({r.status_code}): {r.text[:200]}")
    print("[media] falling back to TEXT-ONLY post.")
    return None


def build_caption():
    with open(CAPTION_PATH) as f:
        text = f.read().strip()
    lines = [ln for ln in text.split("\n") if "http" not in ln.lower()]
    caption = "\n".join(lines).strip()
    return caption[:CAPTION_LIMIT].rstrip()


def post_tweet(access_token, caption, media_id=None):
    payload = {"text": caption}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}
    r = requests.post(
        TWEET_URL,
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise SystemExit(f"Tweet failed {r.status_code}: {r.text}")
    kind = "image + text" if media_id else "text-only"
    print(f"posted to X ({kind}): {r.json()}")


def main():
    if not os.path.exists(CAPTION_PATH):
        raise SystemExit("No caption found - skipping X post.")
    access_token = refresh_access_token()
    media_id = try_upload_image(access_token) if os.path.exists(IMG_PATH) else None
    caption = build_caption()
    post_tweet(access_token, caption, media_id)


if __name__ == "__main__":
    main()

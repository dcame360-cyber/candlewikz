#!/usr/bin/env python3
"""
x_poster.py — post the candlewikz card image + caption to X (Twitter).

Runs in GitHub Actions right after crypto_poster.py renders the card.
Reuses output/latest.png and output/caption.txt.

How auth works here:
- X access tokens expire fast, so every run we exchange the long-lived
  REFRESH token for a fresh access token, then post.
- IMPORTANT: posts go out as image + text, NEVER with a link in the body
  (a URL in the post costs ~13x more). Keep links in your X bio instead.

Required GitHub secrets:
  X_CLIENT_ID, X_CLIENT_SECRET, X_REFRESH_TOKEN

Dependencies: requests
"""

import os
import sys
import json
import base64
import requests

IMG_PATH = "output/latest.png"
CAPTION_PATH = "output/caption.txt"

TOKEN_URL  = "https://api.x.com/2/oauth2/token"
UPLOAD_URL = "https://api.x.com/2/media/upload"   # v2 media upload
TWEET_URL  = "https://api.x.com/2/tweets"

CAPTION_LIMIT = 270   # keep under X's 280 with a safety margin


def refresh_access_token():
    """Exchange the stored refresh token for a fresh access token."""
    client_id = os.environ["X_CLIENT_ID"]
    client_secret = os.environ["X_CLIENT_SECRET"]
    refresh_token = os.environ["X_REFRESH_TOKEN"]

    # confidential client -> HTTP Basic auth with client id:secret
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"Token refresh failed {r.status_code}: {r.text}")
    tok = r.json()
    # NOTE: X may return a NEW refresh token here. If posting later starts
    # failing with 'invalid_grant', regenerate the refresh token and update
    # the X_REFRESH_TOKEN secret. (See README.)
    return tok["access_token"]


def upload_image(access_token):
    with open(IMG_PATH, "rb") as f:
        files = {"media": ("latest.png", f, "image/png")}
        headers = {"Authorization": f"Bearer {access_token}"}
        r = requests.post(UPLOAD_URL, headers=headers, files=files, timeout=60)
    if r.status_code not in (200, 201):
        raise SystemExit(f"Media upload failed {r.status_code}: {r.text}")
    data = r.json()
    media_id = data.get("id") or data.get("media_id_string") or data.get("data", {}).get("id")
    if not media_id:
        raise SystemExit(f"No media id in upload response: {data}")
    return str(media_id)


def build_caption():
    with open(CAPTION_PATH) as f:
        text = f.read().strip()
    # X is short-form: take the first lines (title + prices), drop the long
    # hashtag block, and hard-cap the length. No links by design.
    lines = [ln for ln in text.split("\n") if "http" not in ln.lower()]
    caption = "\n".join(lines).strip()
    if len(caption) > CAPTION_LIMIT:
        caption = caption[:CAPTION_LIMIT].rstrip()
    return caption


def post_tweet(access_token, media_id, caption):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {"text": caption, "media": {"media_ids": [media_id]}}
    r = requests.post(TWEET_URL, headers=headers, data=json.dumps(payload), timeout=30)
    if r.status_code not in (200, 201):
        raise SystemExit(f"Tweet failed {r.status_code}: {r.text}")
    print(f"posted to X: {r.json()}")


def main():
    if not os.path.exists(IMG_PATH):
        raise SystemExit("No card image found - skipping X post.")
    access_token = refresh_access_token()
    media_id = upload_image(access_token)
    caption = build_caption()
    post_tweet(access_token, media_id, caption)


if __name__ == "__main__":
    main()

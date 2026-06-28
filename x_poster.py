#!/usr/bin/env python3
"""
x_poster.py — post the candlewikz card to X, with self-healing token rotation.

X issues a NEW refresh token every time the old one is used (single-use rotation).
This script captures that new token and writes it back to the GitHub Actions secret
X_REFRESH_TOKEN, so the next run always has a valid token. No more manual refreshes.

Tries to post the image; if X blocks the media upload (known 403 on some
accounts), falls back to a text-only post so the run still succeeds.
Never includes a link in the post body (URL posts cost ~13x more).

Required GitHub secrets:
  X_CLIENT_ID, X_CLIENT_SECRET, X_REFRESH_TOKEN
  GH_PAT         - a GitHub fine-grained PAT with Secrets: read & write on this repo
Provided automatically by Actions:
  GITHUB_REPOSITORY  (e.g. "dcame360-cyber/candlewikz")

Dependencies: requests, pynacl
"""

import os
import base64
import requests
from nacl import encoding, public

TOKEN_URL  = "https://api.x.com/2/oauth2/token"
UPLOAD_URL = "https://api.x.com/2/media/upload"
TWEET_URL  = "https://api.x.com/2/tweets"
IMG_PATH = "output/latest.png"
CAPTION_PATH = "output/caption.txt"
CAPTION_LIMIT = 270


def refresh_access_token():
    """Exchange refresh token for an access token; return (access, new_refresh)."""
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
    tok = r.json()
    return tok["access_token"], tok.get("refresh_token")


def save_refresh_token(new_refresh):
    """Write the rotated refresh token back into the GitHub Actions secret."""
    pat = os.environ.get("GH_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (pat and repo and new_refresh):
        print("[token] skipping secret update (missing GH_PAT/repo/token)")
        return
    api = f"https://api.github.com/repos/{repo}/actions/secrets"
    hdr = {"Authorization": f"Bearer {pat}",
           "Accept": "application/vnd.github+json"}
    try:
        key = requests.get(f"{api}/public-key", headers=hdr, timeout=30).json()
        sealed = public.SealedBox(
            public.PublicKey(key["key"].encode(), encoding.Base64Encoder)
        ).encrypt(new_refresh.encode())
        body = {"encrypted_value": base64.b64encode(sealed).decode(),
                "key_id": key["key_id"]}
        resp = requests.put(f"{api}/X_REFRESH_TOKEN", headers=hdr, json=body, timeout=30)
        if resp.status_code in (201, 204):
            print("[token] X_REFRESH_TOKEN updated for next run")
        else:
            print(f"[token] update failed {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[token] update error: {e}")


def try_upload_image(access_token):
    try:
        with open(IMG_PATH, "rb") as f:
            r = requests.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                data={"media_category": "tweet_image"},
                files={"media": ("latest.png", f, "image/png")},
                timeout=60,
            )
    except Exception as e:
        print(f"[media] upload exception: {e}")
        return None
    if r.status_code in (200, 201):
        d = r.json()
        mid = (d.get("id") or d.get("media_id_string")
               or d.get("data", {}).get("id") or d.get("data", {}).get("media_key"))
        if mid:
            print("[media] upload OK")
            return str(mid)
    print(f"[media] upload not available ({r.status_code}): {r.text[:160]} -> text-only")
    return None


def build_caption():
    with open(CAPTION_PATH) as f:
        text = f.read().strip()
    lines = [ln for ln in text.split("\n") if "http" not in ln.lower()]
    return "\n".join(lines).strip()[:CAPTION_LIMIT].rstrip()


def post_tweet(access_token, caption, media_id=None):
    payload = {"text": caption}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}
    r = requests.post(
        TWEET_URL,
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json"},
        json=payload, timeout=30,
    )
    if r.status_code not in (200, 201):
        raise SystemExit(f"Tweet failed {r.status_code}: {r.text}")
    print(f"posted to X ({'image + text' if media_id else 'text-only'}): {r.json()}")


def main():
    if not os.path.exists(CAPTION_PATH):
        raise SystemExit("No caption found - skipping X post.")
    access_token, new_refresh = refresh_access_token()
    # Save the rotated token immediately, before posting, so we never lose it.
    save_refresh_token(new_refresh)
    media_id = try_upload_image(access_token) if os.path.exists(IMG_PATH) else None
    post_tweet(access_token, build_caption(), media_id)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
telegram_poster.py — send the candlewikz daily card + a short extra to Telegram.

Reuses output/latest.png (the rendered card) and output/caption.txt.
Adds a one-line "market mood" extra so the channel offers a little more than
the IG/X posts (the reason people join Telegram).

Required GitHub secrets:
  TELEGRAM_BOT_TOKEN  - from BotFather
  TELEGRAM_CHAT_ID    - your channel username, e.g. @candlewikz
Dependencies: requests
"""

import os
import requests

IMG_PATH = "output/latest.png"
CAPTION_PATH = "output/caption.txt"
TG_CAPTION_LIMIT = 1024  # Telegram photo caption hard limit


def market_mood():
    """Read the caption's % changes and produce a short mood line."""
    try:
        with open(CAPTION_PATH) as f:
            text = f.read()
    except FileNotFoundError:
        return ""
    # pull every percentage like (-1.37%) or (+0.50%)
    changes = []
    for tok in text.replace("(", " ").replace(")", " ").split():
        if tok.endswith("%"):
            try:
                changes.append(float(tok.strip("%+")))
            except ValueError:
                pass
    if not changes:
        return ""
    avg = sum(changes) / len(changes)
    if avg <= -3:   mood = "🕯️ Mood: deep red — candles burning low."
    elif avg < -0.5: mood = "🕯️ Mood: cooling off — soft red across the board."
    elif avg <= 0.5: mood = "🕯️ Mood: flat — the market holding its breath."
    elif avg < 3:    mood = "🕯️ Mood: warming up — green starting to flicker."
    else:            mood = "🕯️ Mood: lit — strong green across the board."
    return mood


def build_caption():
    try:
        with open(CAPTION_PATH) as f:
            base = f.read().strip()
    except FileNotFoundError:
        base = "candlewikz daily"
    mood = market_mood()
    caption = base + ("\n\n" + mood if mood else "")
    return caption[:TG_CAPTION_LIMIT]


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    caption = build_caption()

    if os.path.exists(IMG_PATH):
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(IMG_PATH, "rb") as img:
            r = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": ("latest.png", img, "image/png")},
                timeout=60,
            )
    else:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": caption}, timeout=30)

    if r.status_code != 200:
        raise SystemExit(f"Telegram post failed {r.status_code}: {r.text}")
    print(f"posted to Telegram: ok ({chat_id})")


if __name__ == "__main__":
    main()

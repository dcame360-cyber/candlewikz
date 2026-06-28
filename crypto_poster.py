#!/usr/bin/env python3
"""
crypto_poster.py — candlewikz automated price-card generator + Instagram publisher.

Two subcommands (run by the GitHub Actions workflow, in this order):

    python crypto_poster.py render   # fetch data -> build output/latest.png + caption.txt
    python crypto_poster.py post     # publish output/latest.png to Instagram via Graph API

Why two steps? Instagram's Content Publishing API can only post an image from a
PUBLIC url. So: render -> commit the PNG to your (public) repo -> Instagram fetches
it from the raw GitHub url. The workflow handles the commit + url between these steps.

Dependencies: pillow  (everything else is the Python standard library)
"""

import os
import sys
import json
import time
import datetime as dt
from urllib import request, parse, error

from PIL import Image, ImageDraw, ImageFont

# ============================ CONFIG ========================================
# "fixed"  -> always show FIXED_COINS (your daily BTC/ETH card)
# "top"    -> top TOP_N coins by market cap
# "movers" -> biggest 24h movers, chosen from the top MOVERS_POOL coins
MODE = os.environ.get("CARD_MODE", "fixed")

FIXED_COINS = ["bitcoin", "ethereum"]   # CoinGecko IDs, NOT ticker symbols
TOP_N = 6
MOVERS_N = 5
MOVERS_POOL = 100                        # rank movers within the top-100 (avoids junk low-caps)

VS_CURRENCY = "usd"

# --- candlewikz brand palette ---
BRAND_NAME = os.environ.get("BRAND_NAME", "candlewikz")
ESPRESSO = (26, 21, 16)      # background
PANEL    = (36, 29, 22)      # card panel
IVORY    = (239, 231, 214)   # primary text / candle body
AMBER    = (242, 169, 59)    # ember accent / flame
AMBER_HI = (255, 225, 160)   # inner flame
WICK     = (58, 47, 37)      # burnt wick
MUTED    = (154, 140, 120)   # secondary text
GREEN    = (63, 185, 138)    # price up
RED      = (229, 96, 79)     # price down
DIVIDER  = (54, 45, 35)

SIZE = 1080
OUTPUT_DIR = "output"
IMG_PATH = os.path.join(OUTPUT_DIR, "latest.png")
CAPTION_PATH = os.path.join(OUTPUT_DIR, "caption.txt")

GRAPH_VERSION = "v21.0"
GRAPH_HOST = "graph.instagram.com"   # Instagram-login token host
USER_AGENT = "candlewikz/1.0"

HASHTAG_SETS = [
    "#bitcoin #ethereum #crypto #btc #eth #cryptonews #blockchain",
    "#crypto #cryptocurrency #bitcoin #ethereum #altcoins #defi #web3",
    "#btc #eth #crypto #cryptotrading #investing #hodl #cryptomarket",
]

# ============================ DATA ==========================================

def _get_json(url):
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def fetch_rows():
    base = "https://api.coingecko.com/api/v3/coins/markets"
    if MODE == "fixed":
        ids = ",".join(FIXED_COINS)
        url = f"{base}?vs_currency={VS_CURRENCY}&ids={ids}&price_change_percentage=24h"
        data = _get_json(url)
        order = {cid: i for i, cid in enumerate(FIXED_COINS)}
        data.sort(key=lambda c: order.get(c["id"], 999))
        title, rows = "DAILY PRICES", data
    elif MODE == "top":
        url = (f"{base}?vs_currency={VS_CURRENCY}&order=market_cap_desc"
               f"&per_page={TOP_N}&page=1&price_change_percentage=24h")
        rows, title = _get_json(url), f"TOP {TOP_N} BY MARKET CAP"
    elif MODE == "movers":
        url = (f"{base}?vs_currency={VS_CURRENCY}&order=market_cap_desc"
               f"&per_page={MOVERS_POOL}&page=1&price_change_percentage=24h")
        pool = [c for c in _get_json(url) if c.get("price_change_percentage_24h") is not None]
        pool.sort(key=lambda c: abs(c["price_change_percentage_24h"]), reverse=True)
        rows, title = pool[:MOVERS_N], "BIGGEST MOVERS - 24H"
    else:
        raise SystemExit(f"Unknown CARD_MODE: {MODE!r}")

    out = []
    for c in rows:
        out.append({
            "symbol": (c.get("symbol") or "").upper(),
            "name":   c.get("name") or "",
            "price":  c.get("current_price") or 0.0,
            "change": c.get("price_change_percentage_24h") or 0.0,
        })
    return title, out

# ============================ FORMATTING ====================================

def fmt_price(p):
    if p >= 1000:  return f"${p:,.0f}"
    if p >= 1:     return f"${p:,.2f}"
    if p >= 0.01:  return f"${p:.4f}"
    return f"${p:.6f}"

def fmt_change(c):
    return f"{'+' if c >= 0 else ''}{c:.2f}%"

# ============================ RENDER ========================================

def _font(bold, size):
    for path in (f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
                 f"fonts/{'Bold' if bold else 'Regular'}.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def draw_mark(d, cx, tip_y, h):
    """Draw the candlewikz candle+flame mark. cx = center x, tip_y = top of flame, h = total height."""
    f = h / 156.0
    def P(vx, vy):  # map SVG-viewBox point -> pixel
        return (cx + (vx - 100) * f, tip_y + (vy - 18) * f)
    # lower candlestick wick
    d.line([P(100, 150), P(100, 172)], fill=MUTED, width=max(2, int(4 * f)))
    # candle body
    (bx0, by0), (bx1, by1) = P(76, 88), P(124, 150)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=int(11 * f), fill=IVORY)
    # burnt upper wick
    d.line([P(100, 88), P(100, 62)], fill=WICK, width=max(2, int(4 * f)))
    # flame (outer + inner)
    outer = [P(100,18),P(88,40),P(84,58),P(90,68),P(100,70),P(110,68),P(116,58),P(112,40)]
    inner = [P(100,36),P(95,50),P(96,60),P(100,62),P(104,60),P(105,50)]
    d.polygon(outer, fill=AMBER)
    d.polygon(inner, fill=AMBER_HI)

def render(title, rows):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    img = Image.new("RGB", (SIZE, SIZE), ESPRESSO)
    d = ImageDraw.Draw(img)
    M = 72
    today = dt.datetime.utcnow().strftime("%b %d, %Y").upper()
    d.rounded_rectangle([M, M, SIZE - M, SIZE - M], radius=40, fill=PANEL)
    px = M + 56

    # --- header = mini logo lockup (this is the reshare watermark) ---
    mark_h = 66
    draw_mark(d, px + 22, M + 56, mark_h)
    wx, wy = px + 70, M + 56 + mark_h / 2
    bf = _font(True, 42)
    d.text((wx, wy), "candle", font=bf, fill=IVORY, anchor="lm")
    w1 = d.textlength("candle", font=bf)
    d.text((wx + w1, wy), "wikz", font=bf, fill=AMBER, anchor="lm")
    d.text((SIZE - px, M + 56 + mark_h / 2), today, font=_font(False, 24), fill=MUTED, anchor="rm")

    # --- title ---
    d.text((px, M + 168), title, font=_font(True, 52), fill=IVORY)

    # --- rows ---
    top, bottom = M + 270, SIZE - M - 110
    n = max(len(rows), 1)
    row_h = (bottom - top) / n
    right = SIZE - px
    sym_f, name_f, price_f, chg_f = _font(True,56), _font(False,26), _font(True,50), _font(True,34)
    for i, r in enumerate(rows):
        cy = top + row_h * i + row_h / 2
        d.text((px, cy), r["symbol"], font=sym_f, fill=IVORY, anchor="lm")
        sw = d.textlength(r["symbol"], font=sym_f)
        d.text((px + sw + 18, cy + 6), r["name"], font=name_f, fill=MUTED, anchor="lm")
        col = GREEN if r["change"] >= 0 else RED
        d.text((right, cy), fmt_change(r["change"]), font=chg_f, fill=col, anchor="rm")
        d.text((right - 210, cy), fmt_price(r["price"]), font=price_f, fill=IVORY, anchor="rm")
        if i < n - 1:
            ly = top + row_h * (i + 1)
            d.line([px, ly, right, ly], fill=DIVIDER, width=2)

    # --- footer ---
    d.text((px, SIZE - M - 70), "Not financial advice  ·  data: CoinGecko",
           font=_font(False, 24), fill=MUTED)
    img.save(IMG_PATH, "PNG")
    print(f"wrote {IMG_PATH}")

def build_caption(title, rows):
    today = dt.datetime.utcnow().strftime("%b %d, %Y")
    lines = [f"{title} - {today}", ""]
    for r in rows:
        lines.append(f"{r['symbol']}  {fmt_price(r['price'])}  ({fmt_change(r['change'])})")
    tags = HASHTAG_SETS[dt.datetime.utcnow().timetuple().tm_yday % len(HASHTAG_SETS)]
    lines += ["", "candlewikz - the market, by candlelight", "Not financial advice.", "", tags]
    caption = "\n".join(lines)
    with open(CAPTION_PATH, "w") as f:
        f.write(caption)
    print(f"wrote {CAPTION_PATH}")
    return caption

# ============================ PUBLISH =======================================

def _graph_post(path, params):
    data = parse.urlencode(params).encode()
    req = request.Request(f"https://{GRAPH_HOST}/{GRAPH_VERSION}/{path}",
                          data=data, method="POST", headers={"User-Agent": USER_AGENT})
    try:
        with request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except error.HTTPError as e:
        raise SystemExit(f"Graph API error {e.code}: {e.read().decode()}")

def post():
    token = os.environ["IG_ACCESS_TOKEN"]
    ig_user = os.environ["IG_USER_ID"]
    image_url = f"{os.environ['IMAGE_URL']}?t={int(time.time())}"
    with open(CAPTION_PATH) as f:
        caption = f.read()
    created = _graph_post(f"{ig_user}/media",
                          {"image_url": image_url, "caption": caption, "access_token": token})
    print(f"created container {created['id']}")
    published = _graph_post(f"{ig_user}/media_publish",
                            {"creation_id": created["id"], "access_token": token})
    print(f"published: {published}")

# ============================ MAIN ==========================================

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "render"
    if cmd == "render":
        title, rows = fetch_rows()
        if not rows:
            raise SystemExit("No data returned - skipping (will not post a blank card).")
        render(title, rows)
        build_caption(title, rows)
    elif cmd == "post":
        post()
    else:
        raise SystemExit("usage: crypto_poster.py [render|post]")

if __name__ == "__main__":
    main()

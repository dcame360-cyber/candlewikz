#!/usr/bin/env python3
"""
crypto_poster.py — candlewikz automated card generator + Instagram publisher.

    python crypto_poster.py render   # fetch data -> build output/latest.png + caption.txt
    python crypto_poster.py post     # publish output/latest.png to Instagram via Graph API

CARD_MODE (env) selects the card type:
    fixed   -> BTC + ETH (the signature daily anchor)
    top     -> top N by market cap
    movers  -> biggest 24h movers, split into gainers / losers
    market  -> market overview: total market cap, 24h change, BTC dominance, Fear & Greed

Relevance gate (anti-white-noise): in "movers" mode, if the biggest move is below
MOVERS_MIN_PCT the card auto-falls back to the "fixed" BTC/ETH card instead of
posting an unremarkable movers list. Controlled by env GATE=1 (default on).

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
MODE = os.environ.get("CARD_MODE", "fixed")
GATE = os.environ.get("GATE", "1") == "1"

FIXED_COINS = ["bitcoin", "ethereum"]
TOP_N = 6
MOVERS_N = 6
MOVERS_POOL = 100
MOVERS_MIN_PCT = 5.0

VS_CURRENCY = "usd"

BRAND_NAME = os.environ.get("BRAND_NAME", "candlewikz")
ESPRESSO = (26, 21, 16)
PANEL    = (36, 29, 22)
IVORY    = (239, 231, 214)
AMBER    = (242, 169, 59)
AMBER_HI = (255, 225, 160)
WICK     = (58, 47, 37)
MUTED    = (154, 140, 120)
GREEN    = (63, 185, 138)
RED      = (229, 96, 79)
DIVIDER  = (54, 45, 35)

SIZE = 1080
OUTPUT_DIR = "output"
IMG_PATH = os.path.join(OUTPUT_DIR, "latest.png")
CAPTION_PATH = os.path.join(OUTPUT_DIR, "caption.txt")

GRAPH_VERSION = "v21.0"
GRAPH_HOST = "graph.instagram.com"
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

def _markets(per_page, ids=None):
    base = "https://api.coingecko.com/api/v3/coins/markets"
    q = f"?vs_currency={VS_CURRENCY}&price_change_percentage=24h"
    if ids:
        q += f"&ids={','.join(ids)}"
    else:
        q += f"&order=market_cap_desc&per_page={per_page}&page=1"
    return _get_json(base + q)

def _row(c):
    return {
        "symbol": (c.get("symbol") or "").upper(),
        "name":   c.get("name") or "",
        "price":  c.get("current_price") or 0.0,
        "change": c.get("price_change_percentage_24h") or 0.0,
    }

def fetch_global():
    d = _get_json("https://api.coingecko.com/api/v3/global")["data"]
    return {
        "mcap":   d["total_market_cap"]["usd"],
        "mcap_chg": d.get("market_cap_change_percentage_24h_usd") or 0.0,
        "btc_dom": d["market_cap_percentage"].get("btc") or 0.0,
        "eth_dom": d["market_cap_percentage"].get("eth") or 0.0,
    }

def fetch_fng():
    d = _get_json("https://api.alternative.me/fng/?limit=1")["data"][0]
    return int(d["value"]), d["value_classification"]

def fetch_payload():
    if MODE == "fixed":
        data = _markets(2, ids=FIXED_COINS)
        order = {cid: i for i, cid in enumerate(FIXED_COINS)}
        data.sort(key=lambda c: order.get(c["id"], 999))
        return {"kind": "list", "title": "DAILY PRICES", "rows": [_row(c) for c in data]}

    if MODE == "top":
        data = _markets(TOP_N)
        return {"kind": "list", "title": f"TOP {TOP_N} BY MARKET CAP",
                "rows": [_row(c) for c in data]}

    if MODE == "movers":
        pool = [c for c in _markets(MOVERS_POOL)
                if c.get("price_change_percentage_24h") is not None]
        pool.sort(key=lambda c: c["price_change_percentage_24h"], reverse=True)
        gainers = [_row(c) for c in pool[:MOVERS_N // 2]]
        losers  = [_row(c) for c in pool[-(MOVERS_N // 2):]][::-1]
        biggest = max(abs(gainers[0]["change"]) if gainers else 0,
                      abs(losers[0]["change"]) if losers else 0)
        if GATE and biggest < MOVERS_MIN_PCT:
            print(f"[gate] biggest move {biggest:.1f}% < {MOVERS_MIN_PCT}% -> fallback to fixed")
            data = _markets(2, ids=FIXED_COINS)
            order = {cid: i for i, cid in enumerate(FIXED_COINS)}
            data.sort(key=lambda c: order.get(c["id"], 999))
            return {"kind": "list", "title": "DAILY PRICES", "rows": [_row(c) for c in data]}
        return {"kind": "movers", "title": "BIGGEST MOVERS - 24H",
                "gainers": gainers, "losers": losers}

    if MODE == "market":
        g = fetch_global()
        try:
            fng_val, fng_lbl = fetch_fng()
        except Exception as e:
            print(f"[market] F&G unavailable: {e}")
            fng_val, fng_lbl = None, None
        return {"kind": "market", "title": "MARKET OVERVIEW", "g": g,
                "fng_val": fng_val, "fng_lbl": fng_lbl}

    raise SystemExit(f"Unknown CARD_MODE: {MODE!r}")

# ============================ FORMATTING ====================================

def fmt_price(p):
    if p >= 1000:  return f"${p:,.0f}"
    if p >= 1:     return f"${p:,.2f}"
    if p >= 0.01:  return f"${p:.4f}"
    return f"${p:.6f}"

def fmt_change(c):
    return f"{'+' if c >= 0 else ''}{c:.2f}%"

def fmt_big_usd(v):
    if v >= 1e12: return f"${v/1e12:.2f}T"
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    return f"${v:,.0f}"

# ============================ RENDER ========================================

def _font(bold, size):
    for path in (f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
                 f"fonts/{'Bold' if bold else 'Regular'}.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def draw_mark(d, cx, tip_y, h):
    f = h / 156.0
    def P(vx, vy):
        return (cx + (vx - 100) * f, tip_y + (vy - 18) * f)
    d.line([P(100, 150), P(100, 172)], fill=MUTED, width=max(2, int(4 * f)))
    (bx0, by0), (bx1, by1) = P(76, 88), P(124, 150)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=int(11 * f), fill=IVORY)
    d.line([P(100, 88), P(100, 62)], fill=WICK, width=max(2, int(4 * f)))
    outer = [P(100,18),P(88,40),P(84,58),P(90,68),P(100,70),P(110,68),P(116,58),P(112,40)]
    inner = [P(100,36),P(95,50),P(96,60),P(100,62),P(104,60),P(105,50)]
    d.polygon(outer, fill=AMBER)
    d.polygon(inner, fill=AMBER_HI)

def _canvas():
    img = Image.new("RGB", (SIZE, SIZE), ESPRESSO)
    d = ImageDraw.Draw(img)
    M = 72
    d.rounded_rectangle([M, M, SIZE - M, SIZE - M], radius=40, fill=PANEL)
    return img, d, M

def _header(d, M, title):
    px = M + 56
    today = dt.datetime.utcnow().strftime("%b %d, %Y").upper()
    mark_h = 66
    draw_mark(d, px + 22, M + 56, mark_h)
    wx, wy = px + 70, M + 56 + mark_h / 2
    bf = _font(True, 42)
    d.text((wx, wy), "candle", font=bf, fill=IVORY, anchor="lm")
    w1 = d.textlength("candle", font=bf)
    d.text((wx + w1, wy), "wikz", font=bf, fill=AMBER, anchor="lm")
    d.text((SIZE - px, M + 56 + mark_h / 2), today, font=_font(False, 24), fill=MUTED, anchor="rm")
    d.text((px, M + 168), title, font=_font(True, 52), fill=IVORY)
    return px

def _footer(d, M, note="Not financial advice  -  data: CoinGecko"):
    d.text((M + 56, SIZE - M - 70), note, font=_font(False, 24), fill=MUTED)

def render_list(title, rows):
    img, d, M = _canvas()
    px = _header(d, M, title)
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
    _footer(d, M)
    img.save(IMG_PATH, "PNG"); print(f"wrote {IMG_PATH}")

def render_movers(title, gainers, losers):
    img, d, M = _canvas()
    px = _header(d, M, title)
    right = SIZE - px
    top = M + 248
    colhead_f = _font(True, 30)
    sym_f, chg_f = _font(True, 40), _font(True, 34)

    def block(label, rows, y0, color):
        d.text((px, y0), label, font=colhead_f, fill=color)
        yy = y0 + 88
        rh = 68
        for r in rows:
            d.text((px, yy), r["symbol"], font=sym_f, fill=IVORY, anchor="lm")
            d.text((right, yy), fmt_change(r["change"]), font=chg_f, fill=color, anchor="rm")
            d.text((right - 230, yy), fmt_price(r["price"]), font=_font(True,34), fill=MUTED, anchor="rm")
            yy += rh
        return yy

    y = block("GAINERS", gainers, top, GREEN)
    d.line([px, y + 2, right, y + 2], fill=DIVIDER, width=2)
    block("LOSERS", losers, y + 18, RED)
    _footer(d, M)
    img.save(IMG_PATH, "PNG"); print(f"wrote {IMG_PATH}")

def render_market(title, g, fng_val, fng_lbl):
    img, d, M = _canvas()
    px = _header(d, M, title)
    right = SIZE - px
    label_f = _font(False, 30)
    val_f   = _font(True, 64)
    small_f = _font(True, 36)

    y = M + 320
    d.text((px, y), "Total Market Cap", font=label_f, fill=MUTED, anchor="lm")
    d.text((px, y + 56), fmt_big_usd(g["mcap"]), font=val_f, fill=IVORY, anchor="lm")
    col = GREEN if g["mcap_chg"] >= 0 else RED
    d.text((right, y + 56), fmt_change(g["mcap_chg"]), font=small_f, fill=col, anchor="rm")
    d.line([px, y + 132, right, y + 132], fill=DIVIDER, width=2)

    y2 = y + 168
    d.text((px, y2), "BTC Dominance", font=label_f, fill=MUTED, anchor="lm")
    d.text((right, y2), f"{g['btc_dom']:.1f}%", font=small_f, fill=AMBER, anchor="rm")
    y3 = y2 + 64
    d.text((px, y3), "ETH Dominance", font=label_f, fill=MUTED, anchor="lm")
    d.text((right, y3), f"{g['eth_dom']:.1f}%", font=small_f, fill=IVORY, anchor="rm")
    d.line([px, y3 + 56, right, y3 + 56], fill=DIVIDER, width=2)

    y4 = y3 + 92
    if fng_val is not None:
        d.text((px, y4), "Fear & Greed", font=label_f, fill=MUTED, anchor="lm")
        if fng_val <= 25:   fcol = RED
        elif fng_val < 50:  fcol = (220, 150, 90)
        elif fng_val < 75:  fcol = (180, 200, 110)
        else:               fcol = GREEN
        d.text((px, y4 + 52), f"{fng_val}", font=val_f, fill=fcol, anchor="lm")
        d.text((px + 130, y4 + 70), fng_lbl, font=small_f, fill=fcol, anchor="lm")
    _footer(d, M, "Not financial advice  -  data: CoinGecko, alternative.me")
    img.save(IMG_PATH, "PNG"); print(f"wrote {IMG_PATH}")

# ============================ CAPTION =======================================

def build_caption(payload):
    today = dt.datetime.utcnow().strftime("%b %d, %Y")
    title = payload["title"]
    lines = [f"{title} - {today}", ""]
    if payload["kind"] == "list":
        for r in payload["rows"]:
            lines.append(f"{r['symbol']}  {fmt_price(r['price'])}  ({fmt_change(r['change'])})")
    elif payload["kind"] == "movers":
        lines.append("Gainers:")
        for r in payload["gainers"]:
            lines.append(f"{r['symbol']}  {fmt_change(r['change'])}")
        lines.append("")
        lines.append("Losers:")
        for r in payload["losers"]:
            lines.append(f"{r['symbol']}  {fmt_change(r['change'])}")
    elif payload["kind"] == "market":
        g = payload["g"]
        lines.append(f"Market cap  {fmt_big_usd(g['mcap'])}  ({fmt_change(g['mcap_chg'])})")
        lines.append(f"BTC dominance  {g['btc_dom']:.1f}%")
        if payload["fng_val"] is not None:
            lines.append(f"Fear & Greed  {payload['fng_val']} ({payload['fng_lbl']})")
    tags = HASHTAG_SETS[dt.datetime.utcnow().timetuple().tm_yday % len(HASHTAG_SETS)]
    lines += ["", "candlewikz", "Not financial advice.", "", tags]
    caption = "\n".join(lines)
    with open(CAPTION_PATH, "w") as f:
        f.write(caption)
    print(f"wrote {CAPTION_PATH}")
    return caption

def render_payload(payload):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if payload["kind"] == "list":
        render_list(payload["title"], payload["rows"])
    elif payload["kind"] == "movers":
        render_movers(payload["title"], payload["gainers"], payload["losers"])
    elif payload["kind"] == "market":
        render_market(payload["title"], payload["g"], payload["fng_val"], payload["fng_lbl"])
    else:
        raise SystemExit(f"cannot render kind {payload['kind']!r}")

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
    creation_id = created["id"]
    print(f"created container {creation_id}")
    for _ in range(12):
        time.sleep(5)
        try:
            url = (f"https://{GRAPH_HOST}/{GRAPH_VERSION}/{creation_id}"
                   f"?fields=status_code&access_token={token}")
            req = request.Request(url, headers={"User-Agent": USER_AGENT})
            status = json.loads(request.urlopen(req, timeout=30).read().decode())
            code = status.get("status_code")
            print(f"container status: {code}")
            if code == "FINISHED":
                break
            if code == "ERROR":
                raise SystemExit(f"Container processing failed: {status}")
        except SystemExit:
            raise
        except Exception as e:
            print(f"status check retry: {e}")
    published = _graph_post(f"{ig_user}/media_publish",
                            {"creation_id": creation_id, "access_token": token})
    print(f"published: {published}")

# ============================ SCHEDULE ======================================

# Weekly rotation. Keys = UTC weekday (Mon=0 ... Sun=6). Values = (am_mode, pm_mode).
ROTATION = {
    0: ("market", "movers"),   # Mon
    1: ("fixed",  "movers"),   # Tue
    2: ("market", "top"),      # Wed
    3: ("fixed",  "movers"),   # Thu
    4: ("market", "movers"),   # Fri
    5: ("fixed",  "top"),      # Sat
    6: ("fixed",  "top"),      # Sun
}

def resolve_mode():
    """Pick CARD_MODE from SLOT env (am/pm) + today's UTC weekday."""
    slot = os.environ.get("SLOT", "am").lower()
    wd = dt.datetime.utcnow().weekday()
    am, pm = ROTATION.get(wd, ("fixed", "movers"))
    return pm if slot == "pm" else am

# ============================ MAIN ==========================================

def main():
    global MODE
    cmd = sys.argv[1] if len(sys.argv) > 1 else "render"
    if cmd == "render":
        # If CARD_MODE wasn't explicitly provided, use the weekly rotation.
        if not os.environ.get("CARD_MODE"):
            MODE = resolve_mode()
            print(f"[schedule] SLOT={os.environ.get('SLOT','am')} -> CARD_MODE={MODE}")
        payload = fetch_payload()
        render_payload(payload)
        build_caption(payload)
    elif cmd == "post":
        post()
    else:
        raise SystemExit("usage: crypto_poster.py [render|post]")

if __name__ == "__main__":
    main()

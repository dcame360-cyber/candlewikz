# candlewikz — automated crypto poster

Zero-cost pipeline: GitHub Actions runs daily → fetches prices from CoinGecko →
renders a branded **candlewikz** card (logo watermark baked in) → posts to Instagram
via Meta's Graph API. No server to manage.

## Repo layout
```
your-repo/
├─ crypto_poster.py            # the script (render + post), candlewikz palette + watermark
├─ .github/workflows/post.yml  # the daily cron
└─ output/                     # latest.png + caption.txt get committed here automatically
```
Put `crypto_poster.py` at the repo root; put `post.yml` at `.github/workflows/post.yml`.
**The repo must be Public** (no secrets live in the code — they go in Actions secrets).

## What you control (top of crypto_poster.py)
- `MODE` — `fixed` (daily BTC/ETH), `top` (top N by market cap), `movers` (biggest 24h movers).
  Also set per-run via `CARD_MODE` in the workflow.
- `FIXED_COINS` — CoinGecko **IDs** (`bitcoin`, `ethereum`, `solana`…), not tickers.
- Brand palette + `BRAND_NAME` are already set to candlewikz — no edits needed.

Test the look locally before touching Instagram:
```
pip install pillow
python crypto_poster.py render
open output/latest.png
```

## Instagram setup (the fiddly part — budget your time here)
1. Convert IG to **Business/Creator** and **link it to a Facebook Page**.
2. developers.facebook.com → create a **Business** app → add the **Instagram** product.
3. In Graph API Explorer, generate a token with: `instagram_basic`,
   `instagram_content_publish`, `pages_show_list`. Convert it to a **long-lived** token.
4. Write down **IG_USER_ID** (your IG business account number) and **IG_ACCESS_TOKEN**.
5. Add both as GitHub repo secrets: Settings → Secrets and variables → Actions.
6. Posting to your **own** account usually works while the app stays in Development
   mode — only submit for App Review if a post fails with a permissions error.

Then: Actions tab → **Run workflow** to test → confirm it posts → let the cron run.

## Gotchas that otherwise eat your weekend
- **Public image URL** — IG fetches the card from the raw GitHub url; that's why the repo
  must be public and the workflow commits the PNG. Bump the `sleep 15` if posts go stale.
- **Token expiry = silent breakage** — long-lived tokens last ~60 days, then posting fails
  quietly. Set a phone reminder to refresh. This is the #1 reason these bots die.
- **No blank posts** — if CoinGecko is down, render exits and the run fails loudly instead
  of posting garbage. Intentional.
- **Cron is UTC** — convert your audience's peak local time to UTC.

## Growing past the MVP (rough order of payoff)
1. Daily **Reel** (animated card) — Reels out-reach static posts.
2. A `movers` day + a weekly scoreboard for variety.
3. Cross-post the same output to X, TikTok, YouTube Shorts, Threads.
4. Rotate stats: BTC dominance, Fear & Greed, distance-from-ATH.
5. Once one niche works, clone this pipeline into a separate stocks page.

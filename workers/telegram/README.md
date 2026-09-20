# Instant Telegram replies (Cloudflare Worker)

GitHub Actions cannot reply in real time (minimum schedule is about 5 minutes).
This Worker receives Telegram webhooks and answers **immediately** for:

- Start / Help / Settings / Channel
- Filter button taps (GMP, subscription, board)

**Preview GMP** acknowledges instantly, then GitHub Actions builds the scored list.

## One-time setup

1. Create a free [Cloudflare](https://dash.cloudflare.com/) account.
2. Install Wrangler: `npm i -g wrangler` then `wrangler login`.
3. Create a KV namespace:
   ```bash
   wrangler kv namespace create PREFS
   ```
   Paste the id into `wrangler.toml` (`id` and `preview_id`).
4. From `workers/telegram/`:
   ```bash
   wrangler secret put TELEGRAM_TOKEN
   wrangler secret put CHANNEL_ID
   wrangler secret put WEBHOOK_SECRET
   wrangler secret put EXPORT_SECRET
   wrangler secret put GITHUB_TOKEN
   wrangler secret put GITHUB_REPO
   wrangler deploy
   ```
   `GITHUB_TOKEN` needs `repo` scope (for `repository_dispatch` preview).
   `GITHUB_REPO` looks like `livexaworks/ipodevta`.
5. Point Telegram at the Worker:
   ```bash
   python -m bot.set_webhook set --url https://ipo-devta-bot.<you>.workers.dev
   ```
   (Set matching `WEBHOOK_SECRET` in `.env` if you used one.)
6. Seed existing users from `data/users.json`:
   ```bash
   curl -X POST https://ipo-devta-bot.<you>.workers.dev/seed \
     -H "Authorization: Bearer $EXPORT_SECRET" \
     -H "Content-Type: application/json" \
     --data-binary @data/users.json
   ```
7. GitHub Actions secrets:
   - `TELEGRAM_WEBHOOK=1`
   - `WEBHOOK_BASE_URL=https://ipo-devta-bot.<you>.workers.dev`
   - `EXPORT_SECRET=` (same as Worker)
   - Existing Telegram secrets unchanged

After this, Settings/Help reply instantly. IPO alert/snapshot stay on the weekday schedule.

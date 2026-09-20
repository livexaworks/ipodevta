# Worker (instant replies)

Telegram webhook for Settings, Help, Channel, Feedback, and Preview ack.

Full steps: create KV `PREFS`, set secrets (`TELEGRAM_TOKEN`, `CHANNEL_ID`, `ADMIN_CHAT_ID`, `WEBHOOK_SECRET`, `EXPORT_SECRET`, `GITHUB_TOKEN`, `GITHUB_REPO`), `wrangler deploy`, then:

```bash
python -m bot.set_webhook set --url https://ipo-devta-bot.<you>.workers.dev
```

If IPODevta is already live for you, you do not need this.

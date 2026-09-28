# IPODevta

Clear IPO fill signals on Telegram: 👍 / 👎 with GMP and subscription, using filters you set.

**Already live on Telegram.** Use the existing bot and channel. Do not waste time cloning this just to file IPOs.

Channel: [t.me/ipodevta](https://t.me/ipodevta)

Happy filing. All the best for allotments.

---

## Data source (hybrid)

| Field | Provider |
|-------|----------|
| Calendar, dates, price, lot, **GMP** | [IPO Guru API v2](https://www.ipoguru.in/ipo-gmp-details-developer-api) (server / Actions only) |
| **QIB / NII / Retail / Total** subscription | BSE public bookbuilding JSON APIs (no Guru quota) |

IPO Guru free plan: **10 req/day**, 1/min (budget default = full plan). Typical collect uses **1** Guru call (`/ipos?status=open`); preview/commands use disk cache only.

| When | IPO Guru | BSE |
|------|----------|-----|
| `alert` / `snapshot` / combined daily run | 1× `GET /ipos?status=open` | live + CATDEM |
| Preview / commands | Disk cache only | none |

Set `IPOGURU_API_KEY` in `.env` and as a GitHub Actions secret. Never put the key in the Worker or any browser/mobile client.

---

## Fork

Have another idea? Fork this repo and build your own. Message copy lives mainly in `bot/render.py` and `workers/telegram/worker.js`.

## Run your own

1. Copy `.env.example` → `.env` (Telegram + `IPOGURU_API_KEY`)
2. Add the same secrets on GitHub Actions
3. Deploy the Worker: `workers/telegram/README.md`
4. `python -m pytest`

```bash
python -m bot.run --mode alert      # closing-day posts (1 API call)
python -m bot.run --mode snapshot   # evening book (1 API call)
python -m bot.run --mode preview --chat-id YOUR_ID   # cache only
```

Information only. Not investment advice. Read the RHP. GMP is unofficial grey-market data.

# 🪙 Goodwill Gold

A Google-Lens-style **thrift resale price scanner**. Standing in a Goodwill or thrift
shop, snap a photo of an item (or type the make/model) and instantly get:

- **What it is** — brand, model, key attributes (Claude vision).
- **What condition it's in** — graded with a confidence score.
- **What it's worth** — a live resale **price range** searched across the major
  secondhand "lines" (eBay sold comps, Mercari, Poshmark, Facebook Marketplace, retail).
- **A buy/skip verdict** — *"Steal under $25 — pass over $40"* — plus the comp sources.

When a photo isn't enough to judge condition, it asks for a **specific extra shot**.
When accessories move the value (charger, controllers, lens, original box), it asks
whether they're **included** — then prices accordingly.

## How it works

A mobile-first **PWA** talks to a **FastAPI** backend that runs a two-stage Claude
pipeline:

```
Phone PWA ──(photos + make/model + accessories answer)──▶ POST /api/analyze
   │
   ├─ Stage A · IDENTIFY   (claude-opus-4-8, vision + structured output)
   │     item · condition · needs_more_photos · accessories
   │
   ├─ gate: if more photos / accessories answer needed → return need_more_info
   │
   └─ Stage B · PRICE      (web_search agentic loop → structured summary)
         steal_deal / fair_market / top_resale · verdict · cited sources
```

The endpoint is **iterative**: the app re-submits with added photos and/or the
accessories answer until it can produce a price. Pricing uses Claude's built-in
`web_search` server tool, so there are **no third-party API keys to manage**.

## Project layout

```
backend/
  app.py            FastAPI app: serves the PWA + POST /api/analyze
  claude_client.py  Stage A (identify) + Stage B (price) Claude calls
  schemas.py        request models + JSON Schemas for structured outputs
  prompts.py        system prompts for both stages
frontend/
  index.html app.js styles.css   mobile-first UI (camera capture + manual entry)
  manifest.json service-worker.js icon.svg   PWA install + offline shell
```

## Run it

```bash
pip install -r requirements.txt
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000/** (on your phone, use the machine's LAN IP).

### Configuration

- **Claude credentials.** In the Claude Code web/cloud environment, access is provided
  automatically via `ANTHROPIC_BASE_URL` — nothing to set. Elsewhere, set
  `ANTHROPIC_API_KEY` (see `.env.example`).
- `CLAUDE_MODEL` — defaults to `claude-opus-4-8`.
- `PORT` — defaults to `8000`.

### Quick API check

```bash
# Make/model lookup (no photo) — should return a priced result with sources
curl -s -X POST localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"make_model": "Sony WH-1000XM4 headphones", "notes": "good shape, no case"}' | python -m json.tool
```

## Notes & limits

- Prices are **estimates from live comps** — Claude weighs recent sold listings, but
  always sanity-check high-value flips yourself.
- Photos are resized in-browser before upload to keep requests small.
- This is not affiliated with Goodwill Industries; "Goodwill Gold" is just the project name.

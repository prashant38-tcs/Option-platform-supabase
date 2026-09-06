# Multi-Agent Options Trading Platform

Real-time Next.js dashboard + FastAPI/WebSocket backend for an NSE index
options multi-agent trading system.

## Deployment

**Primary guide (current):** [`SUPABASE_RENDER_DEPLOYMENT.md`](./SUPABASE_RENDER_DEPLOYMENT.md)
-- Supabase for Postgres + Render.com free tier for hosting the backend
and frontend. Read this first; it explains upfront why Supabase alone
cannot host the backend (Edge Functions are Deno-only with hard
CPU/memory/wall-clock limits incompatible with a continuous scheduler +
WebSocket server), and what the actual free-tier tradeoffs are.

A `render.yaml` Blueprint at the repo root lets you deploy both services
in one step via Render's Dashboard -> New -> Blueprint.

## Running locally

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # fill in your real Fyers/Groq/Gemini keys
python scripts/fyers_daily_login.py   # once per trading day
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Or test both together with Docker first:
```bash
touch backend/.fyers_session.json
docker compose up --build
```

Open `http://localhost:3000` for the dashboard and
`http://localhost:8000/docs` for the API reference. The dashboard
connects via WebSocket to stream live agent reasoning, the option
chain, sentiment, candidate strategies, and orders as each cycle runs.

## Architecture summary

Five agents (Data Ingestion, Sentiment, Quant Analytics, Risk Manager,
Execution) run through a LangGraph pipeline, polled continuously by a
background scheduler across NIFTY/BANKNIFTY/FINNIFTY/SENSEX. Three
trading modes -- Advisory (recommendation only), Paper (simulated
fills), and Live (real orders, gated behind a full SEBI compliance
checklist) -- share the same pipeline and risk engine.

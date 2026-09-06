# Deploying with Supabase (Database) + Render (App Hosting)

## Read this first: what Supabase actually can and can't do here

You asked to deploy on Supabase since Railway's free tier is full. Before
building anything, I checked this carefully, because there's a real
architectural mismatch that would waste your time if I didn't flag it
upfront:

**Supabase cannot host this backend.** Supabase's serverless compute
("Edge Functions") only runs Deno/TypeScript/WASM -- there is no official
Python support, and it's been an open, unfulfilled feature request on
Supabase's own GitHub for over a year. Even if this backend were rewritten
in TypeScript, Edge Functions enforce hard limits that are fundamentally
incompatible with what this platform does: 256MB memory, 2 seconds of CPU
time per request, and a wall-clock cap of 150s (free) / 400s (paid) after
which the function is forcibly killed -- including open WebSocket
connections. This backend runs a **continuous** asyncio scheduler polling
every 60 seconds indefinitely, computes Black-Scholes Greeks via scipy,
orchestrates a 5-agent LangGraph pipeline, and holds long-lived WebSocket
connections open to stream live results -- none of that fits inside a
per-request serverless function, regardless of language.

**What Supabase genuinely is good for here:** Postgres. That's it, for
now (this app doesn't use Redis/Auth/Storage yet). Supabase's own
recommended pattern for a Next.js app is to pair it with a *separate*
app host (their docs and quickstarts consistently point to Vercel for
the frontend) -- Supabase provides backend *services* (database, auth,
storage, realtime), not general-purpose app hosting.

**So the actual plan is:** Supabase for Postgres, and **Render.com's free
tier** for hosting both the FastAPI backend and the Next.js frontend --
Render is a genuine, permanent free tier (unlike Fly.io, which killed its
free tier in 2024) that natively supports Python, Docker, and WebSockets.
I verified Render's own docs show a FastAPI + WebSocket example
essentially identical to what this backend needs.

**The honest tradeoff you're accepting:** Render's free tier spins a
service down after 15 minutes with no inbound traffic (HTTP or WebSocket),
and takes about a minute to wake back up. In practice, that means: while
your dashboard's browser tab is open (an active WebSocket connection
counts as traffic), the backend stays warm and the scheduler keeps
cycling. If nobody has the dashboard open, cycles pause after 15 minutes
and resume automatically the next time someone connects. For an
Advisory/Paper-mode personal project, this is a reasonable tradeoff for
$0/month. If you later arm LIVE trading with real open positions, you
should not rely on this free tier -- an unmonitored position with a
paused risk-management loop is a real risk; upgrade to Render's paid
tier (no spin-down) before that point.

---

## Step 1: Create the Supabase project (Postgres only)

1. [supabase.com/dashboard](https://supabase.com/dashboard) -> **New
   Project**. Pick a region close to you (e.g. Singapore/Mumbai if
   available) and set a strong database password -- save it somewhere
   safe, you'll need it in the connection string.
2. Once provisioned, go to **Project Settings -> Database -> Connection
   string**.
3. **Use the Session Pooler connection string, not the Direct
   connection.** Supabase's Direct connection (`db.<ref>.supabase.co:5432`)
   is IPv6-only unless you pay for the IPv4 add-on, and Render's free
   tier is IPv4-only -- so Direct connection will simply fail to
   connect. The Session Pooler
   (`aws-0-<region>.pooler.supabase.com:5432`) is explicitly documented
   by Supabase as the right choice for "persistent backend on IPv4-only
   networks," which is exactly this deployment.
4. Copy that connection string, converting it to the SQLAlchemy-style
   URL this app expects:

   ```
   postgresql+asyncpg://postgres.<project-ref>:<your-db-password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```

   (Supabase shows you the plain `postgresql://` form; just change the
   scheme prefix to `postgresql+asyncpg://` for this app's async
   SQLAlchemy usage, once the persistence layer is wired up. Nothing in
   the current codebase queries the database yet, so this is prep for a
   future step -- you can even skip this entirely for now and leave
   `DATABASE_URL` blank.)

---

## Step 2: Test locally with Docker first (recommended)

Same as before -- catch build issues on your own machine before deploying:

```bash
cp backend/.env.example backend/.env    # fill in real Fyers/Groq/Gemini keys
touch backend/.fyers_session.json
docker compose up --build
```

Open `http://localhost:8000/docs` and `http://localhost:3000` to confirm
both sides come up cleanly.

---

## Step 3: Push to GitHub

```bash
cd options-platform
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Use `git` directly (terminal or VS Code's Source Control panel) rather
than GitHub's web drag-and-drop uploader, which has previously dropped
nested folders silently.

---

## Step 4: Deploy both services to Render via Blueprint

This repo includes a `render.yaml` at the root that defines both
services declaratively -- this is the fastest path, far simpler than
clicking through two separate manual service-creation flows.

1. [dashboard.render.com](https://dashboard.render.com) -> **New ->
   Blueprint**.
2. Connect your GitHub account if you haven't, then select your repo.
   Render detects `render.yaml` automatically.
3. Render will show you both services (`options-platform-backend`,
   `options-platform-frontend`) and prompt you to fill in every
   `sync: false` variable it finds:
   - `FYERS_APP_ID`, `FYERS_SECRET_ID`, `FYERS_REDIRECT_URI` -- your real
     Fyers credentials
   - `GROQ_API_KEY`, `GEMINI_API_KEY` -- your free LLM keys
   - `DATABASE_URL` -- the Supabase Session Pooler string from Step 1
     (or leave blank, see note above)
   - `CORS_ALLOWED_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` -- **leave
     these blank for now**, you'll fill them in during Step 5, since
     neither service's URL exists yet on this first deploy.
4. Click **Apply**. Render builds both Dockerfiles (using each
   service's `rootDir` setting, so `backend/Dockerfile` and
   `frontend/Dockerfile` are picked up correctly) and deploys them.

   If you'd rather not use the Blueprint and instead click through
   manually: **New -> Web Service** twice, once per service, setting
   **Root Directory** to `backend` / `frontend` respectively and
   **Language** to **Docker** for both -- this is exactly what the
   Blueprint does under the hood.

---

## Step 5: Wire up the two URLs (required, second pass)

Once both services have deployed at least once, each gets a real
`https://<service-name>.onrender.com` URL (visible at the top of each
service's dashboard page).

1. Open the **frontend** service -> **Environment** -> set
   `NEXT_PUBLIC_API_BASE_URL` to the backend's URL, e.g.
   `https://options-platform-backend.onrender.com`.
   Since this is a build-time variable baked into the JS bundle, saving
   it triggers Render to rebuild automatically -- confirm via the
   **Events** tab that a new deploy actually started, not just a
   restart.
2. Open the **backend** service -> **Environment** -> set
   `CORS_ALLOWED_ORIGINS` to the frontend's URL, e.g.
   `["https://options-platform-frontend.onrender.com"]` (note: valid
   JSON array syntax, matching how this app already parses
   `SCHEDULER_DEFAULT_UNDERLYINGS`).

---

## Step 6: Complete today's Fyers login against the deployed backend

Same two-endpoint flow built for Railway -- works identically here,
since it's just HTTP against whatever backend URL you have:

```bash
# Step A: get the login URL from the deployed backend
curl https://options-platform-backend.onrender.com/api/fyers/login-url

# Step B: open that URL in your browser, log in to Fyers, complete 2FA,
# then copy the FULL URL your browser lands on after the redirect.

# Step C: hand that back to the deployed backend
curl -X POST https://options-platform-backend.onrender.com/api/fyers/exchange \
  -H "Content-Type: application/json" \
  -d '{"input": "<paste the full redirected URL here>"}'
```

Repeat once per trading day. **Note the free-tier interaction:** if the
backend has spun down from inactivity, that first `curl` call will take
about a minute to respond while it wakes up -- this is normal, not a
failure.

---

## Step 7: Verify

```bash
curl https://options-platform-backend.onrender.com/health
curl https://options-platform-backend.onrender.com/api/scheduler/status
```

Then open the frontend's URL in a browser and confirm the "Live" badge
in the header turns green and the option chain populates after the next
cycle.

---

## Troubleshooting

**Service says "no open ports detected on 0.0.0.0"**
Confirm the service's Language is set to **Docker** (not auto-detected
Python), and that you didn't override the Start Command -- this
Dockerfile's `CMD` already handles `$PORT` binding correctly via shell
expansion (`--port ${PORT:-8000}`); Render sets `PORT` to `10000` by
default. An overridden Start Command that hardcodes a different port is
the most common cause of this error.

**Frontend shows the old backend URL after changing
`NEXT_PUBLIC_API_BASE_URL`**
Confirm the Environment change actually triggered a rebuild (check the
**Events** tab) -- a "Save only" or a plain service restart will not
re-bake the JS bundle; you need a real redeploy.

**Backend takes ~1 minute to respond to the first request after a while**
Expected free-tier spin-down/wake-up behavior, not a bug. Cycles resume
automatically once the service wakes and the WebSocket reconnects.

**`DATABASE_URL` connection fails / times out**
Almost certainly means you copied the Direct connection string
(IPv6-only) instead of the Session Pooler string (IPv4). Re-check Step 1.

**Cycles keep showing "halted -- Fyers session expired"**
You haven't completed Step 6 yet today, or the service redeployed since
your last login (container disk is wiped on redeploy, same as on
Railway) -- redo Step 6.

**Static IP for LIVE trading**
Render's free tier has no static outbound IP option at all (Render's
paid tiers don't offer this either, unlike Railway Pro) -- if you need
LIVE mode's SEBI static-IP requirement satisfied while hosted on Render,
you'll need a third-party static-IP proxy service (e.g. QuotaGuard
Static) and the `OUTBOUND_PROXY_URL` setting already wired into this
backend's `FyersClient` (see `app/core/config.py`).

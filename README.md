# Trading Guardian

A personal forex trading assistant whose primary purpose is **capital preservation
and reducing losses**, not maximizing returns.

It generates transparent **BUY / HOLD / SELL (LONG / FLAT / SHORT)** notifications
for major forex pairs (EURUSD, GBPUSD, USDJPY, XAUUSD, ...) using rule-based
technical logic, enforces strict risk management, and notifies via Telegram.
Intended for **paper/demo trading and personal education only**.

> ⚠️ Most retail forex traders lose money. Spreads, slippage, overfitting and
> execution quality can turn a winning backtest into a losing live system.
> This software is not financial advice. Use paper trading first and never risk
> money you cannot afford to lose.

## Architecture

```
config.yaml  ──►  src/config.py
                      │
   ┌──────────────────┼──────────────────┐
   ▼                  ▼                  ▼
src/data/provider  src/strategy      src/risk
 (CSV / yfinance /  (MTF rules)     (sizing, DD,
  synthetic)                          cooldown)
   │                  │                  │
   └──────► src/backtest/engine ◄────────┘
                      │
   ┌──────────────────┼──────────────────┐
   ▼                  ▼                  ▼
src/execution     src/notify/       scripts/
 (paper broker)    telegram         run_backtest
                                      run_live
```

Modules:

- `src/indicators.py` — EMA, ATR, RSI, ADX (pure pandas, auditable).
- `src/strategy.py` — multi-timeframe rule engine + price-action triggers.
- `src/risk.py` — fixed-fractional sizing, drawdown limits, cooldown, trailing/BE.
- `src/execution.py` — paper broker with spread/slippage simulation.
- `src/backtest/engine.py` + `metrics.py` — event-driven backtester + metrics.
- `src/notify/telegram.py` — Telegram Bot API (no heavy SDK).
- `src/data/provider.py` — CSV / yfinance / synthetic data.

## Strategy rules (v1)

Higher timeframe (e.g. 4H) trend filter:
- UP   if EMA(50) > EMA(200) AND ADX(14) >= 15
- DOWN if EMA(50) < EMA(200) AND ADX(14) >= 15
- else FLAT (no trading)

Lower timeframe (e.g. 15m) entry:
- LONG  if HTF trend UP AND close > EMA(50) AND RSI(14) >= 40 AND bullish PA trigger
- SHORT if HTF trend DOWN AND close < EMA(50) AND RSI(14) <= 60 AND bearish PA trigger
- PA trigger = bullish/bearish engulfing OR pin bar (hammer / shooting star)

Risk:
- Stop loss = 1.5 × ATR(14)
- Take profit = 2.0 × risk (≈ 1:2 R:R)
- Position size = (equity × risk%) / (stop distance in pips × pip value)
- Default risk per trade 0.5%
- Hard stop if daily drawdown ≥ 2% or weekly ≥ 5%
- Cooldown 24h after 3 consecutive losses
- Optional trailing stop and break-even at +1R

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml (balance, pairs, Telegram token, ...)
```

## Run backtest

```bash
python scripts/run_backtest.py
```

Outputs `logs/equity_curve.csv` and `logs/trades.csv` and prints metrics:
win rate, profit factor, expectancy (R), max drawdown, Sharpe.

## Run a paper scan

```bash
python scripts/run_live.py
```

Fetches latest data (yfinance, with synthetic fallback), generates signals,
sizes positions under risk rules, and sends Telegram notifications if enabled.
Wire a real broker adapter before any live use.

## Tests

```bash
pytest -q
```

## Stage 2 — FastAPI backend + Streamlit frontend

### Run backend
```bash
uvicorn backend.main:app --reload --port 8000
```
Docs: http://localhost:8000/docs

### Run frontend
```bash
streamlit run frontend/app.py
```
Dashboard: http://localhost:8501 (assumes backend on localhost:8000)

### Run both with Docker
```bash
docker compose up --build
```

### API endpoints
- `POST /backtest` — metrics, equity curve, trades
- `GET /signals?pairs=EURUSD,GBPUSD` — current BUY/SELL/HOLD signals
- `GET /risk-status` — equity, drawdowns, cooldown, allowed flag
- `GET /config`, `POST /config` — read/update configuration
- `GET /ohlc` — OHLC bars for charting

## Authentication & Multi-user (Stage 3)

- Register/login via `/register` and `/login` (JWT).
- Each user has isolated config, risk state, and backtest results.
- Passwords hashed with bcrypt; tokens signed with `SECRET_KEY` from env.
- User data stored in SQLite (`data/trading_guardian.db` by default).

### Local dev
```bash
cp .env.example .env   # set SECRET_KEY
uvicorn backend.main:app --reload --port 8000
streamlit run frontend/app.py
```

### Deploy with Docker
```bash
cp .env.example .env   # edit secrets
docker compose up --build
```

## Stage 4 additions

- User roles: first registered user becomes `admin`; others `user`. Admin-only `GET /admin/stats`.
- Multiple named configs per user: `GET/POST/DELETE /configs/saved` and `POST /configs/saved/{name}/activate`.
- Streamlit sidebar lets users save/load/delete/switch saved configs.
- Basic per-IP rate limiting (configurable via `RATE_LIMIT_PER_MINUTE`, default 120).

## Deployment

### Local development (without Docker)
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # edit SECRET_KEY at minimum
uvicorn backend.main:app --reload --port 8000
# in another terminal:
streamlit run frontend/app.py
```

### Local development (with Docker)
```bash
cp .env.example .env
docker compose up --build
```
Backend: http://localhost:8000  Frontend: http://localhost:8501

### Deploy to Render
1. Push repo to GitHub.
2. Create a new **Web Service** for the backend:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - Env vars: `SECRET_KEY`, `ENVIRONMENT=production`, `DATABASE_PATH=/var/data/trading_guardian.db`, `CORS_ORIGINS=https://your-frontend.onrender.com`
   - Add a persistent disk mounted at `/var/data` for SQLite.
3. Create a second **Web Service** for the frontend:
   - Build command: `pip install -r requirements.txt`
   - Start command: `streamlit run frontend/app.py --server.port $PORT --server.address 0.0.0.0`
   - Env vars: `API_BASE=https://your-backend.onrender.com`

### Deploy to Railway
1. Create a project from the GitHub repo.
2. Add two services: backend and frontend.
   - Backend start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - Frontend start: `streamlit run frontend/app.py --server.port $PORT --server.address 0.0.0.0`
3. Set environment variables in each service (see `.env.example`).
   - Backend: `SECRET_KEY`, `ENVIRONMENT=production`, `CORS_ORIGINS=https://<frontend-domain>`
   - Frontend: `API_BASE=https://<backend-domain>`

### Deploy to a VPS with Docker Compose
```bash
git clone <your-repo>
cd Trading-guide
cp .env.example .env   # edit secrets and CORS_ORIGINS
docker compose up -d --build
```
Put a reverse proxy (Caddy/Nginx) in front for HTTPS. Keep `SECRET_KEY` and Telegram tokens only in `.env` (never commit).

### Keeping secrets secure
- Never commit `.env` or the SQLite database.
- Rotate `SECRET_KEY` to invalidate all sessions.
- Store Telegram bot tokens only in environment variables, never in code or frontend.

## Warnings

- Backtests ignore real-world frictions imperfectly; always include spread,
  slippage and commission.
- Overfitting is easy: keep rules simple and validate out-of-sample.
- This project ships a paper broker only. No live order routing is implemented.
- Past performance does not predict future results.
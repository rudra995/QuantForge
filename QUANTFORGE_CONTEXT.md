# QuantForge — AI Coding Assistant Context

## What This Is

QuantForge is a production-grade quantitative trading platform built in Python.
It is the lead project on an undergraduate CS resume targeting quant/data engineering internships.
Every architectural decision must reflect real production standards: no shortcuts, no toy patterns.

---

## Project Goal

A full-stack quantitative trading platform that allows users to:
- Define and register trading strategies
- Backtest strategies on historical OHLCV data with realistic simulation (slippage, fees, position sizing)
- Simulate live paper trading via WebSockets
- Monitor portfolio performance and risk metrics in real time
- Use an AI (RAG) layer for strategy explanation and optimization
- Deploy as containerized microservices on Kubernetes

---

## Non-Negotiable Architecture Rules

1. **Event-driven backtester** — uses an event queue: MarketEvent → SignalEvent → OrderEvent → FillEvent. Never a simple loop.
2. **Abstract Strategy base** — all strategies inherit from `BaseStrategy`. Plug-and-play via a registry.
3. **Pydantic everywhere** — all data in/out is typed and validated. No raw dicts.
4. **Structured logging** — `structlog` throughout. No print statements, no stdlib logging calls.
5. **Config via environment** — `pydantic-settings`. No hardcoded values anywhere.
6. **Full type hints** — all functions, all classes. mypy-compatible.
7. **Docstrings on all classes and public methods.**
8. **Tests alongside every feature** — pytest, placed in `tests/`.

---

## Current Project State

### ✅ DONE — Scaffold (Phase 0)

**`quantforge/core/config.py`**
- `Settings(BaseSettings)` with fields: `ENV` (dev/prod), `LOG_LEVEL`, `DATABASE_URL` (asyncpg), `REDIS_URL`
- Loads from `.env`, case-sensitive, extra fields ignored
- Singleton `settings` instance exported

**`quantforge/core/exceptions.py`**
- `AppException(Exception)` — base with `message`, `context`, formatted `__str__`
- `DataIngestionError(AppException)` — adds `ticker`, `source`
- `StrategyNotFoundError(AppException)` — adds `strategy_name`
- `BacktestError(AppException)` — adds `ticker`, `metric`

**`quantforge/core/logging.py`**
- `structlog` with contextvar-based `request_id` injection
- JSON renderer in prod, ConsoleRenderer (colored) in dev
- `get_request_id()`, `set_request_id()`, `inject_request_id_processor()` exported
- `logger` singleton exported from `core/__init__.py`

**`quantforge/data/models.py`**
- `OHLCVBar` — ticker, timestamp, OHLCV fields with `@model_validator` enforcing price boundary constraints (high ≥ open/close/low, low ≤ open/close/high)
- `Trade` — id, ticker, side (buy/sell), quantity, price, timestamp, fees
- `Position` — ticker, quantity (positive=long, negative=short), average_entry_price
- `EquityCurvePoint` — timestamp, equity
- `Portfolio` — cash, positions (dict[str, Position]), equity_curve (list[EquityCurvePoint]), `total_positions_cost` property

**`tests/test_scaffold.py`**
- Full coverage of: Settings parsing, all exception types, contextvar/structlog processor, OHLCVBar validation (valid + 2 invalid cases), Trade validation, Portfolio math

---

## Full Project Structure (Target)

```
quantforge/
├── core/
│   ├── __init__.py          ✅ done
│   ├── config.py            ✅ done
│   ├── exceptions.py        ✅ done
│   └── logging.py           ✅ done
│
├── data/
│   ├── __init__.py          ✅ done
│   ├── models.py            ✅ done
│   ├── ingestion.py         ⬜ next — yfinance fetcher → OHLCVBar list
│   ├── storage.py           ⬜ SQLAlchemy async ORM + Alembic
│   └── cache.py             ⬜ Redis layer (aioredis)
│
├── strategies/
│   ├── __init__.py          ⬜
│   ├── base.py              ⬜ abstract BaseStrategy
│   ├── registry.py          ⬜ StrategyRegistry (dict-based, decorator registration)
│   └── sma_crossover.py     ⬜ first concrete strategy
│
├── backtester/
│   ├── __init__.py          ⬜
│   ├── events.py            ⬜ MarketEvent, SignalEvent, OrderEvent, FillEvent
│   ├── engine.py            ⬜ event-driven BacktestEngine
│   ├── portfolio.py         ⬜ PortfolioManager (stateful, uses Portfolio model)
│   └── execution.py         ⬜ ExecutionHandler with slippage + fee models
│
├── metrics/
│   ├── __init__.py          ⬜
│   ├── performance.py       ⬜ Sharpe, Sortino, CAGR, Total Return
│   ├── risk.py              ⬜ Max Drawdown, VaR, Calmar Ratio
│   └── report.py            ⬜ BacktestReport dataclass
│
├── api/
│   ├── __init__.py          ⬜
│   ├── main.py              ⬜ FastAPI app with lifespan, CORS, exception handlers
│   ├── schemas.py           ⬜ request/response Pydantic models
│   ├── dependencies.py      ⬜ DB session, Redis client as FastAPI deps
│   └── routers/
│       ├── strategies.py    ⬜
│       ├── backtests.py     ⬜
│       └── metrics.py       ⬜
│
├── db/
│   ├── __init__.py          ⬜
│   ├── models.py            ⬜ SQLAlchemy ORM: market_data, strategies, backtests, trades, users
│   ├── session.py           ⬜ async sessionmaker
│   └── migrations/          ⬜ Alembic
│
└── tests/
    └── test_scaffold.py     ✅ done
```

---

## Build Sequence (Do Not Skip Steps)

| # | Feature | Key Files |
|---|---------|-----------|
| 1 | ✅ Scaffold + core + data models | core/, data/models.py |
| 2 | ⬜ Data ingestion layer | data/ingestion.py |
| 3 | ⬜ Strategy abstraction + SMA | strategies/ |
| 4 | ⬜ Event system + backtester | backtester/events.py, engine.py |
| 5 | ⬜ Portfolio manager | backtester/portfolio.py |
| 6 | ⬜ Execution handler (realism) | backtester/execution.py |
| 7 | ⬜ Metrics engine | metrics/ |
| 8 | ⬜ DB layer (SQLAlchemy + Alembic) | db/ |
| 9 | ⬜ FastAPI backend | api/ |
| 10 | ⬜ Redis cache layer | data/cache.py |
| 11 | ⬜ Docker Compose | docker-compose.yml |
| 12 | ⬜ Frontend (Next.js) | frontend/ |
| 13 | ⬜ WebSockets + paper trading | realtime/ |
| 14 | ⬜ Kafka pipeline | kafka/ |
| 15 | ⬜ Kubernetes | k8s/ |
| 16 | ⬜ Monitoring (Prometheus + Grafana) | monitoring/ |
| 17 | ⬜ RAG + ML layer | ai/ |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12+ |
| Validation | Pydantic v2 |
| Config | pydantic-settings |
| Logging | structlog |
| API | FastAPI + uvicorn |
| DB | PostgreSQL via SQLAlchemy (async) + asyncpg |
| Migrations | Alembic |
| Cache | Redis via aioredis |
| Data | yfinance (historical), Binance/Alpaca WebSockets (live) |
| ML | XGBoost, LSTM, RL agents |
| AI | RAG with vector DB + LLM |
| Containers | Docker + Docker Compose |
| Orchestration | Kubernetes |
| Monitoring | Prometheus + Grafana |
| Frontend | Next.js + React |
| Testing | pytest + httpx |

---

## Dependency Reference (pyproject.toml)

Core: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `sqlalchemy[asyncio]`, `asyncpg`, `aioredis`, `alembic`, `structlog`, `yfinance`, `pandas`, `numpy`
Testing: `pytest`, `pytest-asyncio`, `httpx`
Dev: `mypy`, `ruff`

---

## Coding Standards (Always Follow)

- All functions and classes have full type hints
- All public classes and methods have docstrings
- No raw dicts where a Pydantic model fits
- No print() — use `logger` from `quantforge.core`
- No hardcoded values — use `settings` from `quantforge.core`
- Raise domain-specific exceptions from `quantforge.core.exceptions`
- Every new module gets a corresponding test file in `tests/`

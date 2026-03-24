# Auto-Research Trading — Ollama Edition

**Karpathy-style autonomous trading strategy research — 100% local, zero API costs.**

This is a fork of [Nunchi-trade/auto-researchtrading](https://github.com/Nunchi-trade/auto-researchtrading) that replaces the Claude Code dependency with a **local Ollama LLM**, so you can run unlimited experiments on your own hardware for free.

> The original repo achieved Sharpe 21.4 from a baseline of 2.7 across 103 fully autonomous experiments on Hyperliquid perpetual futures (BTC, ETH, SOL).

---

## What This Does

An AI agent running **entirely on your local machine** autonomously:

1. Reads the current `strategy.py`
2. Proposes and implements a focused modification
3. Backtests it against historical Hyperliquid perp data
4. Keeps the change if the score improved, reverts if not
5. Repeats indefinitely — no human intervention needed

**No API keys. No cloud costs. Runs 24/7 on your own GPU.**

---

## Why This Fork Exists

The original repo uses [Claude Code](https://docs.anthropic.com/en/docs/claude-code), which burns through Anthropic API credits quickly when running hundreds of experiments. This fork replaces that with [Ollama](https://ollama.com), letting you run the same autonomous loop on a local GPU (NVIDIA or Apple Silicon) at zero marginal cost.

---

## Hardware Recommendations

| Hardware | Recommended Model | Notes |
|---|---|---|
| NVIDIA RTX 2070 (8GB VRAM) | `deepseek-r1:14b` | Fits mostly in VRAM, fast responses |
| NVIDIA RTX 3080/3090 | `qwen2.5:32b` | Excellent reasoning quality |
| NVIDIA RTX 4090 | `llama3.3:70b` | Best available open source |
| Apple M4 (16GB RAM) | `deepseek-r1:14b` | Works well on Apple Silicon |
| Any machine (32GB RAM) | `qwen2.5:32b` (Q4) | CPU offload, slower but capable |

**Recommended default: `deepseek-r1:14b`** — it is a reasoning model that "thinks" through problems step by step before proposing changes, which maps well to the iterative experiment loop.

---

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — fast Python package manager
- [Ollama](https://ollama.com) — local LLM runtime
- Git

### 1. Install Ollama

**Windows:** Download from [ollama.com](https://ollama.com) and run the installer.

**macOS:**
```bash
brew install ollama
```

### 2. Pull a Model

```bash
# Recommended for RTX 2070 / Apple M4 16GB
ollama pull deepseek-r1:14b

# Alternative — strong research and coding
ollama pull qwen2.5:14b

# If you have more VRAM or RAM
ollama pull qwen2.5:32b
```

### 3. Clone and Set Up

```bash
git clone https://github.com/boogme-lgtm/auto-research-ollama.git
cd auto-research-ollama

# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
# Windows: pip install uv

# Download backtest data (one-time, ~1 min, cached)
uv run prepare.py
```

### 4. Start Ollama

```bash
# macOS/Linux
ollama serve

# Windows: Ollama runs automatically after install, or open the Ollama app
```

### 5. Run the Autonomous Loop

```bash
# Basic — uses deepseek-r1:14b on localhost
python autoresearch_ollama.py

# Specify model
python autoresearch_ollama.py --model qwen2.5:14b

# Point to Ollama on a networked machine (e.g. Alienware GPU on your LAN)
python autoresearch_ollama.py --ollama-url http://192.168.1.50:11434

# Limit number of experiments
python autoresearch_ollama.py --max-experiments 50
```

Press **Ctrl+C** to stop at any time. Progress is saved in `results.tsv` and git history.

---

## Running Ollama on a Networked GPU (Alienware → Mac)

If you have a gaming PC with a strong NVIDIA GPU and want to use it as the AI backend while running the research loop on a Mac or another machine:

**On the Windows machine (Alienware):**

Run `expose_ollama_network.bat` — this sets `OLLAMA_HOST=0.0.0.0:11434` and starts Ollama so it's accessible on your local network.

Or manually in Command Prompt:
```
set OLLAMA_HOST=0.0.0.0:11434
ollama serve
```

Find your Windows machine's local IP by running `ipconfig` and looking for the IPv4 address (e.g. `192.168.1.50`).

**On your Mac:**
```bash
python autoresearch_ollama.py --ollama-url http://192.168.1.50:11434
```

---

## Windows Setup (Alienware)

Run `setup_windows.bat` — it checks all prerequisites, installs uv, pulls the model, and downloads the backtest data automatically.

---

## Command Reference

```bash
# Run a single backtest of the current strategy
uv run backtest.py

# Run all 5 benchmark strategies for comparison
uv run run_benchmarks.py

# Start autonomous Ollama loop (all defaults)
python autoresearch_ollama.py

# Full options
python autoresearch_ollama.py \
  --model deepseek-r1:14b \
  --ollama-url http://localhost:11434 \
  --max-experiments 200 \
  --tag mar23
```

---

## How the Loop Works

```
LOOP FOREVER:
  1. Read current strategy.py
  2. Build prompt: current code + experiment history + scoring rules + prior lessons
  3. Send to local Ollama LLM → get modified strategy.py
  4. git commit the change
  5. uv run backtest.py
  6. If score improved → keep (commit stays)
  7. If score equal or worse → git reset --hard (revert)
  8. Log result to results.tsv
  9. Repeat
```

The git history is your experiment log. Every kept improvement is a commit. You can always `git log` to see the full progression.

---

## Strategy Interface

Your strategy must implement a `Strategy` class with a single `on_bar()` method.

```python
class Strategy:
    def __init__(self):
        pass

    def on_bar(self, bar_data: dict, portfolio: PortfolioState) -> list[Signal]:
        """
        Called once per hourly bar across all symbols.

        bar_data: dict of symbol → BarData
            - BarData.close, .open, .high, .low, .volume, .funding_rate
            - BarData.history: DataFrame of last 500 bars
        portfolio: PortfolioState
            - portfolio.cash: available cash
            - portfolio.positions: dict of symbol → signed USD notional

        Returns list of Signal(symbol, target_position)
        target_position: signed USD notional (+long, -short, 0=close)
        """
        return []
```

---

## Data Available

| Field | Description |
|---|---|
| `bar_data[symbol].history` | DataFrame of last 500 hourly bars |
| Columns | `timestamp`, `open`, `high`, `low`, `close`, `volume`, `funding_rate` |
| Symbols | BTC, ETH, SOL |
| Validation period | 2024-07-01 to 2025-03-31 |
| Initial capital | $100,000 |
| Fees | 2 bps maker, 5 bps taker, 1 bps slippage |

No API keys required. Data is fetched from public CryptoCompare and Hyperliquid APIs.

---

## Scoring Formula

```
score = sharpe × √(min(trades/50, 1.0)) − drawdown_penalty − turnover_penalty

drawdown_penalty = max(0, max_drawdown_pct − 15) × 0.05
turnover_penalty = max(0, annual_turnover/capital − 500) × 0.001

Hard cutoffs (→ −999): fewer than 10 trades, drawdown > 50%, lost > 50% of capital
```

**Baseline to beat: 2.724** (simple momentum strategy)

---

## Key Lessons Baked Into the LLM Prompt

These discoveries from the original 103 experiments are included in the system prompt as prior knowledge, giving the local LLM a head start:

- **Simplicity wins** — removing features often improves score more than adding them
- **RSI period 8** beats period 14 for hourly crypto (standard 14 is too slow)
- **Uniform position sizing** beats momentum-weighted sizing
- **ATR trailing stops at 5.5×** beat conventional 3.5× (hold winners longer)
- **6-signal ensemble with 4/6 majority vote** is the current best architecture
- **The Great Simplification**: removing pyramiding, funding boost, BTC filter, and correlation filter added +2.0 Sharpe

---

## Benchmarks

5 reference strategies included. Baseline to beat is **2.724**.

| Rank | Strategy | Score | Sharpe | Return | Max DD | Trades |
|---|---|---|---|---|---|---|
| 1 | `simple_momentum` | 2.724 | 2.724 | +42.6% | 7.6% | 9081 |
| 2 | `funding_arb` | -0.191 | -0.191 | -1.3% | 9.4% | 1403 |
| 3 | `regime_mm` | -0.322 | -0.322 | -3.1% | 11.2% | 12854 |
| 4 | `mean_reversion` | -3.964 | -3.380 | -26.2% | 26.7% | 3185 |
| 5 | `momentum_breakout` | -999 | — | — | — | 0 |

---

## Original Results (103 Claude Code Experiments)

| Experiment | Score | Sharpe | Max DD | Key Change |
|---|---|---|---|---|
| Baseline | 2.724 | 2.724 | 7.6% | Simple momentum |
| exp15 | 8.393 | 8.823 | 3.1% | 5-signal ensemble, 4/5 votes |
| exp28 | 9.382 | 9.944 | 3.0% | ATR 5.5 trailing stop |
| exp37 | 10.305 | 11.125 | 2.3% | BB width compression (6th signal) |
| exp72 | 19.697 | 20.099 | 0.7% | RSI period 8 |
| **exp102** | **20.634** | **20.634** | **0.3%** | RSI 50/50, BB 85, position 0.08 |

---

## Project Structure

```
├── strategy.py               # The only file the agent edits
├── backtest.py               # Backtest runner (fixed — do not modify)
├── prepare.py                # Data download + engine (fixed — do not modify)
├── autoresearch_ollama.py    # ← NEW: autonomous loop using local Ollama LLM
├── setup_windows.bat         # ← NEW: one-click Windows setup for Alienware
├── expose_ollama_network.bat # ← NEW: expose Ollama on LAN for remote access
├── run_benchmarks.py         # Compare 5 reference strategies
├── benchmarks/               # 5 reference strategies
├── program.md                # Original Claude Code loop instructions
├── STRATEGIES.md             # Full evolution log of all 103 experiments
├── pyproject.toml            # Dependencies
└── uv.lock                   # Locked dependencies
```

---

## Credits

- **Original research and repo**: [Nunchi-trade](https://github.com/Nunchi-trade/auto-researchtrading)
- **Ollama adaptation**: Coach Cristian / [C-Squared](https://www.youtube.com/@csqpod)
- **Inspired by**: [Andrej Karpathy's autoresearch](https://github.com/karpathy/autoresearch)

---

## License

MIT — fork freely, run locally, keep your alpha.

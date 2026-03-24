#!/usr/bin/env python3
"""
autoresearch_ollama.py — Autonomous trading strategy research using a local Ollama LLM.

Drop-in replacement for the Claude Code `/autoresearch` workflow.
Runs 100% locally — no API keys, no cloud costs.

Usage:
    python autoresearch_ollama.py [--model deepseek-r1:14b] [--ollama-url http://localhost:11434] [--max-experiments 200]

Requirements:
    - Ollama running locally (or on a networked machine) with a model pulled
    - uv installed (for running backtests)
    - Data downloaded: uv run prepare.py

Author: Coach Cristian / C-Squared — forked from Nunchi-trade/auto-researchtrading
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

DEFAULT_MODEL = "deepseek-r1:14b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MAX_EXPERIMENTS = 500
RESULTS_FILE = "results.tsv"
STRATEGY_FILE = "strategy.py"
RUN_LOG = "run.log"

# ─────────────────────────────────────────────
# Ollama client
# ─────────────────────────────────────────────

def ollama_chat(messages: list[dict], model: str, base_url: str, temperature: float = 0.7) -> str:
    """Send a chat request to Ollama and return the assistant's reply."""
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": 4096,
            "num_predict": 2048,
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=600)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Cannot connect to Ollama at {base_url}")
        print("Make sure Ollama is running: `ollama serve`")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Ollama request failed: {e}")
        raise


def check_ollama(base_url: str, model: str) -> bool:
    """Check that Ollama is running and the model is available."""
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=10)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        # Check for exact match or prefix match (e.g. "deepseek-r1:14b" vs "deepseek-r1:14b-...")
        available = any(m == model or m.startswith(model.split(":")[0]) for m in models)
        if not available:
            print(f"[WARNING] Model '{model}' not found in Ollama.")
            print(f"Available models: {models}")
            print(f"Pull it with: ollama pull {model}")
            return False
        return True
    except Exception:
        return False


def warmup_model(base_url: str, model: str) -> None:
    """Send a tiny request to load the model into VRAM before the main loop."""
    print(f"Warming up model '{model}' (loading into GPU memory)...")
    try:
        url = f"{base_url}/api/chat"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "options": {"num_ctx": 512},
        }
        resp = requests.post(url, json=payload, timeout=600)
        resp.raise_for_status()
        print(f"✓ Model loaded and ready")
    except Exception as e:
        print(f"[WARNING] Warmup failed: {e} — will retry on first experiment")


# ─────────────────────────────────────────────
# Git helpers
# ─────────────────────────────────────────────

def git_current_branch() -> str:
    return subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()


def git_log_short(n: int = 5) -> str:
    return subprocess.check_output(
        ["git", "log", f"--oneline", f"-{n}"], text=True
    ).strip()


def git_commit(message: str) -> str:
    subprocess.run(["git", "add", STRATEGY_FILE], check=True)
    result = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True, text=True
    )
    return result.stdout + result.stderr


def git_reset_hard() -> None:
    subprocess.run(["git", "reset", "--hard", "HEAD~1"], check=True)


def git_diff_strategy() -> str:
    """Return the diff of strategy.py vs HEAD."""
    result = subprocess.run(
        ["git", "diff", "HEAD", STRATEGY_FILE],
        capture_output=True, text=True
    )
    return result.stdout


# ─────────────────────────────────────────────
# Backtest runner
# ─────────────────────────────────────────────

def get_python_cmd() -> list[str]:
    """Return the right command to run backtest.py on this platform."""
    import shutil
    if shutil.which("uv"):
        return ["uv", "run", "backtest.py"]
    # Fall back to plain python
    python = shutil.which("python") or shutil.which("python3") or sys.executable
    return [python, "backtest.py"]


def run_backtest() -> dict | None:
    """Run the backtest and parse the results. Returns None on crash."""
    cmd = get_python_cmd()
    with open(RUN_LOG, "w") as f:
        result = subprocess.run(
            cmd,
            stdout=f, stderr=f,
            timeout=180
        )

    with open(RUN_LOG) as f:
        log = f.read()

    metrics = {}
    for line in log.splitlines():
        for key in ["score", "sharpe", "total_return_pct", "max_drawdown_pct", "num_trades"]:
            if line.startswith(f"{key}:"):
                try:
                    metrics[key] = float(line.split(":")[1].strip())
                except ValueError:
                    pass

    if "score" not in metrics:
        # Crashed — return None with log tail
        tail = "\n".join(log.splitlines()[-30:])
        return {"crashed": True, "log_tail": tail}

    return metrics


# ─────────────────────────────────────────────
# Results tracking
# ─────────────────────────────────────────────

def init_results_tsv() -> None:
    if not Path(RESULTS_FILE).exists():
        with open(RESULTS_FILE, "w") as f:
            f.write("commit\tscore\tsharpe\tmax_dd\tstatus\tdescription\n")


def append_result(commit_hash: str, metrics: dict, status: str, description: str) -> None:
    score = metrics.get("score", -999)
    sharpe = metrics.get("sharpe", 0)
    max_dd = metrics.get("max_drawdown_pct", 0)
    with open(RESULTS_FILE, "a") as f:
        f.write(f"{commit_hash[:8]}\t{score:.3f}\t{sharpe:.3f}\t{max_dd:.3f}\t{status}\t{description}\n")


def read_results() -> list[dict]:
    rows = []
    if not Path(RESULTS_FILE).exists():
        return rows
    with open(RESULTS_FILE) as f:
        lines = f.readlines()
    for line in lines[1:]:
        parts = line.strip().split("\t")
        if len(parts) >= 5:
            try:
                rows.append({
                    "commit": parts[0],
                    "score": float(parts[1]),
                    "sharpe": float(parts[2]),
                    "max_dd": float(parts[3]),
                    "status": parts[4],
                    "description": parts[5] if len(parts) > 5 else "",
                })
            except ValueError:
                pass
    return rows


def best_score(results: list[dict]) -> float:
    scores = [r["score"] for r in results if r["score"] > -999]
    return max(scores) if scores else 2.724  # baseline


# ─────────────────────────────────────────────
# LLM prompting
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert quantitative trading researcher specializing in crypto perpetual futures strategy development.

You are running an autonomous experiment loop on Hyperliquid perp data (BTC, ETH, SOL, hourly bars, Jul 2024 - Mar 2025).

Your job:
1. Read the current strategy.py
2. Propose ONE focused modification to improve the score
3. Output ONLY the complete new strategy.py content — nothing else

Rules:
- Only modify strategy.py — this is the single mutable file
- Do NOT modify prepare.py, backtest.py, or benchmarks/
- Only use: numpy, pandas, scipy, requests, pyarrow, and stdlib
- Each experiment = one focused change (not a complete rewrite)
- Think step by step about WHY your change should improve the Sharpe ratio

The scoring formula:
  score = sharpe * sqrt(min(trades/50, 1.0)) - drawdown_penalty - turnover_penalty
  drawdown_penalty = max(0, max_drawdown_pct - 15) * 0.05
  turnover_penalty = max(0, annual_turnover/capital - 500) * 0.001
  Hard cutoffs: <10 trades → -999, >50% drawdown → -999

Key lessons from 103 prior experiments:
- Simplicity wins — removing complexity often improves score
- RSI period 8 beats period 14 for hourly crypto
- Uniform position sizing beats momentum-weighted sizing
- ATR trailing stops at 5.5x beat conventional 3.5x
- 6-signal ensemble with 4/6 majority vote is the current best architecture

IMPORTANT: Output ONLY the raw Python code for strategy.py. No markdown, no explanation, no code fences. Start directly with the import statements or class definition."""


def build_experiment_prompt(
    strategy_code: str,
    results_history: list[dict],
    experiment_num: int,
    current_best: float,
) -> str:
    recent = results_history[-10:] if len(results_history) > 10 else results_history
    history_str = "\n".join(
        f"  exp{i+1}: score={r['score']:.3f} sharpe={r['sharpe']:.3f} dd={r['max_dd']:.1f}% [{r['status']}] {r['description']}"
        for i, r in enumerate(recent)
    )

    return f"""=== EXPERIMENT {experiment_num} ===

Current best score: {current_best:.3f}
Baseline to beat: 2.724

Recent experiment history (last {len(recent)}):
{history_str if history_str else "  (no experiments yet — start from scratch)"}

Current strategy.py:
```python
{strategy_code}
```

Propose and implement ONE focused modification to strategy.py that you believe will improve the score above {current_best:.3f}.

Think carefully about:
- What signal or parameter change is most likely to improve Sharpe?
- Will this change increase or decrease trade count? (need >10 trades)
- Will this change increase drawdown? (keep below 50%)

Output ONLY the complete new strategy.py Python code. No explanation. No markdown fences."""


def extract_python_code(response: str) -> str:
    """Extract Python code from LLM response, stripping any markdown fences or thinking tags."""
    # Remove <think>...</think> blocks (DeepSeek R1 style)
    response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)

    # Remove markdown code fences
    response = re.sub(r"```python\n?", "", response)
    response = re.sub(r"```\n?", "", response)

    # Strip leading/trailing whitespace
    response = response.strip()

    return response


def get_commit_description(strategy_code: str, model: str, base_url: str) -> str:
    """Ask the LLM for a short description of the change for the git commit message."""
    messages = [
        {
            "role": "user",
            "content": f"In 10 words or less, describe the key change in this trading strategy. Output only the description, nothing else:\n\n{strategy_code[:2000]}"
        }
    ]
    try:
        desc = ollama_chat(messages, model, base_url, temperature=0.3)
        desc = re.sub(r"<think>.*?</think>", "", desc, flags=re.DOTALL).strip()
        # Keep it short
        return desc[:80].replace("\n", " ")
    except Exception:
        return "strategy modification"


# ─────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Autonomous trading research with local Ollama LLM")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help=f"Ollama base URL (default: {DEFAULT_OLLAMA_URL})")
    parser.add_argument("--max-experiments", type=int, default=DEFAULT_MAX_EXPERIMENTS, help="Max experiments to run")
    parser.add_argument("--tag", default=None, help="Experiment branch tag (default: auto-generated from date)")
    parser.add_argument("--skip-branch", action="store_true", help="Skip branch creation (use current branch)")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════╗
║        AUTO-RESEARCH TRADING — OLLAMA EDITION            ║
║  Model: {args.model:<48}║
║  Ollama: {args.ollama_url:<47}║
║  Max experiments: {args.max_experiments:<39}║
╚══════════════════════════════════════════════════════════╝
""")

    # Check Ollama is running
    print("Checking Ollama connection...")
    if not check_ollama(args.ollama_url, args.model):
        print(f"\nStart Ollama and pull the model:")
        print(f"  ollama serve")
        print(f"  ollama pull {args.model}")
        sys.exit(1)
    print(f"✓ Ollama connected, model '{args.model}' available\n")

    # Warm up the model (load into VRAM before the loop starts)
    warmup_model(args.ollama_url, args.model)
    print()

    # Check we're in the right directory
    if not Path(STRATEGY_FILE).exists():
        print(f"[ERROR] {STRATEGY_FILE} not found. Run this from the auto-research-ollama directory.")
        sys.exit(1)

    # Check data exists
    data_dir = Path.home() / ".cache" / "autotrader" / "data"
    if not data_dir.exists():
        print("[INFO] Downloading backtest data (one-time setup, ~1 min)...")
        subprocess.run(["uv", "run", "prepare.py"], check=True)

    # Create experiment branch
    if not args.skip_branch:
        tag = args.tag or datetime.now().strftime("%b%d").lower()
        branch = f"autotrader/{tag}-ollama"
        existing = subprocess.run(
            ["git", "branch", "--list", branch], capture_output=True, text=True
        ).stdout.strip()
        if existing:
            print(f"Branch '{branch}' already exists. Switching to it.")
            subprocess.run(["git", "checkout", branch], check=True)
        else:
            subprocess.run(["git", "checkout", "-b", branch], check=True)
        print(f"✓ On branch: {branch}\n")

    # Initialize results
    init_results_tsv()
    results = read_results()
    current_best = best_score(results)
    print(f"Starting best score: {current_best:.3f} (baseline: 2.724)\n")

    # Run baseline first if no results yet
    if not results:
        print("Running baseline backtest...")
        metrics = run_backtest()
        if metrics and not metrics.get("crashed"):
            current_best = metrics["score"]
            print(f"Baseline score: {current_best:.3f}")
            commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            append_result(commit_hash, metrics, "baseline", "original strategy")
            results = read_results()

    # ── Main experiment loop ──
    experiment_num = len(results)
    consecutive_failures = 0

    print(f"Starting autonomous experiment loop (max {args.max_experiments} experiments)...")
    print("Press Ctrl+C to stop at any time.\n")

    while experiment_num < args.max_experiments:
        experiment_num += 1
        print(f"{'─'*60}")
        print(f"Experiment {experiment_num} | Best score: {current_best:.3f}")
        print(f"{'─'*60}")

        # Read current strategy
        strategy_code = Path(STRATEGY_FILE).read_text()

        # Build prompt and ask LLM
        print(f"Asking {args.model} for next experiment idea...")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_experiment_prompt(
                strategy_code, results, experiment_num, current_best
            )},
        ]

        try:
            response = ollama_chat(messages, args.model, args.ollama_url)
        except Exception as e:
            print(f"[ERROR] LLM call failed: {e}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                print("Too many consecutive failures. Stopping.")
                break
            time.sleep(5)
            continue

        # Extract Python code
        new_strategy = extract_python_code(response)

        if len(new_strategy) < 100:
            print(f"[WARNING] LLM returned suspiciously short code ({len(new_strategy)} chars). Skipping.")
            consecutive_failures += 1
            continue

        consecutive_failures = 0

        # Write new strategy
        Path(STRATEGY_FILE).write_text(new_strategy)

        # Get a short description for the commit
        description = get_commit_description(new_strategy, args.model, args.ollama_url)
        commit_msg = f"exp{experiment_num}: {description}"

        # Commit
        commit_output = git_commit(commit_msg)
        commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        print(f"Committed: {commit_msg[:70]}")

        # Run backtest
        print("Running backtest...")
        t0 = time.time()
        metrics = run_backtest()
        elapsed = time.time() - t0

        if metrics is None or metrics.get("crashed"):
            log_tail = metrics.get("log_tail", "") if metrics else ""
            print(f"[CRASHED] Backtest failed after {elapsed:.1f}s")
            print(f"Log tail:\n{log_tail[-500:]}")
            git_reset_hard()
            append_result(commit_hash[:8], {"score": -999, "sharpe": 0, "max_drawdown_pct": 0}, "crashed", description)
            results = read_results()
            continue

        score = metrics["score"]
        sharpe = metrics["sharpe"]
        max_dd = metrics["max_drawdown_pct"]
        num_trades = int(metrics.get("num_trades", 0))

        print(f"Score: {score:.3f} | Sharpe: {sharpe:.3f} | Max DD: {max_dd:.1f}% | Trades: {num_trades} | Time: {elapsed:.1f}s")

        if score > current_best:
            improvement = score - current_best
            print(f"✅ IMPROVEMENT! +{improvement:.3f} (new best: {score:.3f})")
            current_best = score
            append_result(commit_hash[:8], metrics, "kept", description)
        else:
            print(f"❌ No improvement ({score:.3f} ≤ {current_best:.3f}). Reverting.")
            git_reset_hard()
            append_result(commit_hash[:8], metrics, "reverted", description)

        results = read_results()
        print()

    print(f"\n{'═'*60}")
    print(f"Experiment loop complete after {experiment_num} experiments.")
    print(f"Final best score: {current_best:.3f}")
    print(f"Results saved to: {RESULTS_FILE}")
    print(f"{'═'*60}")


if __name__ == "__main__":
    main()

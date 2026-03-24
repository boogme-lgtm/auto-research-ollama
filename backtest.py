"""
Run backtest. Usage: uv run backtest.py
Imports strategy from strategy.py, runs on validation data, prints metrics.
This file is fixed — do not modify.
"""

import time
import multiprocessing
import sys

from prepare import load_data, run_backtest, compute_score, TIME_BUDGET

def run_backtest_process():
    """The actual backtest logic, designed to be run in a separate process."""
    t_start = time.time()

    # Import strategy inside the function to avoid issues with multiprocessing
    from strategy import Strategy

    strategy = Strategy()
    data = load_data("val")

    print(f"Loaded {sum(len(df) for df in data.values())} bars across {len(data)} symbols")
    print(f"Symbols: {list(data.keys())}")

    result = run_backtest(strategy, data)
    score = compute_score(result)

    t_end = time.time()

    print("---")
    print(f"score:              {score:.6f}")
    print(f"sharpe:             {result.sharpe:.6f}")
    print(f"total_return_pct:   {result.total_return_pct:.6f}")
    print(f"max_drawdown_pct:   {result.max_drawdown_pct:.6f}")
    print(f"num_trades:         {result.num_trades}")
    print(f"win_rate_pct:       {result.win_rate_pct:.6f}")
    print(f"profit_factor:      {result.profit_factor:.6f}")
    print(f"annual_turnover:    {result.annual_turnover:.2f}")
    print(f"backtest_seconds:   {result.backtest_seconds:.1f}")
    print(f"total_seconds:      {t_end - t_start:.1f}")

if __name__ == '__main__':
    # Use multiprocessing for a cross-platform timeout, since signal.SIGALRM is not available on Windows.
    process = multiprocessing.Process(target=run_backtest_process)
    process.start()

    # Wait for the process to complete, with a timeout
    process.join(TIME_BUDGET + 30)  # 30s grace period for startup

    if process.is_alive():
        print("TIMEOUT: backtest exceeded time budget")
        process.terminate()
        process.join()
        sys.exit(1)

    if process.exitcode != 0:
        print(f"Backtest process failed with exit code {process.exitcode}")
        sys.exit(process.exitcode)

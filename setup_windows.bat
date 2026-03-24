@echo off
REM ============================================================
REM  Auto-Research Trading — Ollama Setup for Windows
REM  Run this once on your Alienware to get everything ready
REM ============================================================

echo.
echo ============================================================
echo  AUTO-RESEARCH TRADING — WINDOWS SETUP
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found

REM Check git
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git not found. Install from https://git-scm.com
    pause
    exit /b 1
)
echo [OK] Git found

REM Install uv
echo.
echo Installing uv (fast Python package manager)...
pip install uv
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install uv
    pause
    exit /b 1
)
echo [OK] uv installed

REM Check Ollama
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [INFO] Ollama not found. 
    echo Please download and install Ollama from: https://ollama.com
    echo Then run this script again.
    pause
    exit /b 1
)
echo [OK] Ollama found

REM Pull the model
echo.
echo Pulling DeepSeek R1 14B model (~9GB download, this will take a while)...
echo You can also use: ollama pull qwen2.5:14b  (alternative model)
ollama pull deepseek-r1:14b
echo [OK] Model ready

REM Download backtest data
echo.
echo Downloading backtest data (Hyperliquid perp data, ~1 min)...
uv run prepare.py
echo [OK] Data ready

echo.
echo ============================================================
echo  SETUP COMPLETE!
echo.
echo  To run the autonomous research loop:
echo    python autoresearch_ollama.py
echo.
echo  To run on a networked Mac (point to this machine):
echo    python autoresearch_ollama.py --ollama-url http://YOUR_IP:11434
echo.
echo  To use a different model:
echo    python autoresearch_ollama.py --model qwen2.5:14b
echo ============================================================
pause

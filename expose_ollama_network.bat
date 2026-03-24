@echo off
REM ============================================================
REM  Expose Ollama on your local network
REM  Run this on the Alienware so your Mac mini can use its GPU
REM ============================================================

echo.
echo ============================================================
echo  EXPOSING OLLAMA ON LOCAL NETWORK
echo ============================================================
echo.
echo This will make Ollama accessible from other devices on your
echo home network (e.g. your Mac mini).
echo.

REM Set environment variable to allow network access
set OLLAMA_HOST=0.0.0.0:11434

REM Show local IP address
echo Your Alienware IP addresses:
ipconfig | findstr /i "IPv4"
echo.
echo Use one of the above IPs on your Mac mini, e.g.:
echo   python autoresearch_ollama.py --ollama-url http://192.168.1.XXX:11434
echo.
echo Starting Ollama (press Ctrl+C to stop)...
echo.

ollama serve

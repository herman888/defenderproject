@echo off
:loop
echo [%time%] Starting claude run...
venv\Scripts\activate.bat
type MEGAPROMPT_V3.md | claude --dangerously-skip-permissions
echo [%time%] Claude exited. Restarting in 10 seconds... (Ctrl+C to stop)
timeout /t 10
goto loop

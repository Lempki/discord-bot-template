@echo off
setlocal
:: Prepares a local development environment with uv.
:: Run it from the repository root. It is safe to run again at any time.
for %%I in (.) do echo === %%~nxI setup ===
echo.

where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv was not found. Install it with: winget install --id astral-sh.uv
    pause
    exit /b 1
)

:: uv creates .venv on first run and installs the locked runtime and development dependencies.
echo Installing dependencies...
uv sync
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.template" ".env" >nul
    echo Created .env from .env.template.
    echo   ^> Edit .env and set your DISCORD_TOKEN before running the bot.
) else (
    echo .env already exists, skipping.
)

echo.
echo Setup complete!
echo   Run the bot : uv run python bot.py
echo   Run tests   : uv run pytest
echo.
pause
endlocal

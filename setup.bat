@echo off
setlocal
echo === discord-bot-template setup ===
echo.

:: Require Python 3.10+
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Create virtual environment if it doesn't already exist
if not exist ".venv\" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists, skipping creation.
)

:: Upgrade pip
echo Upgrading pip...
.venv\Scripts\python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip.
    pause
    exit /b 1
)

:: Install requirements
echo Installing requirements...
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install requirements.
    pause
    exit /b 1
)

:: Copy .env.example to .env if .env doesn't exist yet
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Created .env from .env.example
    echo   ^> Edit .env and set your DISCORD_TOKEN before running the bot.
) else (
    echo .env already exists, skipping.
)

echo.
echo Setup complete!
echo   Activate venv : .venv\Scripts\activate
echo   Run the bot   : .venv\Scripts\python bot.py
echo.
pause
endlocal

@echo off
echo Setting up pycoterm...

REM Check if Python is available
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

echo Python found. Installing dependencies...

REM Install dependencies from requirements.txt
pip install -r requirements.txt

if %ERRORLEVEL% neq 0 (
    echo Failed to install dependencies from requirements.txt. Trying alternative installation...
    echo.
    echo Trying pip upgrade first...
    pip install --upgrade pip
    pip install -r requirements.txt
    
    if %ERRORLEVEL% neq 0 (
        echo All installation attempts failed.
        echo Please try manually: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo.
echo Setup complete!
echo Run the application with: python pycoterm.py
echo.
pause
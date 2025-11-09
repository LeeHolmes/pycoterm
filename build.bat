@echo off
echo Building pyco executable with PyInstaller...

REM Check if Python is available
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Check if PyInstaller is installed, install if not
echo Checking for PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
    REM Check again after installation
    python -c "import PyInstaller" >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo Failed to install PyInstaller properly
        pause
        exit /b 1
    )
)

REM Check if pycoterm.py exists
if not exist "pycoterm.py" (
    echo ERROR: pycoterm.py not found in current directory
    pause
    exit /b 1
)

REM Check if icon exists
if not exist "pyco.ico" (
    echo WARNING: pyco.ico not found, building without icon
    set ICON_PARAM=
) else (
    echo Found pyco.ico, using as application icon
    set ICON_PARAM=--icon=pyco.ico
)

REM Clean previous build
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build
REM Don't delete pyco.spec - we want to keep our custom data files

echo.
echo Building standalone executable...
echo This may take a few minutes...

REM Build with PyInstaller using spec file
python -m PyInstaller pyco.spec

if %ERRORLEVEL% neq 0 (
    echo.
    echo Build failed! Check the output above for errors.
    pause
    exit /b 1
)

REM Check if executable was created
if exist "dist\pyco.exe" (
    echo.
    echo ========================================
    echo Build successful!
    echo ========================================
    echo.
    echo Executable location: dist\pyco.exe
    echo File size:
    dir dist\pyco.exe | findstr pyco.exe
    echo.
    echo You can now distribute the single file: dist\pyco.exe
) else (
    echo.
    echo ERROR: Executable was not created successfully
    echo Check the PyInstaller output above for details
    pause
    exit /b 1
)

echo.
echo Build process complete!
echo Your standalone pyco.exe is ready in the dist folder.
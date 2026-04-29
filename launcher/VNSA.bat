@echo off
:: VNSA 2.0 Launcher
setlocal

:: Absolute project root — update if you move the folder
set "ROOT=F:\Files\Personal\VNSA Source\VNSA 2\VNSA-2"
set "KEYS=%ROOT%\backend\config\keys.env"
set "KEYS_EXAMPLE=%ROOT%\backend\config\keys.env.example"
set "FRONTEND=%ROOT%\frontend"
set "MODULES=%ROOT%\frontend\node_modules"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Install from python.org
    pause & exit /b 1
)

:: Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo Node.js not found. Install from nodejs.org
    pause & exit /b 1
)

:: First run — create keys.env and open it
if not exist "%KEYS%" (
    copy "%KEYS_EXAMPLE%" "%KEYS%" >nul
    echo First time setup: Fill in your API keys, save the file, then run this again.
    notepad "%KEYS%"
    exit /b 0
)

:: Install node_modules if missing
if not exist "%MODULES%" (
    echo Installing Electron for the first time - please wait...
    cd /d "%FRONTEND%"
    npm install
)

:: Launch — no terminal window stays open
cd /d "%FRONTEND%"
start "" /b npx electron .

exit /b 0

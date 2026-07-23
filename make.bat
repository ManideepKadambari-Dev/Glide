@echo off
REM ===========================================================================
REM  make.bat  -  Glide developer tasks
REM
REM    make.bat dev     Run Glide from source            (py -m glide)
REM    make.bat build   Build the standalone Glide.exe and zip it for release
REM
REM  Run with no argument to pick from a menu.
REM ===========================================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "MODE=%~1"
if not defined MODE call :menu

if /i "%MODE%"=="dev"   goto dev
if /i "%MODE%"=="run"   goto dev
if /i "%MODE%"=="build" goto build
if /i "%MODE%"=="dist"  goto build

echo.
echo   Unknown option "%MODE%".
echo   Usage:  %~nx0 [ dev ^| build ]
exit /b 1


:menu
echo.
echo   ==================================
echo      Glide  -  developer tasks
echo   ==================================
echo.
echo      [1]  Run Glide         -  development
echo      [2]  Build ^& package   -  standalone .exe + zip
echo.
set /p "SEL=  Choose 1 or 2:  "
if "%SEL%"=="1" set "MODE=dev"
if "%SEL%"=="2" set "MODE=build"
goto :eof


:dev
echo.
echo   [dev]  Starting Glide...  press  Q  or  Esc  in the window to quit.
echo.
py -m glide
exit /b %errorlevel%


:build
echo.
echo   [build]  Packaging Glide into a standalone Windows app.
echo.

echo   1/5  Checking PyInstaller...
py -m PyInstaller --version >nul 2>&1
if not errorlevel 1 goto model
echo        installing PyInstaller...
py -m pip install --disable-pip-version-check pyinstaller
if errorlevel 1 goto fail

:model
echo   2/5  Checking the hand model...
if exist "hand_landmarker.task" goto freeze
echo        downloading hand_landmarker.task...
py -c "import sys; from glide.app import ensure_model; sys.exit(0 if ensure_model('hand_landmarker.task') else 1)"
if errorlevel 1 goto fail

:freeze
echo   3/5  Building Glide.exe with PyInstaller ^(this takes a minute^)...
py -m PyInstaller --noconfirm Glide.spec
if errorlevel 1 goto fail

echo   4/5  Zipping dist\Glide-windows.zip...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\Glide' -DestinationPath 'dist\Glide-windows.zip' -Force"
if errorlevel 1 goto fail

echo   5/5  Verifying the frozen build...
"dist\Glide\Glide.exe" --selftest >nul 2>&1
if errorlevel 1 (echo        selftest FAILED & goto fail)
"dist\Glide\Glide.exe" --check >nul 2>&1
if errorlevel 1 (echo        model check FAILED & goto fail)

echo.
echo   Done.  Deployable artifact:
for %%F in ("dist\Glide-windows.zip") do echo       %%~fF   -  %%~zF bytes
echo.
echo   Next: upload that zip to your Cloudflare R2 bucket, then link it
echo   from your portfolio.
exit /b 0


:fail
echo.
echo   BUILD FAILED  -  see the messages above.
exit /b 1

@echo off
echo ============================================
echo  Video Translator - LibreTranslate Server
echo ============================================
echo.
echo This starts two containers: this app (speech-to-text) and LibreTranslate
echo itself (translation engine). Runs alongside nllb-server on a different
echo port (8001) - you can run both and switch between them in the extension
echo popup, or run just this one.
echo.

where docker >nul 2>nul
if errorlevel 1 (
    echo ERROR: Docker was not found on this machine.
    echo Install Docker Desktop first: https://www.docker.com/products/docker-desktop/
    echo Then run this script again.
    pause
    exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
    echo ERROR: Docker is installed but doesn't seem to be running.
    echo Start Docker Desktop, wait until it says "running", then run this script again.
    pause
    exit /b 1
)

docker compose version >nul 2>nul
if errorlevel 1 (
    echo ERROR: "docker compose" isn't available. Update Docker Desktop
    echo (it bundles Compose v2) and try again.
    pause
    exit /b 1
)

echo Building and starting both containers...
echo (First time: a few minutes - downloading Python packages, the STT model,
echo AND LibreTranslate's own language models. Later runs are much faster
echo thanks to the cached volumes.)
echo.
docker compose up -d --build
if errorlevel 1 (
    echo.
    echo Startup failed - see the errors above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Containers started.
echo ============================================
echo.
echo To watch progress:   docker compose logs -f
echo   (server ready once you see "Ready (translation backend: LibreTranslate...)"
echo    then "Application startup complete.")
echo   (libretranslate ready once its own log shows "Running on http://0.0.0.0:5000")
echo To check readiness:  open http://127.0.0.1:8001/health in a browser -
echo   ready when "sttModelLoaded" and "translationReady" are both true
echo.
echo To stop:   docker compose down
echo To start again:   docker compose up -d
echo   (no need to re-run this script unless the code changes)
echo.
pause

@echo off
echo ============================================
echo  Video Translator - Local Server Launcher
echo ============================================
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

echo Building the server image...
echo (First time: a few minutes, downloading Python packages. Later runs: seconds.)
echo.
docker build -t chrome-video-translator-server:local .
if errorlevel 1 (
    echo.
    echo Build failed - see the errors above.
    pause
    exit /b 1
)

docker volume create chrome-video-translator-hf-cache >nul

echo.
echo Stopping any previous instance...
docker stop chrome-video-translator-server >nul 2>nul
docker rm chrome-video-translator-server >nul 2>nul

echo.
echo Starting the server...
docker run -d --name chrome-video-translator-server -p 8000:8000 -v chrome-video-translator-hf-cache:/data/hf-cache chrome-video-translator-server:local
if errorlevel 1 (
    echo.
    echo Failed to start - see the errors above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Server container started.
echo ============================================
echo.
echo IMPORTANT: the FIRST run downloads about 2.5GB of AI models. That alone
echo can take several minutes depending on your internet connection - the
echo server isn't actually ready for translation until that finishes. Later
echo runs reuse the same downloaded models (stored in a Docker volume) and
echo start in well under a minute.
echo.
echo To watch progress:   docker logs -f chrome-video-translator-server
echo   (ready once you see "All models ready." then "Application startup complete.")
echo To check readiness:  open http://127.0.0.1:8000/health in a browser -
echo   ready when it shows "sttModelLoaded":true and "translationModelLoaded":true
echo.
echo To stop the server:  docker stop chrome-video-translator-server
echo To start it again:   docker start chrome-video-translator-server
echo   (no need to re-run this script unless the code changes)
echo.
pause

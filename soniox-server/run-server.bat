@echo off
echo ============================================
echo  Video Translator - Soniox Server Launcher
echo ============================================
echo.
echo This starts one container: this app, which relays tab audio to Soniox's
echo cloud STT+translation API (https://soniox.com/). Unlike nllb-server and
echo libre-server, this is NOT fully local -- audio leaves your machine and
echo the API is paid (see soniox-server/README.md). Runs on port 8002, so it
echo can run alongside nllb-server (8000) and libre-server (8001).
echo.

set USE_ENV_FILE=0
if exist ".env" (
    set USE_ENV_FILE=1
) else if "%SONIOX_API_KEY%"=="" (
    echo ERROR: SONIOX_API_KEY is not set, and no .env file was found in this folder.
    echo Get a key at https://soniox.com/, then either:
    echo   1^) copy .env.example to .env and fill in your key, or
    echo   2^) set it directly: set SONIOX_API_KEY=your-key-here
    echo and run this script again.
    pause
    exit /b 1
)

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
echo (First time: under a minute -- no AI models to download, this server
echo just relays audio to Soniox's cloud API.)
echo.
docker build -t chrome-video-translator-soniox-server:local .
if errorlevel 1 (
    echo.
    echo Build failed - see the errors above.
    pause
    exit /b 1
)

echo.
echo Stopping any previous instance...
docker stop chrome-video-translator-soniox-server >nul 2>nul
docker rm chrome-video-translator-soniox-server >nul 2>nul

echo.
echo Starting the server...
if "%USE_ENV_FILE%"=="1" (
    echo ^(using .env for SONIOX_API_KEY^)
    docker run -d --name chrome-video-translator-soniox-server -p 8002:8002 --env-file .env chrome-video-translator-soniox-server:local
) else (
    docker run -d --name chrome-video-translator-soniox-server -p 8002:8002 -e SONIOX_API_KEY=%SONIOX_API_KEY% chrome-video-translator-soniox-server:local
)
if errorlevel 1 (
    echo.
    echo Failed to start - see the errors above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Container started.
echo ============================================
echo.
echo To watch progress:   docker logs -f chrome-video-translator-soniox-server
echo To check readiness:  open http://127.0.0.1:8002/health in a browser -
echo   ready when "apiKeyConfigured" is true (this only confirms the key is
echo   set, not that it's valid or that Soniox is reachable)
echo.
echo To stop:   docker stop chrome-video-translator-soniox-server
echo To start again:   docker start chrome-video-translator-soniox-server
echo   (no need to re-run this script unless the code changes)
echo.
pause

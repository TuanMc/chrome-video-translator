import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.config.settings import SONIOX_API_KEY
from app.websocket.translation_socket import router as translation_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No local model to load — unlike nllb-server/libre-server, this server
    # has nothing to warm up at startup: Soniox is a per-session cloud
    # WebSocket connection (see app/providers/soniox_client.py), not an
    # in-process or self-hosted model. Startup just checks a key is present.
    if not SONIOX_API_KEY:
        logger.warning(
            "SONIOX_API_KEY is not set — sessions will fail immediately. "
            "Get a key at https://soniox.com/ and set it before starting a session."
        )
    else:
        logger.info("Ready (SONIOX_API_KEY configured).")

    yield


app = FastAPI(title="Video Translator Local Server (Soniox)", lifespan=lifespan)
app.include_router(translation_router)


@app.get("/health")
async def health(request: Request) -> dict:
    # apiKeyConfigured is a configuration check, not a live reachability
    # check against Soniox (unlike libre-server's is_reachable()) — actually
    # pinging Soniox on every health poll would cost money. sttModelLoaded
    # and translationReady both just mirror it: Soniox does STT and
    # translation together in one combined session, so there's no
    # independent "STT ready" vs "translation ready" state here — kept as
    # two fields purely so the extension's existing shared health-parsing
    # shape (see extension/src/background/service-worker.ts) needs no
    # special-casing for a third provider.
    configured = bool(SONIOX_API_KEY)
    return {
        "status": "ok",
        "apiKeyConfigured": configured,
        "sttModelLoaded": configured,
        "translationReady": configured,
    }

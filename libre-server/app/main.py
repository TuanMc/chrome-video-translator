import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.config.settings import LIBRETRANSLATE_URL
from app.providers.speech_to_text.faster_whisper import load_model
from app.providers.translation.libretranslate import LibreTranslateProvider
from app.websocket.translation_socket import router as translation_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loaded once and reused for every session (requirement.md section 25) — do NOT
    # construct a WhisperModel per request, load time alone is seconds-to-tens-of-seconds.
    logger.info("Loading faster-whisper model (this can take a while on first run)...")
    model, device, compute_type = load_model()
    app.state.whisper_model = model
    app.state.whisper_device = device
    app.state.whisper_compute_type = compute_type
    # A single worker serializes inference calls onto one thread. Simpler than reasoning
    # about concurrent CTranslate2 calls, and fine for the assumed single-user local
    # usage; revisit if concurrent sessions become a real requirement.
    app.state.whisper_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")
    logger.info("Whisper ready.")

    # No in-process model to load here — translation goes over HTTP to a
    # separate LibreTranslate container (see docker-compose.yml). Constructed
    # once and reused for every session; readiness is a live reachability
    # check (see /health and translation_socket.py), not a load step.
    app.state.translation_provider = LibreTranslateProvider(LIBRETRANSLATE_URL)
    logger.info("Ready (translation backend: LibreTranslate at %s).", LIBRETRANSLATE_URL)

    yield

    app.state.whisper_executor.shutdown(wait=False)
    await app.state.translation_provider.aclose()


app = FastAPI(title="Video Translator Local Server (LibreTranslate)", lifespan=lifespan)
app.include_router(translation_router)


@app.get("/health")
async def health(request: Request) -> dict:
    provider = getattr(request.app.state, "translation_provider", None)
    return {
        "status": "ok",
        "sttModelLoaded": getattr(request.app.state, "whisper_model", None) is not None,
        # Live check, short timeout — LibreTranslate is a separate, independently
        # started container, so this can flip between requests (unlike an
        # in-process model, which is either loaded or the server isn't up yet).
        "translationReady": await provider.is_reachable() if provider is not None else False,
        "device": getattr(request.app.state, "whisper_device", "cpu"),
    }

import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.config.settings import NLLB_DEVICE, NLLB_QUANTIZE_CPU
from app.providers.speech_to_text.faster_whisper import load_model
from app.providers.translation.nllb import load_model as load_nllb_model
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

    nllb_model, nllb_tokenizer, nllb_device = load_nllb_model(NLLB_DEVICE, quantize_cpu=NLLB_QUANTIZE_CPU)
    app.state.nllb_model = nllb_model
    app.state.nllb_tokenizer = nllb_tokenizer
    app.state.nllb_device = nllb_device
    # Separate from whisper_executor so STT-for-the-next-segment and
    # translation-for-the-current-segment can genuinely run in parallel.
    app.state.nllb_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nllb")
    logger.info("All models ready.")

    yield

    app.state.whisper_executor.shutdown(wait=False)
    app.state.nllb_executor.shutdown(wait=False)


app = FastAPI(title="Video Translator Local Server", lifespan=lifespan)
app.include_router(translation_router)


@app.get("/health")
async def health(request: Request) -> dict:
    return {
        "status": "ok",
        "sttModelLoaded": getattr(request.app.state, "whisper_model", None) is not None,
        "translationModelLoaded": getattr(request.app.state, "nllb_model", None) is not None,
        "device": getattr(request.app.state, "whisper_device", "cpu"),
    }

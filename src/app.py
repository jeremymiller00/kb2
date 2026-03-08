import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from src.routes.api import router as api_router
from src.routes.insights import router as insights_router
from src.routes.research import router as research_router
from src.routes.ui import router as ui_router

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "kb.log"),
    ],
)

logger = logging.getLogger("kb.access")

app = FastAPI(title="kb", version="2.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Skip static file requests
    if request.url.path.startswith("/static"):
        return await call_next(request)

    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000

    query = f"?{request.url.query}" if request.url.query else ""
    logger.info(
        "%s %s%s %d %.0fms",
        request.method, request.url.path, query,
        response.status_code, duration_ms,
    )
    return response


app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(api_router, prefix="/api")
app.include_router(insights_router, prefix="/api/insights")
app.include_router(research_router, prefix="/api/research")
app.include_router(ui_router)


if __name__ == "__main__":
    import uvicorn
    from src.config import API_PORT
    uvicorn.run("src.app:app", host="0.0.0.0", port=API_PORT, reload=True)

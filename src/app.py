import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.routes.api import router as api_router
from src.routes.insights import router as insights_router
from src.routes.research import router as research_router
from src.routes.ui import router as ui_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="kb", version="2.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(api_router, prefix="/api")
app.include_router(insights_router, prefix="/api/insights")
app.include_router(research_router, prefix="/api/research")
app.include_router(ui_router)


if __name__ == "__main__":
    import uvicorn
    from src.config import API_PORT
    uvicorn.run("src.app:app", host="0.0.0.0", port=API_PORT, reload=True)

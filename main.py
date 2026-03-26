from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import settings
from models.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 启动定时任务
    from scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="AgentOps — AI-native DevOps Platform", lifespan=lifespan)

from api.lark_events import router as lark_router  # noqa: E402
from api.tasks import router as tasks_router  # noqa: E402

app.include_router(lark_router, prefix="/api/lark")
app.include_router(tasks_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.debug)

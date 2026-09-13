"""FastAPI entrypoint — lifespan wires services like Spring AppConfig."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from terminal_agent.api.auth import ApiKeyMiddleware
from terminal_agent.api.deps import AppState, build_app_state
from terminal_agent.api.routes import router
from terminal_agent.api.sse import SseHub
from terminal_agent.config import get_settings


def _resolve_web_dist(web_dist: str) -> Path | None:
    candidates: list[Path] = []
    if web_dist and web_dist.strip():
        candidates.append(Path(web_dist))
    candidates.extend(
        [
            Path("web/dist"),
            Path("../web/dist"),
            Path.cwd() / "web/dist",
            Path.cwd().parent / "web/dist",
        ]
    )
    for path in candidates:
        if (path / "index.html").is_file():
            return path.resolve()
    return None


def create_app(state: AppState | None = None) -> FastAPI:
    settings = state.settings if state is not None else get_settings()
    prebuilt = state

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_state = getattr(app.state, "app_state", None) or prebuilt or build_app_state(settings)
        app_state.memory_store.init()
        await app_state.persistence.init()
        app_state.simulator.start_clock()
        hub = SseHub(app_state.store, app_state.simulator, app_state.harness)
        hub.wire()
        app_state.sse_hub = hub
        app.state.app_state = app_state
        try:
            yield
        finally:
            await hub.shutdown()
            app_state.simulator.stop_clock()

    app = FastAPI(title="Terminal Agent Runtime", version="0.1.0", lifespan=lifespan)
    if prebuilt is not None:
        # Allow tests to inject a prebuilt graph; lifespan still starts clock/SSE.
        app.state.app_state = prebuilt
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ApiKeyMiddleware, settings=settings)
    app.include_router(router)

    dist = _resolve_web_dist(settings.web_dist)
    if dist is not None:
        index = dist / "index.html"

        @app.get("/")
        async def spa_root() -> FileResponse:
            return FileResponse(index)

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "terminal_agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()

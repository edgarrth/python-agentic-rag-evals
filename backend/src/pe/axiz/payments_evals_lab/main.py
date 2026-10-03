from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pe.axiz.payments_evals_lab.api.routes import router
from pe.axiz.payments_evals_lab.config.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Laboratorio reproducible de Evals para RAG, LLM y comportamiento agentic en payment processing.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()

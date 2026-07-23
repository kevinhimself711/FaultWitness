"""Production ASGI entrypoint configured only through workload environment."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI

from faultwitness.api.app import create_app
from faultwitness.api.postgres_store import PostgresIncidentStore


def _database_url() -> str:
    explicit = os.environ.get("FW_DATABASE_URL")
    if explicit:
        return explicit
    required = {
        name: os.environ.get(name) for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    }
    if any(not value for value in required.values()):
        raise RuntimeError("PostgreSQL connection environment is incomplete")
    user = quote(required["POSTGRES_USER"] or "", safe="")
    password = quote(required["POSTGRES_PASSWORD"] or "", safe="")
    database = quote(required["POSTGRES_DB"] or "", safe="")
    host = os.environ.get("FW_POSTGRES_HOST", "postgres.fw-data.svc.cluster.local")
    return f"postgresql://{user}:{password}@{host}:5432/{database}"


store = PostgresIncidentStore(_database_url())


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await store.connect()
    try:
        yield
    finally:
        await store.close()


app = create_app(store=store, lifespan=lifespan)

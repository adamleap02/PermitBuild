from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import alerts, auth, billing, export, ingest, jurisdictions, permits, properties, saved_searches

app = FastAPI(
    title="Construction Intel API",
    description=(
        "Database of US residential/commercial construction permits, enriched with "
        "property data, for contractors/suppliers/lenders/insurers/investors to find "
        "homes actively under construction."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(permits.router)
app.include_router(properties.router)
app.include_router(export.router)
app.include_router(ingest.router)
app.include_router(jurisdictions.router)
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(saved_searches.router)
app.include_router(alerts.router)


@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "service": "construction-intel-backend"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}

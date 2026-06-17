"""Goodwill Gold — FastAPI backend.

Serves the mobile PWA and exposes a single iterative ``POST /api/analyze`` endpoint
that runs the two-stage Claude pipeline (identify -> gate -> price).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import claude_client
from .schemas import AnalyzeRequest

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("goodwill_gold")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Goodwill Gold", version="1.0.0")


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> JSONResponse:
    if not req.images and not (req.make_model and req.make_model.strip()):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one photo or a make/model to look up.",
        )

    try:
        identified = claude_client.identify(req.images, req.make_model, req.notes)
    except Exception as exc:  # noqa: BLE001 — surface a clean error to the client
        log.exception("identify failed")
        raise HTTPException(status_code=502, detail=f"Identification failed: {exc}") from exc

    item = identified.get("item", {})
    condition = identified.get("condition", {})
    photos = identified.get("needs_more_photos", {})
    accessories = identified.get("accessories", {})

    need_photos = bool(photos.get("required"))
    need_accessories = bool(accessories.get("matters_to_value")) and req.accessories_included is None

    if need_photos or need_accessories:
        follow_ups: dict = {}
        if need_photos:
            follow_ups["photos"] = {
                "message": "A couple more photos would help me grade this accurately.",
                "requested_angles": photos.get("requested_angles", []),
            }
        if need_accessories:
            follow_ups["accessories"] = {
                "question": accessories.get("question")
                or "Are the original accessories included?",
                "items_to_check": accessories.get("items_to_check", []),
            }
        return JSONResponse(
            {
                "status": "need_more_info",
                "item": item,
                "condition": condition,
                "follow_ups": follow_ups,
            }
        )

    try:
        priced = claude_client.price(item, condition, req.accessories_included)
    except Exception as exc:  # noqa: BLE001
        log.exception("pricing failed")
        raise HTTPException(status_code=502, detail=f"Pricing failed: {exc}") from exc

    return JSONResponse(
        {
            "status": "complete",
            "item": item,
            "condition": condition,
            "currency": priced.get("currency", "USD"),
            "price_range": priced.get("price_range", {}),
            "verdict": priced.get("verdict", {}),
            "price_confidence": priced.get("confidence"),
            "sources": priced.get("sources", []),
        }
    )


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "model": os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")}


# Serve the PWA at the root. Mounted last so /api/* and /healthz take precedence.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

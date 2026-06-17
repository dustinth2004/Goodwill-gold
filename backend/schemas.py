"""Request/response models and the JSON Schemas used for Claude structured outputs.

The two schemas (IDENTIFY_SCHEMA, PRICE_SCHEMA) deliberately use only features that
Claude's structured outputs support: objects with ``additionalProperties: false``,
string ``enum``s, and arrays of objects/strings. No numeric/length constraints
(``minimum``, ``maxLength``, etc.) — those are not supported and are validated in
application code instead.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# API request / response models
# --------------------------------------------------------------------------- #
class AnalyzeRequest(BaseModel):
    """Payload from the PWA. The endpoint is iterative: the client re-POSTs with
    added photos and/or the accessories answer until pricing can be produced."""

    images: list[str] = Field(
        default_factory=list,
        description="Item photos as base64 strings (raw base64 or data: URLs).",
    )
    make_model: Optional[str] = Field(
        default=None, description="Optional typed make / model / keywords."
    )
    notes: Optional[str] = Field(
        default=None, description="Optional free-text notes (visible flaws, size, etc.)."
    )
    accessories_included: Optional[bool] = Field(
        default=None,
        description="User's answer to the accessories follow-up, once asked.",
    )


# --------------------------------------------------------------------------- #
# Condition grades (kept in sync with the enum inside IDENTIFY_SCHEMA)
# --------------------------------------------------------------------------- #
CONDITION_GRADES = [
    "new_with_tags",
    "like_new",
    "good",
    "fair",
    "poor",
    "for_parts",
    "unknown",
]


# --------------------------------------------------------------------------- #
# Stage A — IDENTIFY schema
# --------------------------------------------------------------------------- #
IDENTIFY_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "item": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short human-readable name, e.g. 'Sony WH-1000XM4 headphones'.",
                },
                "category": {"type": "string"},
                "brand": {"type": "string"},
                "model": {"type": "string"},
                "attributes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Salient details: color, size, material, era, etc.",
                },
                "identification_confidence": {
                    "type": "number",
                    "description": "0.0-1.0 confidence in the item identification.",
                },
            },
            "required": [
                "title",
                "category",
                "brand",
                "model",
                "attributes",
                "identification_confidence",
            ],
        },
        "condition": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "grade": {"type": "string", "enum": CONDITION_GRADES},
                "confidence": {
                    "type": "number",
                    "description": "0.0-1.0 confidence in the condition grade.",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this grade — visible wear, damage, completeness.",
                },
            },
            "required": ["grade", "confidence", "rationale"],
        },
        "needs_more_photos": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "required": {
                    "type": "boolean",
                    "description": "True only when a specific angle would change the grade.",
                },
                "requested_angles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Concrete shots to take, e.g. 'back/serial label', 'underside of soles'.",
                },
            },
            "required": ["required", "requested_angles"],
        },
        "accessories": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "matters_to_value": {
                    "type": "boolean",
                    "description": "True when accessories materially change resale value.",
                },
                "question": {
                    "type": "string",
                    "description": "Yes/no question to ask the user, '' when not applicable.",
                },
                "items_to_check": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Accessories that matter, e.g. 'charger', 'original box', 'lens cap'.",
                },
            },
            "required": ["matters_to_value", "question", "items_to_check"],
        },
    },
    "required": ["item", "condition", "needs_more_photos", "accessories"],
}


# --------------------------------------------------------------------------- #
# Stage B — PRICE schema
# --------------------------------------------------------------------------- #
PRICE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "currency": {"type": "string", "description": "ISO currency code, e.g. 'USD'."},
        "price_range": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "steal_deal": {
                    "type": "number",
                    "description": "Buy at/below this for a clear flip win.",
                },
                "fair_market": {
                    "type": "number",
                    "description": "Typical sold price for this item in this condition.",
                },
                "top_resale": {
                    "type": "number",
                    "description": "Best realistic resale ceiling (the 'run-through' price).",
                },
            },
            "required": ["steal_deal", "fair_market", "top_resale"],
        },
        "verdict": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "buy_under": {
                    "type": "number",
                    "description": "Grab it if the store price is under this.",
                },
                "walk_over": {
                    "type": "number",
                    "description": "Walk away if the store price is over this.",
                },
                "one_liner": {
                    "type": "string",
                    "description": "Punchy in-store call, e.g. 'Steal under $25, pass over $40'.",
                },
            },
            "required": ["buy_under", "walk_over", "one_liner"],
        },
        "confidence": {
            "type": "number",
            "description": "0.0-1.0 confidence in the price range given the comps found.",
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "price": {"type": "string", "description": "Listed/sold price as text, '' if unknown."},
                    "marketplace": {
                        "type": "string",
                        "description": "e.g. 'eBay (sold)', 'Mercari', 'Poshmark', 'retail'.",
                    },
                },
                "required": ["title", "url", "price", "marketplace"],
            },
        },
    },
    "required": ["currency", "price_range", "verdict", "confidence", "sources"],
}

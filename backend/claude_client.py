"""Thin wrapper over the Anthropic SDK implementing the two analysis stages.

Stage A (``identify``): vision + structured output -> what the item is, its condition,
and whether we need more photos / an accessories answer.

Stage B (``price``): a ``web_search`` agentic loop to gather live resale comps, followed
by a structured-output pass that coerces the findings into the price JSON.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import anthropic

from . import prompts
from .schemas import IDENTIFY_SCHEMA, PRICE_SCHEMA

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
MAX_SEARCH_CONTINUATIONS = 5


def _make_client() -> anthropic.Anthropic:
    """Build the Anthropic client.

    Standard deployments set ``ANTHROPIC_API_KEY``. When only an OAuth bearer token
    is available (``ANTHROPIC_AUTH_TOKEN`` — e.g. running inside a Claude Code remote
    environment), use it and attach the required oauth beta header.
    """
    if not os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return anthropic.Anthropic(
            auth_token=os.environ["ANTHROPIC_AUTH_TOKEN"],
            default_headers={"anthropic-beta": "oauth-2025-04-20"},
        )
    return anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL from env


_client = _make_client()

_DATA_URL_RE = re.compile(r"^data:(?P<media>[^;]+);base64,(?P<data>.+)$", re.DOTALL)
_ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _image_block(raw: str) -> dict:
    """Build a base64 image content block from a raw base64 string or a data: URL."""
    media_type = "image/jpeg"
    data = raw.strip()
    match = _DATA_URL_RE.match(data)
    if match:
        media_type = match.group("media")
        data = match.group("data")
    if media_type not in _ALLOWED_MEDIA:
        media_type = "image/jpeg"
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def _first_text(response: Any) -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def _extract_json(text: str) -> dict:
    """Parse JSON, tolerating accidental prose/code fences around it."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        return json.loads(brace.group(0))
    raise ValueError(f"No JSON object found in model response: {text[:300]!r}")


# --------------------------------------------------------------------------- #
# Stage A — identify item + condition
# --------------------------------------------------------------------------- #
def identify(
    images: list[str],
    make_model: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    content: list[dict] = [_image_block(img) for img in images if img]

    lines = ["Assess this thrift-store item for resale."]
    if make_model:
        lines.append(f"Typed make/model/keywords: {make_model}")
    if notes:
        lines.append(f"User notes: {notes}")
    if not content:
        lines.append("(No photo provided — identify from the text above.)")
    content.append({"type": "text", "text": "\n".join(lines)})

    response = _client.messages.create(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=prompts.IDENTIFY_SYSTEM,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": IDENTIFY_SCHEMA}},
    )
    return _extract_json(_first_text(response))


# --------------------------------------------------------------------------- #
# Stage B — price via live web search
# --------------------------------------------------------------------------- #
def _run_web_search(query_text: str) -> Any:
    """Run the web_search agentic loop, resuming on pause_turn, and return the
    final response object."""
    messages: list[dict] = [{"role": "user", "content": query_text}]
    response = _client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=prompts.PRICE_SEARCH_SYSTEM,
        messages=messages,
        tools=[WEB_SEARCH_TOOL],
    )
    continuations = 0
    while response.stop_reason == "pause_turn" and continuations < MAX_SEARCH_CONTINUATIONS:
        messages.append({"role": "assistant", "content": response.content})
        response = _client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=prompts.PRICE_SEARCH_SYSTEM,
            messages=messages,
            tools=[WEB_SEARCH_TOOL],
        )
        continuations += 1
    return response


def price(item: dict, condition: dict, accessories_included: Optional[bool]) -> dict:
    title = item.get("title") or item.get("model") or item.get("brand") or "item"
    attrs = ", ".join(item.get("attributes", []))
    grade = condition.get("grade", "unknown")

    if accessories_included is True:
        acc = "Original accessories ARE included."
    elif accessories_included is False:
        acc = "Original accessories are NOT included."
    else:
        acc = "Accessory completeness unknown."

    query = (
        f"Find current secondhand resale prices for: {title}.\n"
        f"Brand: {item.get('brand', '')}  Model: {item.get('model', '')}\n"
        f"Attributes: {attrs}\n"
        f"Condition grade: {grade}. {acc}\n"
        "Search eBay sold listings, Mercari, Poshmark, Facebook Marketplace, and retail."
    )

    search_response = _run_web_search(query)
    research = _first_text(search_response).strip() or (
        f"No comps were found via search for {title}. Estimate conservatively from "
        "general resale knowledge and return empty sources."
    )

    fmt_response = _client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=prompts.PRICE_FORMAT_SYSTEM,
        messages=[{"role": "user", "content": f"Pricing research:\n\n{research}"}],
        output_config={"format": {"type": "json_schema", "schema": PRICE_SCHEMA}},
    )
    return _extract_json(_first_text(fmt_response))

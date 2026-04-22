"""Economic calendar provider for high-impact news restrictions."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

import httpx

from app.config import get_settings

_CACHE_LOCK = asyncio.Lock()
_CACHE_EXPIRY = 0.0
_CACHE_EVENTS: list[dict] = []


def _parse_event(raw: dict) -> dict | None:
    """Normalize a Forex Factory export row into the engine's event shape."""
    event_time = raw.get("date")
    if not event_time:
        return None

    try:
        parsed_time = datetime.fromisoformat(event_time)
    except ValueError:
        return None

    country = str(raw.get("country") or "").upper().strip()
    impact = str(raw.get("impact") or "").strip().title()
    title = str(raw.get("title") or "").strip()
    if not country or not impact or not title:
        return None

    return {
        "title": title,
        "country": country,
        "date": parsed_time,
        "impact": impact,
    }


async def _fetch_calendar_events() -> list[dict]:
    settings = get_settings()
    headers = {
        "User-Agent": "PropGuardAI/1.0 (+https://propguard-ai.vercel.app)",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(
        timeout=settings.economic_calendar_timeout_seconds,
        headers=headers,
        follow_redirects=True,
    ) as client:
        response = await client.get(settings.economic_calendar_url)
        response.raise_for_status()
        payload = response.json()

    events: list[dict] = []
    for item in payload if isinstance(payload, list) else []:
        parsed = _parse_event(item)
        if parsed:
            events.append(parsed)
    return events


async def get_high_impact_events() -> list[dict]:
    """Return cached high-impact economic events from Forex Factory export."""
    global _CACHE_EVENTS, _CACHE_EXPIRY

    settings = get_settings()
    now = time.time()
    if _CACHE_EVENTS and now < _CACHE_EXPIRY:
        return list(_CACHE_EVENTS)

    async with _CACHE_LOCK:
        now = time.time()
        if _CACHE_EVENTS and now < _CACHE_EXPIRY:
            return list(_CACHE_EVENTS)

        events = await _fetch_calendar_events()
        high_impact = [event for event in events if event["impact"] == "High"]
        _CACHE_EVENTS = high_impact
        _CACHE_EXPIRY = now + settings.economic_calendar_cache_ttl_seconds
        return list(_CACHE_EVENTS)

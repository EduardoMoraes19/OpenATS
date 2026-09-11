"""Wraps every 2xx JSON response from /api/* and /public/* in {"data": ...},
matching the `res.json({data: ...})` convention the TS controllers use
almost universally (confirmed via grep: 70+ occurrences across
backend/src/modules/*.controller.ts and backend/src/routes/public.routes.ts).
`/health` and `/oauth/*` are outside these prefixes already, so they are
untouched - matching the one confirmed TS exception (`/health` returns a
bare `{status, checks}`).

A response whose top-level JSON is already a dict containing a "data" key
is left untouched, so an endpoint that needs extra top-level siblings next
to "data" (e.g. `{"data": candidate, "stageAutomation": {...}}`,
`{"data": deleted, "count": N}`, pagination envelopes) can simply return
that shape directly - the middleware only fills in the common bare-body
case, it never overwrites an explicit envelope.
"""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_ENVELOPE_PREFIXES = ("/api/", "/public/")


class EnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if not request.url.path.startswith(_ENVELOPE_PREFIXES):
            return response
        if response.status_code == 204 or not (200 <= response.status_code < 300):
            return response
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return response

        body = b"".join([section async for section in response.body_iterator])
        try:
            payload = json.loads(body)
        except ValueError:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        if not (isinstance(payload, dict) and "data" in payload):
            payload = {"data": payload}

        new_body = json.dumps(payload).encode("utf-8")
        headers = dict(response.headers)
        headers["content-length"] = str(len(new_body))
        return Response(
            content=new_body,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )

"""Pure rendering engine, equivalent to
backend/src/modules/template/template-engine.service.ts.

`{{var}}` regex substitution against a flat context dict - unresolved
variables are left as-is, matching the TS behavior (no error on missing
keys).
"""

from __future__ import annotations

import re
from typing import Any

_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def replace_variables(text: str, context: dict[str, str]) -> str:
    def _substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        return context.get(key, match.group(0))

    return _VAR_PATTERN.sub(_substitute, text)


def _render_block_html(block: dict[str, Any], context: dict[str, str]) -> str:
    block_type = block.get("type")
    content = replace_variables(block.get("content", ""), context) if "content" in block else ""

    if block_type == "heading":
        return f'<h1 style="margin:0 0 16px;font-size:22px;">{content}</h1>'
    if block_type == "text":
        return f'<p style="margin:0 0 16px;line-height:1.5;">{content}</p>'
    if block_type == "button":
        url = replace_variables(block.get("url", ""), context)
        return (
            f'<a href="{url}" style="display:inline-block;background:#0a0a0a;color:#fff;'
            f'text-decoration:none;padding:12px 24px;border-radius:8px;margin:16px 0;">{content}</a>'
        )
    if block_type == "image":
        url = replace_variables(block.get("url", ""), context)
        alt = replace_variables(block.get("alt", ""), context)
        return f'<img src="{url}" alt="{alt}" style="max-width:100%;" />'
    if block_type == "divider":
        return '<hr style="border:none;border-top:1px solid #e5e5e5;margin:24px 0;" />'
    if block_type == "spacer":
        height = block.get("height", 24)
        return f'<div style="height:{height}px;"></div>'
    return ""


def render_json(blocks: list[dict[str, Any]], context: dict[str, str]) -> list[dict[str, Any]]:
    rendered = []
    for block in blocks:
        new_block = dict(block)
        if "content" in new_block:
            new_block["content"] = replace_variables(new_block["content"], context)
        if "url" in new_block:
            new_block["url"] = replace_variables(new_block["url"], context)
        rendered.append(new_block)
    return rendered


def render_html(body: str | list[dict[str, Any]], context: dict[str, str]) -> str:
    if isinstance(body, str):
        return replace_variables(body, context)
    return "".join(_render_block_html(block, context) for block in body)


def compile_template(
    *, subject: str, body_json: str | list[dict[str, Any]], context: dict[str, str]
) -> dict[str, Any]:
    return {
        "subject": replace_variables(subject, context),
        "bodyJson": (
            replace_variables(body_json, context)
            if isinstance(body_json, str)
            else render_json(body_json, context)
        ),
        "html": render_html(body_json, context),
    }

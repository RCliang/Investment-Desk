"""
Unit tests for MinerU ZIP extraction helper `_download_and_extract_markdown`.

All tests monkeypatch `requests.get` — no real network calls.

Coverage:
1. Happy path: ZIP contains full.md → extracted correctly
2. Missing full.md → RuntimeError with diagnostic
3. Bad ZIP bytes → RuntimeError
4. Case-insensitive fallback: subdir/Full.md matched via suffix
"""

from __future__ import annotations

import io
import zipfile

import pytest
import requests

from app.services import mineru_service as m


def _make_zip(entries: dict[str, str]) -> bytes:
    """Build an in-memory ZIP with the given filename → content mapping."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in entries.items():
            zf.writestr(name, body)
    return buf.getvalue()


class _FakeResp:
    """Minimal stand-in for requests.Response."""

    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        pass


def _patch_get(monkeypatch, payload: bytes):
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, stream=False, timeout=None: _FakeResp(payload),
    )


def test_download_and_extract_markdown_happy_path(monkeypatch):
    zip_bytes = _make_zip({
        "full.md": "# 标题\n\n正文内容",
        "layout.json": "{}",
        "images/x.png": "",
    })
    _patch_get(monkeypatch, zip_bytes)

    md = m._download_and_extract_markdown("https://fake/zip")
    assert "标题" in md
    assert "正文内容" in md


def test_download_and_extract_markdown_missing_full_md(monkeypatch):
    zip_bytes = _make_zip({"layout.json": "{}", "origin.pdf": ""})
    _patch_get(monkeypatch, zip_bytes)

    with pytest.raises(RuntimeError, match="mineru_zip_missing_full_md"):
        m._download_and_extract_markdown("https://fake/zip")


def test_download_and_extract_markdown_bad_zip(monkeypatch):
    _patch_get(monkeypatch, b"not a zip")

    with pytest.raises(RuntimeError, match="mineru_zip_bad_zip"):
        m._download_and_extract_markdown("https://fake/zip")


def test_download_and_extract_markdown_case_insensitive_fallback(monkeypatch):
    """Defensive: docs say full.md but tolerate Full.md in a subdir."""
    zip_bytes = _make_zip({
        "subdir/Full.md": "# ok",
        "meta.json": "{}",
    })
    _patch_get(monkeypatch, zip_bytes)

    md = m._download_and_extract_markdown("https://fake/zip")
    assert md == "# ok"

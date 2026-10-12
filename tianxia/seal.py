"""玉璽碎片的規則（docs/superpowers/specs/2026-10-11-玉璽碎片-design.md；計畫 docs/superpowers/plans/2026-10-12-玉璽-1-核心.md）。"""
from __future__ import annotations

from .models import Content


def on(content: Content) -> bool:
    """碎片開著：Config.seal.enabled，而且內容有 content/seal.json（測試內容沒有＝關著）。"""
    return content.config.seal.enabled and bool(content.seal)

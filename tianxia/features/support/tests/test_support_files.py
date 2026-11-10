"""客服單的截圖（客服自動受理第 215 批；設計 5.1、5.5）：檔頭認種類、旁檔的 files 表、上傳（串流累計、超過就停）、看圖（主人與客服，其他人 404 同一句）。"""
from __future__ import annotations

import pytest

from tianxia.features.support import rules

PNG = b"\x89PNG\r\n\x1a\n"
JPG = b"\xff\xd8\xff\xe0"
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 "


def test_image_kind_by_magic():
    assert rules.image_kind(PNG + b"rest") == "png"
    assert rules.image_kind(JPG + b"rest") == "jpg"
    assert rules.image_kind(WEBP + b"rest") == "webp"
    assert rules.image_kind(b"GIF89a" + b"\x00" * 10) is None
    assert rules.image_kind(b"") is None
    assert rules.image_kind(b"RIFF\x10\x00\x00\x00WAVE") is None
    assert rules.image_kind(b"MZ\x90\x00" + PNG) is None
    # 只看前 12 位元組：WebP 的標記落在第 12 個位元組之後就不算
    assert rules.image_kind(b"RIFF\x10\x00\x00\x00\x00WEBP") is None
    assert set(rules.CONTENT_TYPES) == {"png", "jpg", "webp"}
    assert rules.CONTENT_TYPES["png"] == "image/png" and rules.CONTENT_TYPES["jpg"] == "image/jpeg" and rules.CONTENT_TYPES["webp"] == "image/webp"


def test_file_strings_have_placeholders():
    assert "{mb}" in rules.FILE_TOO_BIG and "3" in rules.FILE_TOO_BIG.format(mb=3)
    assert "{n}" in rules.FILES_FULL and "3" in rules.FILES_FULL.format(n=3)
    assert rules.FILE_NOT_IMAGE and "{" not in rules.FILE_NOT_IMAGE

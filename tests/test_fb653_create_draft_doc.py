"""FB-653：`state.CreateDraft` 的說明不再寫「擲品級」。

自創武學的品級不擲（武學重構之後；`create.finish` 的 `grade = content.config.arts.create_grade`），說明還寫「立名（付心得、擲品級、登記）」
會讓讀的人以為立名這一步有一擲。說明寫現在的規則；只是文字，不影響執行。
"""
from __future__ import annotations

from tianxia import create
from tianxia.state import CreateDraft


def test_the_draft_doc_says_the_grade_is_not_rolled():
    doc = CreateDraft.__doc__
    assert "擲品級" not in doc
    assert "付心得、登記" in doc and "create_grade" in doc


def test_the_create_module_agrees():
    assert "擲品級" not in create.__doc__
    assert "Config.arts.create_grade" in create.__doc__

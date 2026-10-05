"""這台機器自己的管理者名單（`.local/admins.txt` 與 `TIANXIA_ADMINS`）。

單獨一個檔是刻意的：這組測試原本接在 `tests/test_content.py` 的檔尾，而上游每次新增內容測試
也都加在那個位置，於是每次 pull 都在同一行衝突（連續三次）。搬出來之後兩邊再也碰不到。
"""


# ── 這台機器自己的管理者名單（.local/admins.txt）────────────


def test_local_admins_file_adds_to_the_tracked_list(tmp_path, monkeypatch):
    """直接改 content/config.json 的話，每次 pull 都會被蓋回去——所以本機設定放在 .local。"""
    from tianxia import content as content_mod

    local = tmp_path / "admins.txt"
    local.write_text("# 註解不算\n司馬\n\n  阿財  \n", encoding="utf-8")
    monkeypatch.setattr(content_mod, "ADMINS_FILE", local)
    monkeypatch.delenv("TIANXIA_ADMINS", raising=False)
    assert content_mod._with_local_admins(["Rayal"]) == ["Rayal", "司馬", "阿財"]


def test_the_env_var_also_adds_admins(tmp_path, monkeypatch):
    from tianxia import content as content_mod

    monkeypatch.setattr(content_mod, "ADMINS_FILE", tmp_path / "nope.txt")
    monkeypatch.setenv("TIANXIA_ADMINS", "阿財, 髒腳 ,")
    assert content_mod._with_local_admins(["Rayal"]) == ["Rayal", "阿財", "髒腳"]


def test_local_admins_never_drop_the_tracked_ones(tmp_path, monkeypatch):
    from tianxia import content as content_mod

    local = tmp_path / "admins.txt"
    local.write_text("Rayal\n", encoding="utf-8")  # 重複的不會列兩次
    monkeypatch.setattr(content_mod, "ADMINS_FILE", local)
    monkeypatch.delenv("TIANXIA_ADMINS", raising=False)
    assert content_mod._with_local_admins(["Rayal"]) == ["Rayal"]


def test_no_local_file_and_no_env_changes_nothing(tmp_path, monkeypatch):
    from tianxia import content as content_mod

    monkeypatch.setattr(content_mod, "ADMINS_FILE", tmp_path / "nope.txt")
    monkeypatch.delenv("TIANXIA_ADMINS", raising=False)
    assert content_mod._with_local_admins(["Rayal"]) == ["Rayal"]

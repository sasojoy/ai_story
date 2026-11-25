"""易名帖改名時旁檔裡的鍵跟著換（評審焦點 3）：鍵換新的、*_shown 照說話那一刻；旁檔不在就什麼都不建。"""
from tianxia.core import renames
from tianxia.features.yiwen import store as yiwen_store


def _node(st, tale, by):
    return st.add_node(tale=tale, parent=0, depth=1, pick="官軍", typed=False, by=by, shown="舊名", luck="good", text=["一段"],
                       options=[], ledger=[], fallback=True, at=1.0, branch_cap=5, free_branches=2, can_pay=False, own=True)


def test_rename_moves_keys_keeps_shown(tmp_path):
    db = tmp_path / "main.db"
    st = yiwen_store.for_db(db)
    tid = st.open_tale(season=1, opening="fog_figure", place="p", by="舊名", shown="舊名", at=0.0)
    nid = _node(st, tid, "舊名").node["id"]
    st.step_walk(tale=tid, account="舊名", season=1, node=nid, at=1.0)
    renames.run(db, "舊名", "新名")
    tale, node = st.tale(tid), st.node(nid)
    assert tale["discoverer"] == "新名" and tale["discoverer_shown"] == "舊名"
    assert node["by"] == "新名" and node["by_shown"] == "舊名"
    assert st.walk(tid, "新名") is not None and st.walk(tid, "舊名") is None


def test_rename_without_side_file_creates_nothing(tmp_path):
    db = tmp_path / "other.db"
    renames.run(db, "舊名", "新名")
    assert not yiwen_store.side_path(db).exists()

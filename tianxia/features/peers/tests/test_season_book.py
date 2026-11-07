"""換季的頭銜簿（title_book）：玩家互動包的 on_season_start（原本在 Game._reset_player_for_new_season 的名帖那一段）。
全部拆包第 37 批合併時補（PM 認定第 1 條）：舊簿非空、其中一條跟這一季也掙到的頭銜重複時，換季之後的簿子是舊的照順序、
再接上這一季新掙到的，重複的那一條不再加。期望值照搬之前的行為寫（old.player.title_book + 新的裡不在舊簿上的）。"""
from __future__ import annotations

from test_social import _player

from tianxia import library


def test_the_title_book_keeps_the_old_order_and_skips_a_repeat(content):
    a = _player(content, "甲")
    p = a.state.player
    p.season_number = 3
    p.top_merits = 2  # 這一季掙到「決戰首功二次」
    art_id = "basic_fist"
    p.arts.append(art_id)  # 功法庫裡一門（測試內容的新角色身上沒有武學；同 tianxia/features/cultivation/tests/test_arts_pages_two.py）
    p.art_quality[art_id] = "絕學"  # 這一季也掙到「練成絕學一門」
    assert library.owned_arts(a.state) == [art_id]
    p.title_book = ["第1季 天下第一", "第3季 決戰首功二次", "第2季 名人榜第一"]  # 中間那一條跟這一季的重複
    a._reset_player_for_new_season(4)
    assert a.state.player.title_book == [
        "第1季 天下第一", "第3季 決戰首功二次", "第2季 名人榜第一",  # 舊的照順序
        "第3季 練成絕學一門",  # 這一季新掙到的接在後面；重複的「第3季 決戰首功二次」不再加
    ]

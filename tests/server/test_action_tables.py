"""殼的三張動作表照包分（全部拆包第 68 批；計畫 docs/superpowers/plans/2026-11-06-伺服器分包-第68批.md 第七節第 7 條）。

走過每一個 op 的成功路、轉型與預設值的是 same_behavior 的 switchboard 一軌；這裡只守搬完之後的形狀：表的先後、每一條歸哪一包、管理者工具的
暫停與 gate、籌備中的擋法（Game 委派上的裝飾器沒有跟著搬，表上那六條自己包）。
"""
from __future__ import annotations

import pytest

import server
from tianxia.core import registry
from tianxia.core.services import PREPARING_REFUSAL

MAIN_OWNERS = {
    "seclude": "seclusion", "smith_forge": "smithy", "smith_sell": "smithy", "smith_upgrade": "smithy", "smith_furnace": "smithy", "donate": "outlets",
    "tavern": "tavern", "anonymous": None, "gender": None, "story_seen": "story", "letter_read": "companions", "letter_decline": "companions",
    "hints_off": "guide", "skip_tutorial": "guide", "view_map": "guide", "view_orders": "guide", "view_tab": "guide", "guide_ack": "guide",
    "allocate": "cultivation", "growth": None, "newbie_drifter": "guide", "pill": None, "checkin": "checkin", "conquest_letter": "territory_acts",
    "seal_use": "seal", "sortie_go": "sortie", "sortie_answer": "sortie", "sortie_join": "sortie", "outing": "explore", "jieyi_leave": "jieyi",
    "zongmen_offer": "zongmen", "zongmen_learn": "zongmen", "zongmen_page": "zongmen",
}
MENXIA_OWNERS = {
    "practice": "cultivation", "heal": None, "forge": "craft", "switch": "cultivation", "slot": "cultivation", "unslot": "cultivation",
    "create_begin": "craft", "create_pose": "craft", "create_back": "craft", "create_name": "craft", "create_cancel": "craft", "create_reroll": "craft",
    "ascend_dismiss": "cultivation", "cultivate": "cultivation", "melt": "cultivation", "melt_insight": "cultivation", "melt_many": "cultivation",
    "name": "cultivation", "name_divine": "smithy", "bind_art": "smithy", "join": "companions", "leave": "companions", "release": "companions",
    "wield": "gear", "dismantle": "gear", "feed": "gear", "repair_item": "smithy", "temper_item": "smithy", "dismantle_many": "gear", "chuangong": "cultivation",
}
# 搬之前 ADMIN_ACTIONS 的 33 個名字，照原本的先後（第二輪第 90 批最後 13 個進管理者包，殼的那一張拿掉了）
ADMIN_OWNERS = {
    "outing_erase": "explore", "open_season": "admin", "end_season": "admin", "next_season": "admin", "pause_clock": "admin", "resume_clock": "admin", "fast_forward": "admin",
    "start_battle": "battle", "fire": "admin", "push_trend": "admin", "schedule": "admin", "jump_next": "admin", "set_trend": "admin", "resolve_event": "admin", "clear_lock": "admin",
    "cancel_battle": "battle", "revive_figure": "figure_acts", "issue_orders": "military", "rotate_seats": "military", "start_showdown": "battle",
    "summon": "military", "give_opportunity": "military", "give_fragment": "military", "seal_emerge": "seal", "seal_stir": "seal", "seal_assign": "seal",
    "seal_duel": "seal", "seal_fix": "seal", "seal_cancel": "seal", "seal_sink_check": "seal", "seal_mandate": "seal", "mingtie_remove": "peers", "mingtie_restore": "peers",
}
# Game 的委派掛著 @_not_while_preparing、包裡的函式沒有的那六個（計畫第七節第 1 條）；模組路徑是表最後叫到的那一支
GUARDED = {
    ("MAIN_ACTIONS", "checkin"): ("tianxia.features.checkin.actions", "check_in"),
    ("MENXIA_ACTIONS", "name_divine"): ("tianxia.features.smithy.divine_actions", "name_divine"),
    ("MENXIA_ACTIONS", "bind_art"): ("tianxia.features.smithy.divine_actions", "bind_art"),
    ("MENXIA_ACTIONS", "join"): ("tianxia.features.companions.actions", "add_to_team"),
    ("MENXIA_ACTIONS", "leave"): ("tianxia.features.companions.actions", "remove_from_team"),
    ("MENXIA_ACTIONS", "release"): ("tianxia.features.companions.actions", "release_companion"),
}


def _module_of(pack: str | None) -> str:
    return "server" if pack is None else f"tianxia.features.{pack}.routes"


@pytest.mark.parametrize(("table", "order", "owners"), [
    (server.MAIN_ACTIONS, server.MAIN_ACTION_ORDER, MAIN_OWNERS),
    (server.MENXIA_ACTIONS, server.MENXIA_ACTION_ORDER, MENXIA_OWNERS),
])
def test_tables_keep_the_written_order_and_each_op_lives_in_its_package(table, order, owners):
    assert type(table) is dict  # 測試照舊 setitem、取值
    assert list(table) == list(order) == list(owners)
    for op, fn in table.items():
        assert fn.__module__ == _module_of(owners[op]), op  # functools.wraps 把裝飾器那六條的 __module__ 帶過來


def test_admin_names_kept_their_relative_order_wherever_they_went():
    names = list(ADMIN_OWNERS)
    for feature in registry.FEATURES:
        mine = [op for op in feature.admin_tools(server) if op in ADMIN_OWNERS]
        assert mine == [n for n in names if ADMIN_OWNERS[n] == feature.name], feature.name
    moved = [n for n in names if ADMIN_OWNERS[n] is not None]
    assert len(names) == 33 and len(moved) == 33


def test_moved_admin_tools_stay_open_while_paused_and_have_no_gate():
    """原本 ADMIN_ACTIONS 那一條：暫停中照做（act(paused_ok=True)）、沒有 404。"""
    for op, pack in ADMIN_OWNERS.items():
        if pack is not None:
            tool = server.FEATURE_ADMIN_ACTIONS[op]
            assert tool.paused_ok is True, op
            assert tool.gate() is None, op
            assert tool.run.__module__ == _module_of(pack), op


class _Preparing:
    """籌備中的那一份 Game：裝飾器只問這兩支；別的一碰就炸（包裡的函式不該被叫到）。"""

    def _preparing(self) -> bool:
        return True

    def _log(self, lines: list[str]) -> list[str]:
        return lines


class _Open(_Preparing):
    def _preparing(self) -> bool:
        return False


@pytest.mark.parametrize(("table", "op"), list(GUARDED))
def test_the_six_guarded_ops_keep_the_preparing_refusal(table, op, monkeypatch):
    """第七節第 1 條：這六條不再經過 Game 的委派，籌備中的擋法掛在表上；擋下來的時候包裡的函式一次都沒叫，開了才叫。"""
    module, name = GUARDED[table, op]
    calls = []
    monkeypatch.setattr(f"{module}.{name}", lambda *args, **kwargs: calls.append(args[1:]) or ["做了。"])
    action = getattr(server, table)[op]
    assert action(_Preparing(), {}) == [PREPARING_REFUSAL] and calls == []
    assert action(_Open(), {}) == ["做了。"] and len(calls) == 1

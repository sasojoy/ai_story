"""減法季批 2 修正輪（PM 2026-10-26；試玩回饋 FB-815～819 與自家營寨比劃的經驗）：
1. 自家營寨跟同袍比劃只給對手那一路的 camp_spar_share（三成），不是全額；
2. 只有頭目的地點（官軍在長社）遇敵拍不再一定撞上頭目：一趟照 5% × 名聲倍數擲一次，沒擲中就當這裡沒有對手（遭遇那一格分給其餘三類）；
   頭目吃掉要選的那一拍時，紀錄標記不寫那一拍；
3. 新手目標 field2 在探索一顆開著時，在二級以上的地方遇敵拍打贏也記上，字改成出門探索的說法；
4. 討伐懸賞與散人出陣的說明在探索一顆開著時不再寫「尋敵」；
5. 45 級的打探懸賞出門一趟交差、經驗換成心得時，段落結尾也寫「境界已到」；
6. 城裡打地痞打成平手寫平手的句子（town_draw），不是吃了虧。
用正式內容（season21），整個檔標 slow。"""
from __future__ import annotations

from unittest import mock

import pytest
from conftest import real_content
from jianfa_kit import jianfa_game, jianfa_rules, ready

from tianxia import bounties, explore_one, renown, sortie, team
from tianxia.encounter import EncounterResult
from tianxia.engine import drill_share
from tianxia.state import Bounty

pytestmark = pytest.mark.slow


def _fight(tier: str = "大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _beats(*beats: str):
    return mock.patch.object(explore_one, "draw", return_value=list(beats))


def _reset(game) -> None:
    """下一趟：體力補滿、沒有待選的事件與感悟。"""
    game.state.player.stamina = 250.0
    game.state.pending_event = None
    game.state.player.sensing = None


# ── 1. 自家營寨比劃只給三成 ──


def test_camp_sparring_pays_the_share_of_the_comrade_squad_not_all_of_it():
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)  # 對手 40 級以下的檔：不吃對手那一道、今天第一場不吃疲勞
    p, cfg = game.state.player, game.content.config.jianfa
    host = game.outing_plan().foe
    assert cfg.camp_spar_share == 0.3 and (host.exp, host.reward_xinde) == (40, 35)
    exp0, xinde0 = p.member.exp, p.stats.get("xinde", 0)
    with _beats("encounter", "material", "material"):
        game.choose("act:explore")
    assert p.member.exp - exp0 == drill_share(host.exp, 0.3) == 12  # 以前全額 40
    assert p.stats.get("xinde", 0) - xinde0 == drill_share(host.reward_xinde, 0.3) == 11  # 心得照同一個比例（以前 35）


def test_the_camp_share_is_one_number_in_the_config():
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)
    game.content.config.jianfa.camp_spar_share = 0.5
    p = game.state.player
    exp0 = p.member.exp
    with _beats("encounter", "material", "material"):
        game.choose("act:explore")
    assert p.member.exp - exp0 == 20


def test_camp_sparring_share_stacks_with_the_fatigue_gate():
    """疲勞那一道照舊乘在上面：第 16 場是 0.8 倍的三成。"""
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)
    p = game.state.player
    p.fight_day, p.fights_today = game._pill_day(), 15
    exp0 = p.member.exp
    with _beats("encounter", "material", "material"):
        game.choose("act:explore")
    assert p.member.exp - exp0 == drill_share(40, 0.3 * 0.8)



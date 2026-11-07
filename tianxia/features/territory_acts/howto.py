"""地盤行動包：玩法說明「地盤」那一節（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from tianxia import conquest, rules, territory
from tianxia.core import features as features_core
from tianxia.core.howto_base import section as _section
from tianxia.core.howto_base import tenth as _tenth
from tianxia.models import Content
from tianxia.state import WorldState


def conquest_lines(content: Content, season: WorldState | None = None) -> list[str]:
    """玩法說明「地盤」一節的領地爭奪版（第 38 項改版第一批；開關在這一季生效時取代拔河那一版；待 joy 潤）。數字讀 Config。
    season 給了而且約戰在這一季開著（減法季批 3b）：出陣、守勢行動、集火那三句換成約戰版（沒有守與混戰）；沒給、關著一個字都不變。"""
    cfg, terr = content.config.conquest, content.config.territory
    gather = f"{cfg.gather_bonus_chance * 100:g}%"
    lines = [
        "地圖分三種：官軍的領地、黃巾的領地，和中立地。中立地開季沒人佔，兩軍爭的就是它；各家的投靠點永遠是自家的，廣宗只照廣宗決戰易手。",
        "能挑的是跟自家領地有路直通的那一塊——中立地，或者敵方的領地，一塊一塊往前推。",
        f"三條戰線的大勢照兩軍佔了多少地來算：一條線上的中立地全被一方拿下，那條線往那一邊偏 {cfg.share:g} 點；"
        "打進敵方的領地份量加倍。時刻表的大事、事件、大勢人物、軍令照舊推線。",
        "出陣不再直接推戰線，推的是那一塊的進度：每一塊對每一個來攻的一方各有一條進度。在別人的地方、還沒人佔的中立地出陣是攻、"
        "推自己那一條；在自家的地方是守、把對面每一條都拉回來；照樣記貢獻。各家的大本營與廣宗不在爭奪之列：別人的攻不得，"  # 裁決 18
        "自家的守了也沒有進度。找不到對手的地方推不動。",
        # 裁決 24（PM 2026-10-20）；待 joy 潤
        "巡哨、傳道、保境安民這類守勢行動也只在自家的領地做：別人的地方、還沒人佔的中立地，那一顆灰著，按不下去。",
        f"哪一條推滿 100，那一塊當場易手：天下大事一句，推過的人照出力分銀兩、經驗、名望，推最多的上江湖史。剛易手的地 "
        f"{cfg.cooldown_minutes:g} 分鐘內兩邊都推不動，那一塊的加成也先停著。沒人推的地每天往回 {cfg.decay_per_day:g}。",  # 待 joy 潤
        f"同一邊的人一小時內一起推同一塊，每多一個人每一下多推 {cfg.focus_step * 100:g}%（最多 {cfg.focus_cap * 100:g}%）。"
        f"出陣時對面 {cfg.clash_minutes:g} 分鐘內在這一塊推過、人還在，就撞上打一場（照截殺的規矩，城裡也打、不搶東西）："
        f"贏的那一下多推 {(cfg.clash_scale - 1) * 100:g}%，輸的那一下白跑。守方把五成以上的進度拉回零，也照出力分守城功。",
        f"進度到 {cfg.letter_at:g}，那一邊這一週在任的第 4 階可以下戰書（一邊一天一張）：挑最近的攻城時段"
        f"（{cfg.slot_first // 60}:00～{cfg.slot_last // 60}:00 的整點或半點）打一場攻城戰，那一塊的進度凍結到打完。"
        f"開打前 {cfg.muster_minutes} 分鐘開集結，人要在那個大區才加得進去。攻城戰是決戰的縮小版：攻方贏了直接易手、"
        f"輸了進度砍半，守方沒人時打那裡的留守，攻方沒人到這一場作罷。軍餉是決戰的{_tenth(cfg.pay_share)}。",
        # 裁決 22（企劃者 2026-10-21）；待 joy 潤
        "兩軍都對同一塊中立地下了戰書，就併成一場三方混戰：那裡的守將兩邊都打，兩軍之間也照常交鋒；強攻打得到守將，"
        "戰線壓向哪一軍，那一軍打守將就越有力。誰補上守將最後一刀，這一塊就歸誰；回合打完守將還沒倒，照舊沒人佔。"
        "散人可以投效兩軍之一，或助守。",
        f"人站在自家領地：療傷、打造、買馬便宜{_tenth(1 - terr.own_price)}，在敵方的領地貴{_tenth(terr.enemy_price - 1)}"
        f"（新手期在敵方領地療傷不加價）；找素材有 {gather} 的機會多撿一個，靜心感悟更容易抓住。",
        "散人在開季是中立地的地方也算自家：一樣便宜、一樣多撿一份，不論那裡此刻被誰佔了。",
        "中立地站著另一批強對手，掉的東西也好；被佔下之後照樣在那裡，兩邊的人去都得打。",
        # 輿圖第三版（第 5 批改字）：沒有局勢層了，天下圖的地面與區圖的名字框照誰佔著上色；待 joy 潤
        "輿圖上，天下圖的地面、區圖名字框的顏色就是此刻誰佔著，灰的是還沒人佔的中立地；正在翻的地泛著攻方的顏色，易手時天下大事會傳一句。",
    ]
    if season is not None and conquest.duel_on(content, season):  # 約戰開著（減法季批 3b）：出陣是約戰、沒有守與混戰；待 joy 潤
        lines[3] = ("出陣不再直接推戰線，推的是那一塊的進度：每一塊對每一個來攻的一方各有一條進度。在別人的地方、還沒人佔的中立地出陣是貼約戰，"
                    "打贏推自己那一條；守是應戰，守住了把攻方那一條拉回來；照樣記貢獻。各家的大本營與廣宗不在爭奪之列，攻不得。")
        lines[4] = "巡哨、傳道、保境安民只在自家的領地做，不推線、一天記一點貢獻：別人的地方、還沒人佔的中立地，那一顆灰著。"
        lines[6] = (f"同一邊的人一小時內一起推同一塊（約戰的同去也算），每多一個人每一下多推 {cfg.focus_step * 100:g}%（最多 {cfg.focus_cap * 100:g}%）。"
                    "守方把五成以上的進度拉回零，也照出力分守城功。")
    lines[-1:-1] = features_core.howto_insert("land_seal", content, season)  # 碎片的來源那一句：判斷在玉璽包（HOWTO_INSERTS）
    return lines


def territory_lines(content: Content, allied: bool = False, season: WorldState | None = None) -> list[str]:
    """玩法說明「地盤」一節（地盤開著時＝領地爭奪，conquest_lines；待 joy 潤）。allied 留著給舊的呼叫寫法。"""
    return conquest_lines(content, season)


def land_section(content: Content, season: WorldState) -> list[str]:
    """「地盤」那一節（HOWTO_ORDER 的 land）：地盤開著才有。"""
    return _section("地盤", territory_lines(content, rules.haoqiang_allied(content, season), season)) if territory.on(content) else []

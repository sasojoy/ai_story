"""探索包的內容驗證（原本是核心 content.py 的 check_explore_one、check_outing_lines；主動搬六包第 3＋4 批搬進來：核心不 import 包，
content.validate 照 FEATURES 叫這一包的 check_content）。本體照搬，只換了搬走之後在別處的名字：

- 「旅人」與至少幾則（TRAVELER_TAG、TRAVELER_MIN）照舊寫在核心的 content.py（tests/core/test_jianfa_switch.py 從那裡拿、換掉 TRAVELER_MIN），
  這裡叫的時候讀那兩個模組屬性，換掉的照樣生效。
- 內容寫壞時錯誤的先後跟搬之前不同：這兩個驗證從 validate 的最後幾項挪到 check_features 那一處（正確的內容一個字都不變）。
"""
from __future__ import annotations

from tianxia import content as content_mod
from tianxia import explore_one  # 過渡：待搬（探索一顆的表、段落句子的組與鍵；第 4 批搬進這一包）
from tianxia.models import Content
from tianxia.zh import to_traditional  # 過渡：待搬（繁體）


def check_explore_one(c: Content, need) -> None:
    """減法季探索一顆（整合設計 4.1，批 2；Config.jianfa 開著的設定才驗，測試內容與週末設定關著不驗）：
    每個地點都靠自己的標籤歸得到一張探索表（explore_one.match；拼錯的標籤會靜靜掉進最後一張）；城裡換上的地痞是認得的隊伍、
    沒有陣營（不然會被當成自己人）；標了「旅人」的事件至少 content_mod.TRAVELER_MIN 則抽得到、而且都在野類的地點。
    四欄加起來 100、標籤只落一張表在數字模型（jianfa_numbers）自己驗。"""
    from tianxia.events import event_matches_location  # noqa: PLC0415  過渡：待搬（events → rules → …：在函式裡 import）

    cfg = c.config.jianfa
    if not (cfg.enabled and cfg.explore_one):
        return
    for loc in c.locations.values():
        need(explore_one.match(cfg, loc.tags) is not None,
             f"地點 {loc.id}：標籤 {loc.tags} 一張探索表都對不上（Config.jianfa.explore_tables；減法季探索一顆照它抽）")
    for sid in cfg.town_foes:
        need(sid in c.squads and c.squads[sid].faction is None, f"config.jianfa.town_foes：{sid} 要是認得的隊伍、不能有陣營")
    wild = {loc.id for loc in c.locations.values() if explore_one.kind_of(cfg, loc).kind == explore_one.WILD}
    travelers = []
    for event in c.events.values():
        if content_mod.TRAVELER_TAG not in event.tags:
            continue
        places = {loc.id for loc in c.locations.values() if event_matches_location(event, loc)}
        need("explore" in event.actions and bool(places) and places <= wild,
             f"事件 {event.id}：標了「{content_mod.TRAVELER_TAG}」要是探索抽得到、只在野類地點的事件（現在在 {sorted(places - wild) or '哪裡都不在'}）")
        travelers.append(event.id)
    need(len(travelers) >= content_mod.TRAVELER_MIN, f"標了「{content_mod.TRAVELER_TAG}」的野外事件只有 {len(travelers)} 則，至少要 {content_mod.TRAVELER_MIN} 則")


def check_outing_lines(c: Content, need) -> None:
    """探索一顆出門一趟的段落句子（content/outing_lines.json，減法季批 2；字待 joy 潤）：寫了的只能是認得的組與鍵
    （explore_one.LINE_KEYS），每一句照 explore_one.SAMPLE 填得進去、只用繁體中文、不寫阿拉伯數字（數字只在「得：…　失：…」那一行，
    是引擎拼的）；Config.jianfa 的探索一顆開著時每一個鍵都要有句子（沒寫的會退回 explore_one.FALLBACK 那一句，正式內容不准）。"""
    lines = c.outing_lines
    for group, table in lines.items():
        keys = explore_one.LINE_KEYS.get(group)
        need(keys is not None and isinstance(table, dict), f"outing_lines：不認得的組 {group}（要寫成「鍵：一串句子」）")
        for key, pool in (table.items() if keys is not None and isinstance(table, dict) else ()):
            need(key in keys, f"outing_lines.{group}：不認得的鍵 {key}")
            need(isinstance(pool, list) and bool(pool), f"outing_lines.{group}.{key}：要寫成一串句子")
            for text in pool if isinstance(pool, list) else []:
                where = f"outing_lines.{group}.{key}"
                try:
                    filled = str(text).format(**explore_one.SAMPLE)
                except (KeyError, IndexError, ValueError) as e:
                    need(False, f"{where}：「{text}」填不進去（{e}）")
                    continue
                need(bool(filled.strip()) and not any(ch.isdigit() for ch in str(text)), f"{where}：「{text}」不能空、不能有數字")
                need(to_traditional(str(text)) == str(text), f"{where}：文字只能用繁體中文（「{str(text)[:12]}」）")
    cfg = c.config.jianfa
    if cfg.enabled and cfg.explore_one:
        for group, keys in explore_one.LINE_KEYS.items():
            for key in keys:
                need(bool((lines.get(group) or {}).get(key)), f"outing_lines.{group} 缺少 {key}（減法季探索一顆開著時每一個鍵都要有句子）")

"""懸賞榜的店面畫面資料（店面獨立介面設計第四節；第二輪第 93 批，原本在 tianxia/shopview.py；計畫 docs/superpowers/plans/2026-11-07-第二輪-第93批.md）。

只讀：不改數值、不碰亂數、不 import engine。board_key 是懸賞榜這一下的情況鍵（actions 記掌櫃那一句時用）；店共用的（掌櫃那一句）在 core/shop_base。
page 是店面那一頁的組法（Feature.shop_view 轉交；core/features.shop_page 問）。
包外讀這一檔的測試改這一檔時 test_for 挑不到：另外跑 `git grep -l bounties_shop -- tests tianxia/features` 列的那幾個。
"""
from __future__ import annotations

from tianxia.core.shop_base import line_text
from tianxia.models import Content
from tianxia.state import GameState
from tianxia.world_state import WorldStateStore

from . import rules as bounties

_HELD_HEAD = bounties.HELD_FULL.partition("{")[0]


def board_key(problem: str | None, done: str) -> str:
    """懸賞榜這一下的情況鍵：做成了是 done；手上揭滿了（bounties.HELD_FULL，寫的是手上真的有幾張）一種；其餘的擋法一律 refused。"""
    if problem is None:
        return done
    return "held_full" if problem.startswith(_HELD_HEAD) else "refused"


# ── 懸賞榜（第四節）──
HELD_HEAD = "你手上揭著的（{n}／{cap}）"  # 待 joy 潤：最上面那一排的標題
SLOT_LEFT = "還能揭 {n} 張"  # 待 joy 潤：那一排最後的空格
HAVE_NOTE = "你有 {n} {unit}合用"  # 待 joy 潤：求兵的告示上
NO_FIT = "你身上沒有合用的"  # 待 joy 潤：求兵交不出時，放大的紙上「交出…」灰掉的原因
PRIZE_CHIP = "重賞"  # 待 joy 潤：21 天季告示正面那一格（FB-391；草圖丙）
PRIZE_SHORT = "另有重賞"  # 待 joy 潤：告示上（放大的紙上，賞那一段照 reward_text 寫是哪一種）
DROP_ASK = "把「{title}」放回榜上？放回去就不算你的了。"  # 待 joy 潤：放棄先問一次（選單上的 bounty:drop 沒有問句，問在網頁那一層）


def _headline(title: str) -> str:
    """告示上那一行大字：短標題「・」後面那一段（「打探・湖邊」→「湖邊」）。"""
    return title.partition("・")[2] or title


def board_view(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """懸賞榜的店面（第四節）：最上面一排手上揭著的（bounties.mine）；木板上是看得到的告示（bounties.visible，同選單的第二層），
    揭著的在前、交得出的求兵其次、其餘照現在的順序。每一張寫哪一方掛的、標題、要做什麼、賞、期限與名額（紙上的 due_line、告示上短的 due_short，FB-196）、重賞、求兵
    你有幾件合用（fitting）；底下那一顆照現在的選項 id：揭著的「放棄」（bounty:drop，問句在網頁）、求兵「交出…」（bounty:pick，
    交不出照 only_original 或 NO_FIT）、其餘「揭下」（bounty:take，揭不了照 take_problem）。第三層開著（bounty_pick 指著一張還交得出的；
    同懸賞榜包 actions.options 的判法）時多 picked 與 hand_in（hand_in_options 的每一顆，回到懸賞榜那一顆除外）。掛單的人（通緝的 poster）
    不寫：照現在的選單寫陣營，畫面不露出誰是假人（設計 6.6）。"""
    p = state.player
    shown = bounties.visible(state, content)
    mine = bounties.mine(state, content)
    mine_ids = {b.id for b in mine}
    picked = next((b for b in shown if b.id == p.bounty_pick and b.kind in bounties.GIVE_KINDS), None)
    picked_items = bounties.fitting(state, content, world, picked) if picked is not None else []
    if not picked_items:
        picked = None  # 那一張下榜了、交不出了就當它不存在（同懸賞榜包 actions.options）
    ranked = []
    for order, b in enumerate(shown):
        title = bounties.title(content, b)
        note = {
            "id": b.id, "kind": b.kind, "kind_name": bounties.KIND_NAMES.get(b.kind, b.kind), "issuer": bounties.issuer(content, b),
            "title": title, "head": _headline(title), "how": bounties.how(content, b, state), "reward": bounties.reward_text(state, content, b),
            "due": bounties.due_line(state, content, b), "short": bounties.due_short(b, content, state.world), "prize": PRIZE_SHORT if bounties.has_prize(content, b) else "",
            "held": b.id in mine_ids, "have": "",
        }
        tags = bounties.reward_tags(state, content, b)
        if tags is not None:  # 21 天季（第 5 批畫面第三組丙）：紙上的小籤、告示角上寫銀兩的小朱印、照等級的那一句
            note.update(tags=tags, corner=bounties.reward_bits(state, content, b).silver_short, level=bounties.level_note(state, content, b),
                        gift=bounties.gift_short(state, content, b), prize_chip=PRIZE_CHIP if note["prize"] else "")  # 附贈與重賞一格（FB-391）
        rank = 2
        if b.id in mine_ids:
            rank = 0
            note["action"] = {"id": f"bounty:drop:{b.id}", "verb": "drop", "enabled": True, "why": None, "confirm": DROP_ASK.format(title=title)}
        elif b.kind in bounties.GIVE_KINDS:
            items = bounties.fitting(state, content, world, b)
            if items:
                rank, note["have"] = 1, HAVE_NOTE.format(n=len(items), unit=bounties.unit_of(b))
            # 交不出的原因照規則：只有神器原品或本命兵器對得上的照實寫，不是才寫 NO_FIT
            why = None if items else (bounties.only_original(state, b).strip("（）") or NO_FIT)
            note["action"] = {"id": f"bounty:pick:{b.id}", "verb": "pick", "enabled": bool(items), "why": why}
        else:
            problem = bounties.take_problem(state, content, b)
            note["action"] = {"id": f"bounty:take:{b.id}", "verb": "take", "enabled": problem is None, "why": problem}
        ranked.append((rank, order, note))
    hand_in = []
    if picked is not None:
        hand_in = [
            {"id": o.id, "label": o.label, "enabled": o.enabled}
            for o in bounties.hand_in_options(state, content, world, picked, picked_items) if o.id != bounties.UNPICK_ID
        ]
    cap = content.config.bounties.max_taken
    held = [{"id": b.id, "title": bounties.title(content, b), "due": bounties.due_text(b, content, state.world)} for b in mine]
    left = max(0, cap - len(held))  # 截殺關了又開時手上可以超過上限（FB-155）：照實列，空格是 0
    return {
        "shop": "board",
        "sign": f"{content.locations[p.location].name}{bounties.BOARD}",
        "silver": p.stats.get("silver", 0),
        "line": line_text(state, content, "board"),
        "back": "bounty:back",
        "unpick": bounties.UNPICK_ID,
        "held": {"rows": held, "head": HELD_HEAD.format(n=len(held), cap=cap), "left": left, "left_text": SLOT_LEFT.format(n=left) if left else ""},
        "notes": [note for _rank, _order, note in sorted(ranked, key=lambda r: (r[0], r[1]))],
        "empty": "" if shown else bounties.BOARD_EMPTY,
        "picked": picked.id if picked is not None else None,
        "hand_in": hand_in,
    }


def page(ctx) -> dict:
    """懸賞榜那一頁（原本 core/page_view.shop_view 最後那一句）。"""
    return board_view(ctx.state, ctx.content, ctx.world)

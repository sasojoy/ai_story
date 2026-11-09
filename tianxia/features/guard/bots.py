"""親衛隊長的假人分數（bot_policy.score 問 bot_pick）：假人也養一個（設計稿第八節：別人看得到他，假人沒有會被看出來）。
假人不叫模型：事件與出師結算一律是固定的（actions._modelless）。救、收、挑做法、求學去處照名號雜湊，善待居多、也有狠心的，跟真人一樣什麼樣的都有。"""
from __future__ import annotations

from . import rules


def score(ctx, option) -> float | None:
    oid = option.id
    if not oid.startswith("guard:"):
        return None
    head, _, rest = oid[len("guard:"):].partition(":")
    name = ctx.state.player.name
    if head in ("meet", "open", "back", "study"):
        return 55.0
    if head == "stay":
        return 1.0
    if head == "school":  # 每個假人一處偏好的去處（照名號雜湊）；錢不夠那一顆按不下去，就挑別處
        keys = list(rules.texts.SCHOOLS)
        return 50.0 if keys[rules.seed("去處", name) % len(keys)] == rest else 10.0
    if head == "save":
        return 60.0
    if head in ("leave", "part", "later"):
        return 1.0
    if head == "adopt":
        return 50.0 + (5.0 if (rules.seed("性別", name) % 2 == 0) == (rest == "男") else 0.0)
    if head == "pick" and rest.isdigit():
        b = rules.book(ctx.state)
        # 每個假人一種待人的路數（0 溫、1 嚴、2 狠；七成溫、兩成嚴、一成狠），每一件再照雜湊偶爾換一下
        bias = rules.seed("路數", name) % 10
        lean = 0 if bias < 7 else 1 if bias < 9 else 2
        drift = rules.seed("這一件", name, b.seq if b is not None else 0) % 10
        want = lean if drift < 7 else (lean + 1) % 3
        return 50.0 if int(rest) == want else 10.0
    return None

"""門派的純規則（設計稿 v6，Joy 2026-11-08「不錯，按照設計稿動工」）：哪幾門是這一包的、拜不拜得了、叛出。
只讀傳進來的 Content 與 PlayerState；誰在哪裡、寫紀錄由 actions 做。"""
from __future__ import annotations

from tianxia.models import Content, Sect
from tianxia.state import PlayerState

SWITCH = "zongmen"  # Sect.switch 寫這個的是這一包管拜入的門派（白馬寺、南華觀、嵩陽劍廬、綠林山寨、鄉里結社）

# 待 joy 潤：這一包新寫給玩家看的字
JOIN = "拜入{sect}"
JOIN_CONFIRM = "拜入{sect}之後，換季也還是{sect}的人，不算投靠任何一方。拜入？"
LEAVE = "叛出{sect}"
LEAVE_CONFIRM = "叛出{sect}之後，這一季不能再回來。確定？"
TITLE = "門派"
JOINED = "你拜入了{sect}。"
FIRST_ART = "在這裡就能學本門的第一式【{art}】。"
LEFT = "你叛出了{sect}。"
GONE = "此刻無法這麼做。"
AT_GATE = "回{place}才學得"
GREET = {  # 拜入那一刻的一句（門派 id → 話）
    "baima": "知客僧替你剃了一綹頭髮，算是記名：「寺裡不問你從哪裡來，只問你肯不肯救人。」",
    "nanhua": "觀主沒有抬頭，只說了一句：「山上的東西，下山不要亂說。」",
    "songyang": "廬主丟給你一柄木劍：「劍是自己的，名字也是自己掙的。」",
    "lulin": "寨主拍了拍你的肩：「上了山，就是兄弟。」",
    "xiangshe": "社長把你的名字寫進社簿：「鄉里的事，就是你的事。」",
}


def own(sect: Sect) -> bool:
    return sect.switch == SWITCH


def sect_here(content: Content, location: str) -> Sect | None:
    """這個地方是哪一門（這一包管拜入的那幾門，開著的）。"""
    return next((s for s in content.sects.values() if own(s) and s.location == location and content.sect_open(s.id)), None)


def left_flag(sect_id: str) -> str:
    return f"叛出:{sect_id}"


def join_problem(p: PlayerState, content: Content, sect: Sect) -> str | None:
    if p.sect is not None or p.journey is not None or p.location != sect.location:
        return GONE
    if left_flag(sect.id) in p.flags:
        return GONE
    return None


def first_art(content: Content, sect_id: str) -> str | None:
    """本門的第一式（內容裡 learn.sect 是這一門的那一門武學）。"""
    return next((s.name for s in content.skills.values() if s.learn is not None and s.learn.sect == sect_id), None)


def join(p: PlayerState, content: Content, sect: Sect) -> list[str]:
    p.sect = sect.id
    out = [JOINED.format(sect=sect.name)]
    if sect.id in GREET:
        out.insert(0, GREET[sect.id])
    art = first_art(content, sect.id)
    if art:
        out.append(FIRST_ART.format(art=art))
    return out


def leave(p: PlayerState, content: Content) -> list[str]:
    sect = content.sects.get(p.sect) if p.sect else None
    if sect is None:
        return [GONE]
    p.flags.add(left_flag(sect.id))
    p.sect = None
    return [LEFT.format(sect=sect.name)]

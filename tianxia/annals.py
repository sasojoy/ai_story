"""過渡（開發規範手冊 3.11）：行狀拆兩半（全部拆包第 29 批之二）。

記一筆行狀的那一半（note、entry、watch、種類常數…）在 tianxia/core/annal_base.py；查詢與行狀頁那一半（profile、standing、
tier_*、xingshi_notes、rows）在 tianxia/features/zhuan/standing.py。舊名留在這裡，兩半都 re-export，拿到的是同一個物件。
"""
from tianxia.core.annal_base import *  # noqa: F401,F403
from tianxia.core.annal_base import _gear, _notable  # noqa: F401
from tianxia.features.zhuan.standing import *  # noqa: F401,F403
from tianxia.features.zhuan.standing import _said, _tier_side, _zhuan_end  # noqa: F401

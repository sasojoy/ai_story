"""過渡（開發規範手冊 3.11）：行狀拆兩半（全部拆包第 29 批之二）。

記一筆行狀的那一半（note、entry、watch、種類常數…）在 tianxia/core/annal_base.py；查詢與行狀頁那一半（profile、standing、
tier_*、xingshi_notes、rows）在 tianxia/features/zhuan/standing.py（那一份也 re-export 核心那一半）。舊名留成指到 standing 的別名：
`from tianxia import annals` 拿到同一個模組物件，兩半的每個名字都在、都是同一個物件，monkeypatch 照樣有效。"""
import sys

from tianxia.features.zhuan import standing as _standing

sys.modules[__name__] = _standing

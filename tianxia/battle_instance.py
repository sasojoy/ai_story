"""過渡（開發規範手冊 3.11）：全服決戰的規則搬進功能包 tianxia/features/battle/instance.py，資料型別與「讀」的那一半搬進核心 tianxia/core/battle_base.py（全部拆包第 54 批）。
這個名字留成指到包裡那個模組的別名（它 re-export 核心那一半）：`from tianxia import battle_instance`（殼的 server.py、scripts/ 的量表與 same_behavior、測試，含
monkeypatch.setattr(battle_instance, "assess_gamble"／"score_gamble"...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包或核心；呼叫端改完就拿掉。"""
import sys

from tianxia.features.battle import instance as _instance

sys.modules[__name__] = _instance

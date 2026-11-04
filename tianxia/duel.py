"""過渡（開發規範手冊 3.11）：單人頭目戰的規則搬進功能包 tianxia/features/bout/duel_rules.py（全部拆包第 12 批）。這個名字留成指到
同一個模組的別名：`from tianxia import duel`（還沒搬的舊模組 bot_policy、server、scripts 與測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。
頭目戰、擂台、奪璽單挑共用的底層在核心 tianxia/core/duel_base.py（那一份 re-export 它）。程式裡新寫的一律 import 包或核心；呼叫端改完就拿掉。"""
import sys

from tianxia.features.bout import duel_rules as _rules

sys.modules[__name__] = _rules

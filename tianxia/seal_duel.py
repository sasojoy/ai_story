"""過渡（開發規範手冊 3.11）：奪璽單挑的純規則搬進功能包 tianxia/features/seal/duel_rules.py（全部拆包第 28 批）。這個名字留成指到同一個模組的別名：
`from tianxia import seal_duel`（engine 還沒收的鍵名、bot_runner、server.py、scripts/measure_seal.py 與測試，含換掉 finish／resolve／open_round 的
patch）照舊拿到那一份。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.seal import duel_rules as _duel_rules

sys.modules[__name__] = _duel_rules

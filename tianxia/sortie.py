"""過渡（開發規範手冊 3.11）：出陣的規則搬進功能包 tianxia/features/sortie/rules.py（主動搬六包第 1 批）。這個名字留成指到同一個模組的
別名：`from tianxia import sortie`（還沒搬的舊模組 sortie_duel、atlas、bounties、howto、mapview、orders、bot_policy、server 與測試）照舊
拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.sortie import rules as _rules

sys.modules[__name__] = _rules

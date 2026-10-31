"""過渡（開發規範手冊 3.11）：出陣約戰的規則搬進功能包 tianxia/features/sortie/duel_rules.py（主動搬六包第 2 批）。這個名字留成指到同一個
模組的別名：`from tianxia import sortie_duel`（engine 的 choose、還沒搬的舊模組 atlas、bot、bot_policy、howto、腳本 measure_conquest 與
測試）照舊拿到那一份（換掉的屬性兩邊都看得到：tests 換 sortie_duel.advance、measure_conquest 換 open／advance，包裡照模組屬性叫）。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.sortie import duel_rules as _rules

sys.modules[__name__] = _rules

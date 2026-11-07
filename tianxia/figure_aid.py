"""過渡（開發規範手冊 3.11）：同陣營的人護著大勢人物（護衛、犒軍、探望）的規則搬進功能包 tianxia/features/figure_acts/figure_aid.py（全部拆包第 31 批）。這個名字留成指到同一個模組的
別名：`from tianxia import figure_aid`（world.py、social.py、server.py、scripts 與測試，含 monkeypatch.setattr(figure_aid, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。
figures.py 第 40 批起直接叫共用層自己的 aid_restore（犒軍與自然回復共用一天的上限搬進 figures，包 re-export 回原名）。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.figure_acts import figure_aid as _figure_aid

sys.modules[__name__] = _figure_aid

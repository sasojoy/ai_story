"""過渡（開發規範手冊 3.11）：託付與勸降的規則搬進功能包 tianxia/features/companions/errands.py（全部拆包第 19 批）。這個名字留成指到同一個模組的
別名：`from tianxia import errands`（還沒搬的舊模組 weekcard、scripts/try_errand_letter.py 與測試，含 monkeypatch.setattr(errands, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.companions import errands as _errands

sys.modules[__name__] = _errands

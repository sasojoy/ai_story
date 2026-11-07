"""過渡（開發規範手冊 3.11）：自創武學（五步、重悟帖）的規則搬進功能包 tianxia/features/craft/create.py（全部拆包第 44 批）。這個名字留成指到同一個模組的
別名：`from tianxia import create`（engine〔委派的型別註記〕、還沒搬的舊模組 skillview、bot、scripts 與測試，含 mock.patch.object(create, ...)）
照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.craft import create as _create

sys.modules[__name__] = _create

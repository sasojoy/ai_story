"""過渡（開發規範手冊 3.11）：每日簽到的規則搬進功能包 tianxia/features/checkin/checkin.py（全部拆包第 30 批；`on`、`PILL_FOUND` 是核心 core/services.py 的
checkin_on、PILL_FOUND，那一份 re-export）。這個名字留成指到同一個模組的別名：`from tianxia import checkin`（還沒搬的舊模組 bot、測試與腳本）
照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.checkin import checkin as _checkin

sys.modules[__name__] = _checkin

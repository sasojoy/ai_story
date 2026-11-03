"""過渡（開發規範手冊 3.11）：修練（絕學的契機與服丹衝關、舊存檔的絕學定名）搬進功能包 tianxia/features/arts/cultivation.py（全部拆包
第 23 批）。這個名字留成指到同一個模組的別名：`from tianxia import cultivation`（還沒搬的舊模組 bot、bot_policy、skillview，
scripts/measure_challenge.py 與測試，含 monkeypatch.setattr(cultivation, "seize"...)、mock.patch("tianxia.cultivation.seize")）照舊拿到那一份
（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.arts import cultivation as _cultivation

sys.modules[__name__] = _cultivation

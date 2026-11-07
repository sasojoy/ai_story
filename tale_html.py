"""過渡（開發規範手冊 3.11）：戰記頁的 HTML 搬進功能包 tianxia/features/tale/tale_html.py（全部拆包第 52 批）。這個名字留成指到同一個模組的
別名：`import tale_html` 照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.tale import tale_html as _tale_html

sys.modules[__name__] = _tale_html

"""過渡（開發規範手冊 3.11）：懸賞榜的規則搬進功能包 tianxia/features/bounties/rules.py（全部拆包第 45 批）。這個名字留成指到同一個模組的
別名：`from tianxia import bounties`（bot、bot_policy、scripts 與測試，含 mock.patch.object(bounties, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。
別人讀的那一半在核心 core/bounty_base.py（包 re-export 同一批）：程式裡新寫的一律讀核心或走事件、掛鉤；呼叫端改完就拿掉。"""
import sys

from tianxia.features.bounties import rules as _rules

sys.modules[__name__] = _rules

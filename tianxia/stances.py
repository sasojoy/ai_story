"""過渡（開發規範手冊 3.11）：人物心意的行動那一半（世界那一半在共用規則層 tianxia/stance_world.py，這一份 re-export）搬進功能包 tianxia/features/companions/stances.py（全部拆包第 19 批）。這個名字留成指到同一個模組的
別名：`from tianxia import stances`（還沒搬的舊模組 companion_agent、bot_policy、scripts/try_stances.py 與測試，含 monkeypatch.setattr(stances, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.companions import stances as _stances

sys.modules[__name__] = _stances

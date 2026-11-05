"""過渡（開發規範手冊 3.11）：discuss 搬進功能包 tianxia/features/peers/discuss.py（全部拆包第 38 批）。這個名字留成指到同一個模組的別名，
`from tianxia import discuss` 照舊拿到那一份（測試換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包。"""
import sys

from tianxia.features.peers import discuss as _discuss

sys.modules[__name__] = _discuss

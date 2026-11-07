"""過渡（開發規範手冊 3.11）：spar 搬進功能包 tianxia/features/peers/spar.py（全部拆包第 38 批）。這個名字留成指到同一個模組的別名，
`from tianxia import spar` 照舊拿到那一份（測試換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包。"""
import sys

from tianxia.features.peers import spar as _spar

sys.modules[__name__] = _spar

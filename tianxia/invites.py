"""過渡（開發規範手冊 3.11）：邀請的帳搬進功能包 tianxia/features/peers/invites.py（全部拆包第 37 批）。這個名字留成指到同一個模組的別名，
`from tianxia import invites` 照舊拿到那一份（測試、假人與還沒搬的切磋、論武、截殺、通緝換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包。"""
import sys

from tianxia.features.peers import invites as _invites

sys.modules[__name__] = _invites

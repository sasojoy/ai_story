"""過渡（開發規範手冊 3.11）：一條線自己的走法（選單、答題、打一場、結算、收尾、餘波）搬進功能包 tianxia/features/story/storyline.py（全部拆包第 30 批；
底座與換字在共用規則層 tianxia/story_base.py，那一份 re-export）。這個名字留成指到同一個模組的別名：`from tianxia import storyline`（還沒搬的舊模組
chapters、腳本與測試，含往 storyline.TASKS、FIGHT_HOOKS 裡登記的）照舊拿到那一份（換掉的屬性兩邊都看得到）。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.story import storyline as _storyline

sys.modules[__name__] = _storyline

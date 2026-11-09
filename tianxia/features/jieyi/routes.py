"""結義的動作表（/api/do/jieyi_leave：俠客頁門下那一段的「割袍斷義」）。只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）。"""
from tianxia.core.services import not_while_preparing

from . import actions


def main_actions(shell) -> dict:
    return {"jieyi_leave": not_while_preparing(lambda g, b: actions.leave(g))}

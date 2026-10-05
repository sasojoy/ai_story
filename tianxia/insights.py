"""意境（武學與成長設計 3.2）。Task 7 補完悟得、探索、合併的規則。"""
from __future__ import annotations

from .martial_arts import Insight
from .models import Content
from .world_state import WorldStateStore


def resolve(insight_id: str | None, content: Content, world: WorldStateStore) -> Insight | None:
    """基本意境（content/insights.json）或全服合併出來的意境；都找不到是 None。"""
    if insight_id is None:
        return None
    d = content.insights.get(insight_id)
    if d is not None:
        return Insight(id=d.id, name=d.name, attribute=d.attribute, lean=d.lean, note=d.desc)
    return world.get_insight(insight_id)

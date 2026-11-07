"""guide 這一包的測試，從 tests/web/test_jianghu_page_web.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from __future__ import annotations
import pytest
from jianghu_kit import MUSTER_SCENE, _guide, node  # noqa: F401

pytestmark = pytest.mark.whole_content


@node
def test_an_opened_step_box_stays_open_while_the_countdown_ticks_and_folds_when_told():
    """點開了：輪詢倒數變了（場景的字跟著變）也不收回去；自己按「收起」才收；集結結束（開打了）就回到平常的樣子（攤開），
    下一場集結又從收著開始。"""
    script = """
      const out = [kind(step)];
      H.openGuide(step); out.push(kind(step));
      S.main = { scene: S.main.scene.replace("12 分 5", "11 分 55") }; out.push(kind(step));
      S.main = { scene: "<p><strong>長社火攻</strong></p>\\n<p>【第一幕】（第 1／9 回合）火起</p>\\n<hr />\\n<p>【長社】</p>" }; out.push(kind(step));
      S.main = { scene: S.main.scene.replace("【第一幕】（第 1／9 回合）火起", "集結中，還剩現實 9 分 0 秒。") }; out.push(kind(step));
      H.openGuide(step); H.shutGuide(step); out.push(kind(step));
      return out;"""
    assert _guide(script, MUSTER_SCENE.format("12 分 5")) == ["line", "card", "card", "card", "line", "line"]

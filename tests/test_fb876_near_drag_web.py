"""FB-876（企劃者 2026-10-26 試玩新輿圖：「輿圖拖曳的時候沒辦法跨區」）：輿圖第一層、第二層（S.mapLayer "near"）拖的範圍以前夾在
「這一區的地點、走得到的地方與你的外框加 60」——別區的地點明明畫成淡墨小圖、點得到，卻拖不過去（站潁川郡 375 寬：往右拖 300 一點都不動、
往下拖只動 59.5）。改成整張圖（底圖的 world.frame）：拖得過區界、看得到隔壁，拖到底停在整張圖的邊上（照舊「圖不能完全拖出框外」）。
天下圖的範圍不變。全區（區圖）企劃者 2026-10-26 選甲：也照整張圖夾、別區畫淡墨小圖，測試在 tests/test_fb876_region_neighbours_web.py
（以前這裡有一條「全區照舊夾在這一區的取景框」，選了甲之後拿掉）。

在 node 裡跑整支 app.js（tests/webharness.py）；假地圖框、手勢照 tests/test_map_pan_web.py。沒有 node 就略過。"""
from __future__ import annotations

import pytest
from test_map_pan_web import READY, _game, run

import webharness

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]

# 整張圖（world.frame）此刻在螢幕上的四邊、露出來的那一塊（panBox 的 a）
EDGES = """
const edges = () => { const f = H.S.mapBase.world.frame; return [...toScreen(f[0], f[1]), ...toScreen(f[0] + f[2], f[1] + f[3])]; };
const open = () => H.panBox(H.curView(), VW, VH).a;
const dragBy = (dx, dy) => { down(1, 180, 300); move(1, 180 + dx / 2, 300 + dy / 2); flush(); move(1, 180 + dx, 300 + dy); flush(); up(1, 180 + dx, 300 + dy); flush(); };
"""


def test_the_first_layer_drags_past_the_region_border():
    """站潁川郡（潁川汝南的西北角），1 倍往下拖 200（看北邊的冀州）：地圖跟著手指整整走 200（修前夾在這一區的外框，只走得動 59.5），
    拖完別區的地點進了框。"""
    out = run(_game("yingchuan"), READY + EDGES + """
const inView = () => H.S.mapBase.places.filter((p) => p.region !== 'yingru').filter((p) => { const [x, y] = toScreen(p.x, p.y); return x >= 0 && x <= VW && y >= 58 && y <= VH - 54; }).map((p) => p.id);
const before = inView();
dragBy(0, 200);
return { layer: H.S.mapLayer, pan: pan(), before, after: inView() };
""", layer="near")
    assert out["layer"] == "near"
    assert out["pan"] == {"z": 1, "x": 0, "y": 200}
    assert set(out["after"]) - set(out["before"]), "拖過去之後沒有多看到別區的地點"


@pytest.mark.parametrize(("dx", "dy", "side"), [(3000, 0, 0), (-3000, 0, 2), (0, 3000, 1), (0, -3000, 3)])
def test_dragging_hard_stops_at_the_edge_of_the_whole_map(dx, dy, side):
    """放大 2 倍往一個方向拖到底：停在整張圖的那一邊（左右是地圖框、上面是那一排底下、底下是抽屜上面），不是這一區的邊上；整張不會拖出框外。"""
    out = run(_game("yingchuan"), READY + EDGES + f"""
zoomTo(2);
dragBy({dx}, {dy});
return {{ edges: edges(), open: open() }};
""", layer="near")
    e, a = out["edges"], out["open"]
    assert e[side] == pytest.approx(a[side], abs=1e-6)  # 那一邊貼齊
    assert e[0] <= a[0] + 1e-6 and e[1] <= a[1] + 1e-6 and e[2] >= a[2] - 1e-6 and e[3] >= a[3] - 1e-6  # 照樣蓋滿露出來的那一塊


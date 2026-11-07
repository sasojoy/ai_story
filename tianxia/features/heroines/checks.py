"""content/heroines.json 的檢查（content.validate 照 FEATURES 叫，關著的包照驗）。"""
from __future__ import annotations

from . import rules


def check(content, need) -> None:
    lines = content.storylines  # 線 id → StoryDef
    for cid, hd in content.heroines.items():
        where = f"heroines.json 的 {cid}"
        ch = content.characters.get(cid)
        need(ch is not None, f"{where}：人物表沒有這一位")
        if ch is not None:
            need(ch.deep_interaction and ch.talk_at is not None, f"{where}：要能深度對話、寫 talk_at")
            need(cid not in {fig.character for fig in content.figures.values()}, f"{where}：不能是大勢人物（大勢人物的所在照人物表）")
        line = lines.get(hd.line)
        need(line is not None, f"{where}：沒有 {hd.line} 這一條奇事")
        ends = {e.id for e in line.endings} if line is not None else set()
        need(set(hd.endings) <= ends, f"{where}：endings 有奇事裡沒有的結局 {sorted(set(hd.endings) - ends)}")
        need(set(hd.hidden) <= set(hd.endings), f"{where}：hidden 要是 endings 裡的結局")
        need(set(hd.stay) <= set(hd.endings), f"{where}：stay 要是 endings 裡的結局")
        need(all(loc in content.locations for loc in hd.stay.values()), f"{where}：stay 有地圖上沒有的地點")
        steps = sorted(s.step for s in hd.scenes)
        need(steps in ([], [3, 4]), f"{where}：隱線要剛好兩段（3、4），現在是 {steps}")
        if steps == [3, 4]:
            three, four = (next(s for s in hd.scenes if s.step == n) for n in (3, 4))
            need(three.affinity <= four.affinity, f"{where}：第四段的情誼不能比第三段低")
        need(set(hd.prompt) <= {3, 4}, f"{where}：prompt 只能寫第 3、4 段")
        for scene in hd.scenes:  # 固定文字也守尺度：未成年、強迫、甲級以上的字一個都不准
            for text in (scene.label, scene.text, scene.accept, scene.decline, scene.accept_label, scene.decline_label):
                bad = [w for w in rules.MINOR + rules.FORCE + rules.EXPLICIT if w in text]
                need(not bad, f"{where} 第 {scene.step} 段：有不准寫的字 {bad}")

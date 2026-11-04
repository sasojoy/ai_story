"""做 MUT：把 $QA_DIR/MUT（HEAD 的一份工作樹）改一個字，看比對有沒有牙。用法：python mkmut.py <23|24>
先 git worktree add --detach $QA_DIR/MUT <head 的 SHA>。flow() 要走到那一句才抓得到；走不到就換一句你的 flow 會走到的。
這幾句都量過，只出現一次（第 23 批是改名成 cultivation 之前量的，路徑照改名之後寫；還沒改名就自動找舊路徑）。位元組替換，換行不動。"""
import os
import sys
from pathlib import Path

MUT = Path(os.environ["QA_DIR"]).resolve() / "MUT"
TABLE = {
    "23": (("tianxia/features/cultivation/ascend.py", 'FALLBACK_PILL = "藥力化開，', 'FALLBACK_PILL = "藥力化開了，'),),
    "24": (("tianxia/features/sense/actions.py", "（在畫布上一筆畫下心中的形。）", "（在畫布上一筆畫下心中的形！）"),),
}
for rel, old, new in TABLE[sys.argv[1]]:
    f = MUT / rel
    if not f.exists():
        f = MUT / rel.replace("features/cultivation", "features/arts")
    raw = f.read_bytes()
    assert raw.count(old.encode("utf-8")) == 1, rel
    f.write_bytes(raw.replace(old.encode("utf-8"), new.encode("utf-8"), 1))
    print(rel, "mutated")

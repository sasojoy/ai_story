"""MUT＝HEAD 改兩個字（看比對有沒有牙）：擂台報名那一句「別人隨時可以來挑。」→「！」（包裡的 arena_rules.py）、
撞上頭目那一句「攔住了去路！」→「。」（包裡的 duel_actions.py）。位元組替換，CRLF 不動。"""
import os
from pathlib import Path

MUT = Path(os.environ["QA_DIR"]).resolve() / "MUT"
for rel, old, new in (("tianxia/features/bout/arena_rules.py", "別人隨時可以來挑。", "別人隨時可以來挑！"),
                      ("tianxia/features/bout/duel_actions.py", "攔住了去路！", "攔住了去路。")):
    f = MUT / rel
    raw = f.read_bytes()
    assert raw.count(old.encode("utf-8")) == 1, rel
    f.write_bytes(raw.replace(old.encode("utf-8"), new.encode("utf-8"), 1))
    print(rel, "mutated")

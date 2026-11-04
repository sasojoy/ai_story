"""單點突變：把 head 抄一份（只抄 tianxia、content、server.py、web、tests/fixtures），每一個突變改一處、跑 arts 一軌一種設定，
跟沒改的 head 比雜湊。用法：python mutants.py <head 工作樹> <暫存資料夾> <same_behavior.py>"""
import hashlib
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

head = Path(sys.argv[1]).resolve()
tmp = Path(sys.argv[2]).resolve()
script = Path(sys.argv[3]).resolve()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
copy = tmp / "mutant_tree"
if copy.exists():
    shutil.rmtree(copy)
copy.mkdir(parents=True)
for name in ("tianxia", "content", "web"):
    shutil.copytree(head / name, copy / name, ignore=shutil.ignore_patterns("__pycache__"))
shutil.copytree(head / "tests" / "fixtures", copy / "tests" / "fixtures")
for name in ("server.py", "llm_queue.py", "server_push.py", "console.py", "zhuan_html.py", "run_bots.py"):
    if (head / name).exists():
        shutil.copy2(head / name, copy / name)

# （檔, 原文, 改成, 設定）：每一個是搬進包的一處；設定挑走得到它的那一種
MUTANTS = [
    ("M1 改練換上的標記", "tianxia/features/arts/actions.py", 'm.startswith("你改練")), msgs[-1]', 'm.startswith("你改練")), msgs[0]', "week7"),
    ("M2 練成心得不足不寫紀錄", "tianxia/features/arts/actions.py", "    if not counted:  # 練不成", "    if False and not counted:  # 練不成", "week7"),
    ("M3 裝意境不設 forged", "tianxia/features/arts/actions.py", "    ctx.forged = True\n", "    ctx.forged = False\n", "week7"),
    ("M4 拆不在槽上的也寫紀錄", "tianxia/features/arts/actions.py", "    if insight_id in slots:\n", "    if True:\n", "week7"),
    ("M5 熔煉的重學指路拿掉", "tianxia/features/arts/actions.py", "msgs = ctx._log(msgs + [relearn] if relearn else msgs)", "msgs = ctx._log(msgs)", "week7"),
    ("M6 批量熔煉序章那一句", "tianxia/features/arts/actions.py", 'MELT_MANY_PROLOGUE = "這裡照師父說的，一門一門熔。"', 'MELT_MANY_PROLOGUE = "這裡照師父說的，一門一門熔！"', "none"),
    ("M7 服丹的體力不寫", "tianxia/features/arts/actions.py", '([f"體力 -{spent}"] if spent > 0 else [])', '([f"體力 -{spent}"] if spent > 99 else [])', "week7"),
    ("M8 定名不存回季", "tianxia/features/arts/actions.py", "        ctx._save_season()\n        shown", "        shown", "week7"),
    ("M9 配點那一句全隊", "tianxia/features/arts/actions.py", 'tail = f"，此刻全隊 {power:.0f} → {after:.0f}"', 'tail = f"，此刻全隊 {power:.0f} → {after:.1f}"', "week7"),
    ("M10 境界卡配完不收", "tianxia/features/arts/actions.py", "        p.milestone_due = 0  # 境界卡", "        p.milestone_due = p.milestone_due  # 境界卡", "week7"),
    ("M11 傳功拒絕也寫紀錄", "tianxia/features/arts/actions.py", "    if ctx._xinde() == xinde:  # 沒花到心得", "    if False:  # 沒花到心得", "week7"),
    ("M12 追風步舊品質不拿掉", "tianxia/features/arts/actions.py", '        del p.art_quality["zhuifeng"]', '        pass', "week7"),
    ("M13 定名通知那一句", "tianxia/features/arts/actions.py", "已由{namer}定名為", "已經由{namer}定名為", "week7"),
    ("M14 學藝的標題", "tianxia/features/arts/actions.py", 'return f"學藝・{ctx.content.skills[skill_id].name}"', 'return f"學藝：{ctx.content.skills[skill_id].name}"', "week7"),
    ("M15 契機的難度比", "tianxia/features/arts/actions.py", "return cultivation.seize(ctx.state, ctx.content, ctx.world, ratio, ctx.rng)",
     "return cultivation.seize(ctx.state, ctx.content, ctx.world, ratio * 2, ctx.rng)", "week7"),
    ("M16 持有數上限", "tianxia/features/arts/view.py", '"cap": library.cap_of(ctx.state, ctx.content),', '"cap": library.cap_of(ctx.state, ctx.content) + 1,', "week7"),
    ("M17 傳功的屬性那一句", "tianxia/features/arts/chuangong.py", '"str": "武學威力 +{pct}"', '"str": "武學威力 ＋{pct}"', "week7"),
    ("M18 服丹沒衝開下一次", "tianxia/features/arts/cultivation.py", 'FAIL_RAMP_LINE = "那一層鬆動了些：', 'FAIL_RAMP_LINE = "那一層鬆動了：', "week7"),
    ("M19 破境卡的套句", "tianxia/features/arts/ascend.py", 'FALLBACK_PILL = "藥力化開，', 'FALLBACK_PILL = "藥力化開了，', "week7"),
    ("M20 籌備中那一句", "tianxia/core/services.py", 'PREPARING_TEXT = "賽季籌備中，等待管理者開季"', 'PREPARING_TEXT = "賽季籌備中，等管理者開季"', "week7"),
]

env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"}


def run(root: Path, profile: str, tag: str) -> str:
    out = tmp / f"mut_{tag}_{profile}.txt"
    db = tmp / f"mut_{tag}_{profile}.db"
    subprocess.run([sys.executable, str(script), "run", str(root), profile, str(out), "--tmp", str(tmp), "--track", "arts", "--db", str(db)],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    for p in tmp.glob(f"mut_{tag}_{profile}*"):
        p.unlink()
    return digest


clean = {p: run(copy, p, "clean") for p in sorted({m[4] for m in MUTANTS})}
print("沒改的", {p: h[:12] for p, h in clean.items()})
for label, rel, old, new, profile in MUTANTS:
    path = copy / rel
    raw = path.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if text.count(old) != 1:
        print(label, "找不到原文（或不只一處）", text.count(old))
        continue
    path.write_bytes(text.replace(old, new).replace("\n", "\r\n").encode("utf-8"))
    try:
        got = run(copy, profile, "m")
        print(label, profile, "抓得到" if got != clean[profile] else "抓不到")
    finally:
        path.write_bytes(raw)
shutil.rmtree(copy)

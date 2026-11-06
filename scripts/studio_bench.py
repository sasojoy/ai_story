"""畫坊量測：一套形象的某幾張各畫 N 次，看第一次就過的比例與失敗理由（主機；要 ComfyUI 開著）。

為什麼要有這一支（2026-11-03 正式站 #494、#495 都在前五張就卡死）：改提示詞、改門檻、改畫法之前先有基準線，
不要憑感覺。每一次都是「第一次畫」，所以量到的是單次通過率；一張要畫幾次的期望值約是它的倒數，
上限 10 次全掛的機率是（1 − 通過率）的 10 次方。

    .venv/Scripts/python.exe -u scripts/studio_bench.py --order 494 --sheets hero_bare_dodge,hero_bare_fall --n 8 --review --out <資料夾>

- --order：訂單編號，那一套的資料夾與玩家寫的那一句照它讀（資料庫唯讀；PowerShell 5.1 傳中文參數會變亂碼）。
- --review 才叫審圖（要 ANTHROPIC_API_KEY，一次約 $0.01；機械驗沒過的不送）。
- --fix：第一次沒過就照畫坊的做法（FIX_PROMPT、上一張當第一張參考圖）再畫一次。
- --variant：prod（預設，照畫坊現在的做法：有姿勢剪影的張用剪影）；color（一律用斗笠小子的彩色原圖，2026-11-03 以前的做法）。
每一次寫一行 JSON 到 <out>/bench.jsonl，原圖與切好的那一條也存在 <out>/。最後印每一張的通過率與失敗理由分類；
`--summary <bench.jsonl>` 只印統計。

2026-11-03 量到的（#494 白衣仙女、#495 斗笠蒙面客合計，第一次就過的比例）：
  dodge：彩色原圖 6%、不給原圖 8%、原圖當起始圖（img2img 0.75）8%、灰色剪影 17%、去斗笠的灰色剪影 31%
  fall ：彩色原圖 6%、不給原圖 8%、原圖當起始圖 0%、灰色剪影 17%、去斗笠的灰色剪影 12%
  照意見重畫（--fix）跟重新畫差不多：dodge 1/15、fall 0/15。
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.features.looks import cutting, orders, studio  # noqa: E402
from tianxia.features.looks.studio_local import LocalPainter  # noqa: E402

WEB_IMG = ROOT / "web" / "img"


def job_for(sheet: str, prompt: str, portrait: Path, variant: str) -> studio.Job:
    """同 studio.jobs 給這一張的那一份（提示詞、清單、參考圖、姿勢剪影一字不差）；color 不用剪影。"""
    order = SimpleNamespace(prompt=prompt)
    pose = studio.POSE_DIR / f"{sheet}.png" if sheet in studio.POSE and variant != "color" else None
    pose = pose if pose is not None and pose.is_file() else None
    return studio.Job(kind="look", pid=0, folder="bench", slot=sheet, label=sheet, portrait=portrait, pose=pose,
                      prompt=f"{orders.gen_prompts(order)[sheet]}\n{studio.POSE_EXTRA if pose else studio.SHEET_EXTRA}",
                      checklist=studio.CHECK_SHEET.format(frames=orders.SHEETS[sheet], action=orders.ACTIONS[sheet],
                                                          gear=studio.GEAR_NONE),
                      aspect=studio.ASPECT[studio.LAYOUT[sheet]], size="2K",
                      refs=(orders.reference(WEB_IMG, sheet), portrait))


# 機械驗的問題 → 類別（照 cutting.sheet_problems 的字句）
MECH = [("空格", "幾乎是空的"), ("只剩一小塊", "只剩一小塊"), ("不只一塊", "不只一塊"), ("貼上緣", "貼到上緣"),
        ("超過地平線", "超過地平線"), ("地面線", "橫跨整格的線"), ("相鄰太像", "幾乎一樣"), ("沒有前後移動", "前後移動"),
        ("切不出來", "切不出")]
# 審圖的理由 → 類別（關鍵字粗分，給人看分佈用；原句照樣存在 jsonl）
REVIEW = [("多一個人/格數", r"兩個|多了一個|多一個|格數|只有\s*\d+\s*格|空"), ("朝向", r"面向左|朝左|背對|轉身|鏡像|向左"),
          ("不是同一個人", r"同一個|不一致|服裝|髮|顏色|衣"), ("動作不對", r"動作|姿勢|不像|奔跑|衝|倒地|閃|後仰|順序"),
          ("被切到", r"切|裁|超出|邊緣"), ("兵器/物品", r"武器|兵器|持|物品|劍|刀"), ("去背", r"去背|殘留|白|透明|灰")]


def classify(problems: list[str], table) -> list[str]:
    out = [name for name, pat in table
           if any((pat in p) if table is MECH else re.search(pat, p) for p in problems)]
    return out or ["其他"]


def main(argv: list[str]) -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", type=int, help="訂單編號：那一套的資料夾與玩家寫的那一句照它讀（資料庫唯讀）")
    ap.add_argument("--look", help="那一套的資料夾（要有 ref.png）；給了 --order 可以不寫")
    ap.add_argument("--prompt", help="玩家寫的那一句；給了 --order 可以不寫")
    ap.add_argument("--sheets", default=",".join(orders.ARENA))
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--fix", action="store_true", help="第一次沒過就照意見再畫一次（同畫坊）")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--variant", default="prod", choices=["prod", "color"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if args.order:
        import sqlite3  # noqa: PLC0415

        from tianxia import database  # noqa: PLC0415

        db = database.default_path().resolve()
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        (data,) = conn.execute("SELECT data FROM mall_purchases WHERE id = ?", (args.order,)).fetchone()
        args.prompt = args.prompt or json.loads(data)["prompt"]
        args.look = args.look or str(db.parent / "looks" / orders.look_id(args.order))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    portrait = Path(args.look) / f"{studio.PORTRAIT}.png"
    painter = LocalPainter(steps=args.steps)
    critic = None
    if args.review:
        from tianxia.features.looks.studio_api import ClaudeCritic  # noqa: PLC0415

        critic = ClaudeCritic()
    for sheet in args.sheets.split(","):
        job = job_for(sheet, args.prompt, portrait, args.variant)
        refs = [p.read_bytes() for p in job.refs if p.is_file()]
        paint_refs = [job.pose.read_bytes(), *refs[1:]] if job.pose is not None else refs  # 同 studio.work
        for i in range(args.n):
            row = attempt(painter, critic, job, refs, job.prompt, paint_refs, out, args.variant, i, 1)
            if args.fix and not (row["mech_ok"] and row["review_ok"] is not False):
                prev = (out / row["file"]).read_bytes()
                fix = row["fix"] or row.get("mech_fix") or "redraw it following the instructions"
                attempt(painter, critic, job, refs, studio.FIX_PROMPT.format(fix=fix, prompt=job.prompt), [prev, *paint_refs],
                        out, args.variant + "+fix", i, 2)
    summary(out / "bench.jsonl")
    return 0


def attempt(painter, critic, job, refs, prompt, images, out, variant, i, n) -> dict:
    """畫一次、切、驗（機械驗沒過就不送審圖），寫一行 jsonl。"""
    sheet = job.slot
    t = time.monotonic()
    raw = painter.paint(prompt, images, job.aspect, job.size)
    secs = round(time.monotonic() - t, 1)
    tag = f"{variant}_{sheet}_{int(time.time())}_{i}_{n}"
    (out / f"{tag}.png").write_bytes(raw)
    row = {"variant": variant, "sheet": sheet, "i": i, "attempt": n, "secs": secs, "file": f"{tag}.png",
           "mech_ok": False, "mech": [], "review_ok": None, "review": [], "fix": ""}
    try:
        image = studio.cut_for(job, raw, cutting)
    except studio.CutProblem as exc:
        row["mech"], row["mech_fix"] = exc.problems, exc.fix
    except (studio.CutError, ValueError) as exc:
        row["mech"] = [f"切不出來：{exc}"]
    else:
        row["mech_ok"] = True
        (out / f"{tag}.webp").write_bytes(image)
        if critic is not None:
            v = critic.review(job.checklist, image, refs)
            row.update(review_ok=v.ok, review=v.problems, fix=v.fix)
    with (out / "bench.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[{variant}] {sheet} #{i} {secs}s 機械{'過' if row['mech_ok'] else '✗ ' + '；'.join(row['mech'])}"
          + ("" if row["review_ok"] is None else f" 審圖{'過' if row['review_ok'] else '✗ ' + '；'.join(row['review'])}"),
          flush=True)
    return row


def summary(path: Path) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    groups: dict = collections.defaultdict(list)
    for r in rows:
        groups[(r["variant"], r["sheet"])].append(r)
    for (variant, sheet), rs in sorted(groups.items()):
        n = len(rs)
        mech = sum(r["mech_ok"] for r in rs)
        reviewed = [r for r in rs if r["review_ok"] is not None]
        ok = sum(bool(r["review_ok"]) for r in reviewed)
        mc = collections.Counter(c for r in rs if not r["mech_ok"] for c in classify(r["mech"], MECH))
        rc = collections.Counter(c for r in reviewed if not r["review_ok"] for c in classify(r["review"], REVIEW))
        line = f"[{variant}] {sheet}: {n} 次，機械驗過 {mech}"
        if reviewed:
            line += f"，審圖 {len(reviewed)} 次過 {ok}（單次通過率 {ok / n:.0%}）"
        print(line)
        if mc:
            print("   機械：" + "、".join(f"{k} {v}" for k, v in mc.most_common()))
        if rc:
            print("   審圖：" + "、".join(f"{k} {v}" for k, v in rc.most_common()))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--summary"]:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        summary(Path(sys.argv[2]))
    else:
        sys.exit(main(sys.argv[1:]))

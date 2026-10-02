"""好玩度量表（企劃者 2026-10-03 提的方法）：假裝自己是什麼都不知道的新玩家跑完一整季，
**看到新東西加分、看到重複過的東西扣分，重複越多次扣越多**，最後印出分數與分項。

為什麼要這個：既有的量法全是資源計數（素材 21 個、心得 167 點），那些數字完全說不出「玩起來
有沒有東西看」。而這個專案反覆踩到的坑本質上就是重複——探索 100 次撞到同幾個事件、17 爐裡
8 爐在重煉已知配方、歷練機制上不會發生所以戰鬥內容從沒出現過。單一個指標會一次抓到這三個。

實作時刻意處理了四件會讓指標量錯的事：

1. **「新」不等於「好玩」**：新事件如果所有選項都 disabled、新功法如果是下品還比身上那門弱，
   那是有新鮮感但沒有收穫（實測過改練更強的功法威力會先掉）。所以首見的加分要乘上「這次行動
   有沒有真的改變什麼」——沒有改變任何狀態的首見只拿一半分。
2. **重複分兩種**：敘事內容的重複（同一段事件文字、同一門功法）真的該扣；機制動作的重複
   （移動、歷練、練功、療傷）不扣——那是遊戲的骨幹，遭遇戰每次結果不同，玩家不會因為「打
   第二場」就無聊。不分開的話指標會把核心循環本身判成扣分來源。
3. **遞增懲罰要有上限**：一季約數百個行動，懲罰若一路線性成長，分數會被尾段支配，等於變成
   「賽季長度」的代理變數。所以第 n 次重複扣 (n-1) × STEP，但夾在 REPEAT_CAP。
4. **分項輸出，不要只看總分**：總分很容易被調參調到好看，分項才看得出是哪一塊乾掉。

### 校準（用已知答案驗指標，不是用指標去下結論）

指標本身要先能把「我們已經知道哪個版本比較無聊」排對順序，否則調出來的參數只是在迎合直覺。
這裡用**行為重現**的方式造出三個已經修掉的缺陷（而不是 checkout 舊 commit——那些版本連
煉製模組都還不存在，同一支腳本跑不起來）：

| 旗標 | 重現哪個歷史狀態 |
|---|---|
| `--no-craft --no-train` | 0716d8b 之前：沒有煉製、也沒有歷練 |
| `--no-train` | 239bdf8 之前：有煉製，但遭遇戰一季只有 3 場 |
| `--allow-recraft` | 2b05b47 之前：47% 的爐在重煉已知配方 |
| （無旗標） | 現在 |

執行：
    .venv/Scripts/python.exe scripts/fun_run.py --seeds 1 2 3
    .venv/Scripts/python.exe scripts/fun_run.py --calibrate
"""
from __future__ import annotations

import argparse
import io
import random
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # 不包的話印 ✔ 會噴 cp950

from tianxia import bot, companion_agent, craft, materials  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.world_state import WorldStateStore  # noqa: E402

DAY = 86400
HALF_HOUR = 1800
MAX_STEPS = 20000
SPEND_XINDE_EVERY = 5

# 首見的加分（有改變狀態才給全額，否則一半，見模組說明第 1 點）
NOVELTY_POINTS = {
    "事件": 3.0,
    "配方首創": 5.0,  # 全服第一個煉出這個配方：最珍貴的一種新鮮感
    "配方查表": 3.0,  # 別人首創、自己第一次拿到：仍然是新功法
    "素材": 2.0,
    "對手": 2.0,
    "地點": 1.0,
}
REPEAT_STEP = 0.5  # 第 n 次看到同一個敘事內容，扣 (n-1) × STEP
REPEAT_CAP = 3.0  # 單次扣分上限（見模組說明第 3 點）
WASTE_PENALTY = 4.0  # 花了資源（素材＋心得）卻沒換到新功法，一次扣這麼多
# 這一項是校準逼出來的：第一版只有「新鮮感」與「重複」兩項，結果「會重煉已知配方、47% 白燒」
# 那個已知缺陷跟修好的版本**分數一模一樣**——因為重煉不會產生新內容，所以在只看新鮮感的
# 指標下它是「什麼都沒發生」，而不是「虧了」。花掉的資源本來可以換到別的新東西，那個機會
# 成本才是它真正的病。


@dataclass
class FunLog:
    """一季的好玩度紀錄。"""

    novelty: Counter = field(default_factory=Counter)  # 類別 -> 首見次數
    novelty_points: float = 0.0
    hollow: Counter = field(default_factory=Counter)  # 類別 -> 首見但什麼都沒改變的次數
    repeats: Counter = field(default_factory=Counter)  # 敘事內容 id -> 看過幾次
    repeat_penalty: float = 0.0
    mechanical: int = 0  # 機制動作的重複次數（不扣分，只記錄）
    wasted: int = 0  # 花了資源卻沒換到新功法的次數
    crafts: int = 0  # 總共開了幾爐
    by_day: dict[int, list[float]] = field(default_factory=dict)  # 遊戲日 -> [加分, 扣分]
    last_novel_day: float = 0.0
    seen: dict[str, set] = field(default_factory=lambda: {k: set() for k in NOVELTY_POINTS})

    @property
    def score(self) -> float:
        return self.novelty_points - self.repeat_penalty - self.wasted * WASTE_PENALTY

    def add_novelty(self, kind: str, key, day: float, changed: bool) -> None:
        if key in self.seen[kind]:
            return
        self.seen[kind].add(key)
        points = NOVELTY_POINTS[kind] * (1.0 if changed else 0.5)
        self.novelty[kind] += 1
        if not changed:
            self.hollow[kind] += 1
        self.novelty_points += points
        self.last_novel_day = max(self.last_novel_day, day)
        self.by_day.setdefault(int(day), [0.0, 0.0])[0] += points

    def add_repeat(self, key: str, day: float) -> None:
        self.repeats[key] += 1
        times = self.repeats[key]
        penalty = min(REPEAT_CAP, (times - 1) * REPEAT_STEP)
        self.repeat_penalty += penalty
        self.by_day.setdefault(int(day), [0.0, 0.0])[1] += penalty


def snapshot(game: Game) -> tuple:
    """用來判斷「這次行動有沒有真的改變什麼」的狀態快照。"""
    p = game.state.player
    m = p.member
    return (
        tuple(sorted(p.stats.items())), tuple(sorted(game.state.world.trends.items())),
        m.neigong_id, m.neigong_level, m.wugong_id, m.wugong_level, m.level,
        sum(p.materials.values()), len(p.arts), game.state.battle_seq, len(p.team),
        round(p.stamina), round(m.neili or 0), round(m.injury),
    )


def observe_step(game: Game, log: FunLog, before: tuple, option_id: str, before_events: set) -> None:
    """一個行動做完之後，記下它給玩家看到了什麼。"""
    s, c = game.state, game.content
    day = s.world.time / DAY
    changed = snapshot(game) != before

    # 事件：engine 把看過的寫進 seen_events，所以「新出現的 id」就是這一步觸發的事件
    fired = s.player.seen_events - before_events
    for event_id in fired:
        log.add_novelty("事件", event_id, day, changed)
    if s.pending_event and not fired:  # 觸發了，但是以前看過的那一則
        log.add_repeat(f"事件:{s.pending_event}", day)

    for material_id, count in s.player.materials.items():
        if count > 0:
            log.add_novelty("素材", material_id, day, True)  # 拿到素材本身就是改變
    for art_id in [s.player.member.neigong_id, s.player.member.wugong_id, *s.player.arts]:
        if art_id:
            log.add_novelty("配方查表", art_id, day, True)
    if s.battles:
        log.add_novelty("對手", s.battles[0].opponent, day, True)
    log.add_novelty("地點", s.player.location, day, True)

    if option_id.startswith(("move:", "act:train", "act:rest")) or option_id in ("act:explore", "act:socialize"):
        if not fired:
            log.mechanical += 1


def fake_structured(self, messages, response_model, **kwargs):
    """LLM 一律假掉（照 tests/test_real_content.py 的作法），煉製因此走決定性組名那條退路。"""
    if response_model is companion_agent.CompanionTurn:
        return companion_agent.CompanionTurn(
            narrative="他微微頷首。", options=["繼續交談", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
        )
    if response_model is companion_agent.MemoryConsolidation:
        return companion_agent.MemoryConsolidation(relationship_summary="關係穩定。", new_milestones=["聊了幾句"])
    return response_model()


def play(content, seed: int, world_dir: Path, *, no_craft=False, no_train=False, allow_recraft=False) -> FunLog:
    """用隨機機器人（＝什麼都不知道的新玩家）跑完一整季，回傳好玩度紀錄。"""
    log = FunLog()
    rng = random.Random(seed)
    store = WorldStateStore(world_dir)
    game = Game.new(content, f"新玩家{seed}", random.Random(seed), store)
    # 遠端新增了「管理者開季」：新世界停在籌備中，沒開季的話選單只有一個 disabled 的
    # 「賽季籌備中」，什麼都做不了（這支腳本第一次跑就是全 0 分，原因就是這個）。
    store.open_season(0.0)
    game.state.world = store.get_season()
    first_crafts: set[str] = set()

    real_can_craft = craft.can_craft

    def lenient_can_craft(state, cnt, ids, kind, world=None):
        return real_can_craft(state, cnt, ids, kind, None)  # 重現舊行為：不檢查「這門你已經有了」

    for step in range(MAX_STEPS):
        if game.state.world.ended:
            break
        options = [o for o in game.options(odds=False) if o.enabled]
        if no_train:
            options = [o for o in options if o.id != "act:train"]
        choice = bot.pick(game, options, rng) if options else None
        if choice is not None:
            before, before_events = snapshot(game), set(game.state.player.seen_events)
            game.choose(choice)
            observe_step(game, log, before, choice, before_events)
            if step % SPEND_XINDE_EVERY == 0:
                bot.spend_xinde(game, rng)
                if not no_craft:
                    known = set(game.world.read().recipes)
                    had_arts = {game.state.player.member.neigong_id, game.state.player.member.wugong_id}
                    had_arts |= set(game.state.player.arts)
                    before_spend = (sum(game.state.player.materials.values()),
                                    game.state.player.stats.get("xinde", 0))
                    if allow_recraft:
                        with mock.patch.object(craft, "can_craft", lenient_can_craft):
                            bot.craft_and_keep_the_best(game, rng)
                    else:
                        bot.craft_and_keep_the_best(game, rng)
                    for key in set(game.world.read().recipes) - known:
                        first_crafts.add(key)
                    now_arts = {game.state.player.member.neigong_id, game.state.player.member.wugong_id}
                    now_arts |= set(game.state.player.arts)
                    after_spend = (sum(game.state.player.materials.values()),
                                   game.state.player.stats.get("xinde", 0))
                    if after_spend != before_spend:  # 真的開了一爐
                        log.crafts += 1
                        if not (now_arts - had_arts):  # 卻沒有換到任何新功法
                            log.wasted += 1
        if choice is None or step % 4 == 0:
            game.advance(HALF_HOUR)

    # 配方首創要事後補記（煉製是在 spend_xinde 那條路徑上，不經過 observe_step）
    log.novelty["配方首創"] = len(first_crafts)
    log.novelty_points += len(first_crafts) * (NOVELTY_POINTS["配方首創"] - NOVELTY_POINTS["配方查表"])
    log.days = game.state.world.time / DAY  # type: ignore[attr-defined]
    return log


def report(label: str, logs: list[FunLog], content) -> float:
    scores = [lg.score for lg in logs]
    avg = sum(scores) / len(scores)
    print(f"\n{'=' * 72}\n{label}　好玩度 {avg:+.1f}（各 seed：{'、'.join(f'{s:+.0f}' for s in scores)}）")
    totals = Counter()
    hollow = Counter()
    for lg in logs:
        totals.update(lg.novelty)
        hollow.update(lg.hollow)
    coverage = {
        "事件": len(content.events), "素材": len(content.materials),
        "地點": len(content.locations), "對手": len(content.squads),
    }
    print("  首見（平均）：", end="")
    for kind in NOVELTY_POINTS:
        n = totals[kind] / len(logs)
        cap = coverage.get(kind)
        extra = f"/{cap}" if cap else ""
        hollow_note = f"（其中 {hollow[kind] / len(logs):.0f} 個沒改變任何東西）" if hollow[kind] else ""
        print(f"{kind} {n:.0f}{extra}{hollow_note}　", end="")
    print()
    rep = sum(sum(lg.repeats.values()) for lg in logs) / len(logs)
    worst = Counter()
    for lg in logs:
        worst.update(lg.repeats)
    top = "、".join(f"{k.split(':')[-1]}×{v // len(logs)}" for k, v in worst.most_common(3))
    print(f"  敘事重複：{rep:.0f} 次（扣 {sum(lg.repeat_penalty for lg in logs) / len(logs):.0f} 分）"
          f"　機制重複：{sum(lg.mechanical for lg in logs) / len(logs):.0f} 次（不扣）")
    crafts = sum(lg.crafts for lg in logs) / len(logs)
    wasted = sum(lg.wasted for lg in logs) / len(logs)
    share = f"（{wasted / crafts:.0%}）" if crafts else ""
    print(f"  開爐 {crafts:.0f} 次，其中白燒 {wasted:.0f} 次{share}"
          f"　扣 {wasted * WASTE_PENALTY:.0f} 分")
    print(f"  最常重複：{top}")
    for lg in logs[:1]:
        days = sorted(lg.by_day)
        line = "".join("+" if lg.by_day[d][0] > lg.by_day[d][1] else "-" for d in days)
        print(f"  seed {1} 每日淨值（+ 是新鮮感贏、- 是重複贏）：{line}")
        print(f"  最後一次看到新東西：第 {lg.last_novel_day:.1f} 天"
              f"（整季 {getattr(lg, 'days', 0):.1f} 天）")
    return avg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--no-craft", action="store_true")
    ap.add_argument("--no-train", action="store_true")
    ap.add_argument("--allow-recraft", action="store_true")
    ap.add_argument("--calibrate", action="store_true", help="跑四個已知狀態，驗指標排序對不對")
    args = ap.parse_args()

    content = load_content(ROOT / "content")
    tmp = Path(tempfile.mkdtemp())
    try:
        with mock.patch.object(OllamaClient, "chat_structured", fake_structured), \
             mock.patch.object(OllamaClient, "chat_text", lambda self, m, **k: ""):
            if not args.calibrate:
                logs = [
                    play(content, s, tmp / f"w{s}", no_craft=args.no_craft, no_train=args.no_train,
                         allow_recraft=args.allow_recraft)
                    for s in args.seeds
                ]
                report("現在的版本" if not (args.no_craft or args.no_train or args.allow_recraft) else "指定旗標",
                       logs, content)
                return

            cases = [
                ("① 沒有煉製也沒有歷練（0716d8b 之前）", {"no_craft": True, "no_train": True}),
                ("② 有煉製但遭遇戰一季 3 場（239bdf8 之前）", {"no_train": True}),
                ("③ 會重煉已知配方、47% 白燒（2b05b47 之前）", {"allow_recraft": True}),
                ("④ 現在", {}),
            ]
            results = []
            for i, (label, flags) in enumerate(cases):
                logs = [play(content, s, tmp / f"c{i}s{s}", **flags) for s in args.seeds]
                results.append((label, report(label, logs, content)))
            print(f"\n{'=' * 72}\n校準結果（期望是 ① < ② < ③ < ④）")
            for label, score in results:
                print(f"  {score:+8.1f}　{label}")
            ordered = [s for _, s in results]
            print("\n排序正確：" + ("是 ✔ 指標可以信任" if ordered == sorted(ordered) else "否 ✘ 要先改指標，不要用它下結論"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

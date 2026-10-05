"""拍《天下大勢》網頁介面（server.py + web/）的手機截圖：照真實操作一步一步拍，輸出 <ID>.jpg 與 manifest.json。

每一張都是「下一步要按的東西已經框起來」的畫面（朱紅外框＋步驟編號），每段流程最後再拍一張結果。
用途是跟企劃者一頁一頁討論介面，不是測試：遊戲有亂數，每次重拍的事件、戰果、悟到的意境都可能不同。

準備（只要做一次）：
  1. 另開一個虛擬環境裝 playwright（不要裝進專案的 .venv）：
       <python 3.14>/python.exe -m venv <暫存>/capvenv
       <暫存>/capvenv/Scripts/python.exe -m pip install playwright
     不用跑 `playwright install`，直接開電腦上的 Edge（--channel msedge；也可以 --channel chrome）。
  2. 把要拍的版本匯出成一份乾淨的樹（不碰任何 worktree）：
       git -C C:/Ray/專案/天下大勢 archive <commit> | tar -x -C <暫存>/webcap-src

重拍：
  <暫存>/capvenv/Scripts/python.exe capture_screens.py --src <暫存>/webcap-src
      --python C:/Ray/專案/天下大勢/.venv/Scripts/python.exe --port 7882 --out <輸出資料夾>
      [--work <暫存>/webcap] [--commit <版本>] [--only main|season-one]

腳本會開兩次 server.py，各用一個全新的資料庫（環境變數 TIANXIA_DB），都用 scripts/set_password.py 建管理者 Rayal：
  - --port：沒設 TIANXIA_PROFILE（預設設定、beta 規則），拍 G A B J C E D F S 這幾段；
  - --port + 1：TIANXIA_PROFILE=weekend（第一季濃縮版），拍 W 那一段（週曆、本週大事、戰況、投靠、軍令、伏筆物品、收季結算）。
自己啟動、拍完就關掉（連同子行程）。管理者與玩家的密碼只寫在 --work 裡，不印在畫面上、不進輸出資料夾。
不要用 7860～7871（開發與試玩伺服器在用）。首次合成的配方要等本機模型取名，最多等 --llm-wait 秒；
本機模型連不上時很快就用退路的名字出爐，所以「爐火正旺」那一張是把煉製的回應攔住幾秒拍的（畫面就是等待中的樣子）。
輸出資料夾裡舊的截圖會先刪掉；manifest.json 裡標了 "external": true 的流程（不是這支腳本拍的）保留不動。
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RESERVED_PORTS = range(7860, 7872)
ADMIN_ACCOUNT = "webcap_admin"
ADMIN_NAME = "Rayal"
PLAYER_NAME = "試劍客"
WILDS = "yingchuan_wilds"  # 潁川郊野：離起點最近、有敵人的地點
JOIN_AT = "changshe"  # 第一季：官軍的投靠地點之一（離起點最近）
JOIN_FACTION = "guan"
CLUE_AT = WILDS  # 官軍才碰得到的伏筆事件「河灘蘆葦」（給葦束）在潁川郊野與潁水河畔

# 框起「下一步要按的東西」：朱紅外框＋步驟編號。position:fixed，所以先把元素捲進畫面（避開頂上狀態列與底部分頁列）。
# 輿圖框裡的東西不能 scrollIntoView：地圖框是 overflow:hidden、靠 transform 平移，捲了框本身會把地圖錯開，只捲整頁。
MARK_JS = """(el, label) => {
  document.getElementById('__tap_mark')?.remove();
  const inMap = el.closest('#map');
  const fixed = getComputedStyle(el).position === 'fixed' || el.closest('.tabs, .sheet, .top, .sticky-act, .ask-layer');
  const bottomLimit = innerHeight - 84, topLimit = 150;
  let r = el.getBoundingClientRect();
  if (inMap) {
    const m = inMap.getBoundingClientRect();
    if (m.top < 120 || m.bottom > innerHeight - 84) window.scrollBy(0, m.top - 130);
  } else if (fixed || r.top < topLimit || r.bottom > bottomLimit) {
    el.scrollIntoView({block: 'center', inline: 'nearest'});  // 已經整個露在畫面上就不捲，畫面照原樣
  }
  r = el.getBoundingClientRect();
  if (!fixed && !inMap) {
    if (r.bottom > bottomLimit) window.scrollBy(0, r.bottom - bottomLimit);
    else if (r.top < topLimit && r.height < innerHeight - 250) window.scrollBy(0, r.top - topLimit);
    r = el.getBoundingClientRect();
  }
  const small = Math.min(r.width, r.height) < 30;  // 地圖上的小圓點：框大一點，編號放左上，免得蓋住右邊的地名
  const pad = small ? Math.max(6, (34 - Math.min(r.width, r.height)) / 2) : 4;
  const box = document.createElement('div');
  box.id = '__tap_mark';
  box.style.cssText = `position:fixed;left:${r.left - pad}px;top:${r.top - pad}px;width:${r.width + 2 * pad}px;height:${r.height + 2 * pad}px;`
    + 'border:3px solid #e8553a;border-radius:12px;z-index:2147483647;pointer-events:none;box-sizing:border-box;'
    + 'box-shadow:0 0 0 3px rgba(232,85,58,0.22);';
  const badge = document.createElement('div');
  badge.textContent = label;
  const badgeTop = small ? 'top:-30px' : (r.top - pad < 14 ? 'bottom:-14px' : 'top:-14px');
  const badgeSide = small ? 'left:-34px' : (r.right + 12 > innerWidth ? 'left:-10px' : 'right:-10px');
  badge.style.cssText = `position:absolute;${badgeTop};${badgeSide};min-width:26px;height:24px;padding:0 7px;border-radius:12px;`
    + 'background:#e8553a;color:#fff;font:700 13px/24px -apple-system,"Segoe UI",sans-serif;text-align:center;'
    + 'box-shadow:0 1px 4px rgba(0,0,0,0.35);';
  box.appendChild(badge);
  document.body.appendChild(box);
}"""
UNMARK_JS = "() => document.getElementById('__tap_mark')?.remove()"


# ── 伺服器 ──────────────────────────────────────────


def port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def kill_tree(proc: subprocess.Popen) -> None:
    """Windows 上 venv 的 python.exe 會再開一個真正的直譯器當子行程：只關父行程的話，port 會被子行程佔著。"""
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            proc.kill()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        pass


def wait_until_up(base: str, proc: subprocess.Popen, seconds: int = 180) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("server.py 啟動失敗，看 --work 裡的 server*.log")
        try:
            urllib.request.urlopen(base + "/", timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("server.py 一直沒有回應")


def make_admin(python: str, src: Path, db: Path, local: Path, env: dict) -> str:
    """用專案自己的 scripts/set_password.py 建管理者帳號與角色；密碼從它寫的檔案讀回來，不印出來。"""
    r = subprocess.run(
        [python, "scripts/set_password.py", ADMIN_ACCOUNT, "--character", ADMIN_NAME, "--db", str(db), "--local-dir", str(local)],
        cwd=src, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError(f"set_password.py 失敗：{r.stdout}{r.stderr[-800:]}")
    return (local / f"{ADMIN_ACCOUNT}_password.txt").read_text(encoding="utf-8").strip()


class Server:
    """一次 server.py：全新的資料庫、管理者、玩家帳號。用 with 包起來，離開就關掉（連同子行程）。"""

    def __init__(self, args, work: Path, port: int, profile: str | None, tag: str):
        self.args, self.work, self.port, self.profile, self.tag = args, work, port, profile, tag
        self.base = f"http://127.0.0.1:{port}"

    def __enter__(self):
        self.work.mkdir(parents=True, exist_ok=True)
        db = self.work / "tianxia.db"
        for f in (db, Path(f"{db}-wal"), Path(f"{db}-shm")):
            if f.exists():
                f.unlink()
        env = dict(os.environ, TIANXIA_DB=str(db), PYTHONIOENCODING="utf-8")
        env.pop("TIANXIA_PROFILE", None)
        if self.profile:
            env["TIANXIA_PROFILE"] = self.profile
        src = Path(self.args.src).resolve()
        print(f"[{self.tag}] 建立管理者……")
        self.admin_pw = make_admin(self.args.python, src, db, self.work / "local", env)
        self.player_login = "jianke_" + secrets.token_hex(3)
        self.player_pw = secrets.token_urlsafe(9)
        (self.work / "player_credentials.txt").write_text(f"{self.player_login}\n{self.player_pw}\n", encoding="utf-8")
        self.log = open(self.work / "server.log", "w", encoding="utf-8")
        print(f"[{self.tag}] 啟動 server.py（{self.base}，設定：{self.profile or '預設'}）……")
        self.proc = subprocess.Popen([self.args.python, "-u", "server.py", "--port", str(self.port)], cwd=src, env=env,
                                     stdout=self.log, stderr=subprocess.STDOUT)
        try:
            wait_until_up(self.base, self.proc)
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *exc):
        kill_tree(self.proc)
        self.log.close()
        if port_busy(self.port):
            print(f"警告：port {self.port} 還有人在聽，請手動關掉。")


# ── 截圖與紀錄 ──────────────────────────────────────────


class Shooter:
    def __init__(self, out: Path, quality: int = 80):
        self.out = out
        self.quality = quality
        self.flows: list[dict] = []
        self.missed: list[str] = []
        self.page = None
        self.cur: dict | None = None
        self.n = 0

    def flow(self, fid: str, title: str, **extra) -> None:
        self.cur = {"id": fid, "title": title, **extra, "steps": []}
        self.flows.append(self.cur)
        self.n = 0

    def resume(self, fid: str) -> None:
        """接著前面那一段拍（例如 B 的遊歷、步行是在輿圖、煉製之後才拍的）。"""
        self.cur = next(f for f in self.flows if f["id"] == fid)
        self.n = len(self.cur["steps"])

    def shot(self, screen: str, action: str = "", target=None, note: str = "") -> str:
        """拍目前的畫面。target 是下一步要按的元素（Locator），會先框起來、拍完再拿掉。"""
        self.n += 1
        sid = f"{self.cur['id']}{self.n}"
        if target is not None:
            target.first.evaluate(MARK_JS, sid)
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=str(self.out / f"{sid}.jpg"), type="jpeg", quality=self.quality)
        if target is not None:
            self.page.evaluate(UNMARK_JS)
        step = {"id": sid, "file": f"{sid}.jpg", "screen": screen, "action": action}
        if note:
            step["note"] = note
        self.cur["steps"].append(step)
        print(f"  {sid}  {screen}" + (f" → {action}" if action else ""))
        return sid

    def miss(self, what: str) -> None:
        self.missed.append(what)
        print(f"  （沒拍：{what}）")


def api_path(path: str):
    return lambda r: urlparse(r.url).path == path


def tap(page, loc, wait_path: str | None = None, timeout: float = 60_000, settle: int = 800) -> None:
    """按下去，等那支 API 回來，再等畫面動畫跑完。"""
    if wait_path:
        with page.expect_response(api_path(wait_path), timeout=timeout):
            loc.first.click()
    else:
        loc.first.click()
    page.wait_for_timeout(settle)


def to_top(page) -> None:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)


def scroll_to(page, loc, top: int = 150) -> None:
    """把元素捲到狀態列下面（不框起來）。"""
    loc.first.evaluate(f"(el) => window.scrollBy(0, el.getBoundingClientRect().top - {top})")
    page.wait_for_timeout(350)


def api(page, path: str, body: dict | None = None) -> dict:
    """用這一頁的登入狀態直接打 API（不拍、不畫：湊意境、跑伏筆、快轉用）。之後要 reload 畫面才會跟上。"""
    return page.evaluate(
        """([p, b]) => fetch(p, b === null ? {credentials: 'same-origin'} : {method: 'POST', credentials: 'same-origin',
             headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b)}).then(r => r.json())""",
        [path, body],
    )


def reload(page) -> None:
    page.reload()
    page.wait_for_selector(".tabs")
    page.wait_for_timeout(800)


def option(page, prefix: str):
    """江湖頁上按得下去的選項：行動列的水墨按鈕、移動卡裡的前往、事件選項、「此地還能做」摺疊裡的，都是 data-act=choose。"""
    return page.locator(f'#page button[data-act="choose"][data-id^="{prefix}"]:not([disabled])')


def has(loc) -> bool:
    return loc.count() > 0


def pick_choice(page):
    """事件選項裡挑一個不用動手的（看熱鬧、離開之類）；都要動手就挑最後一個。隨口應對（choice:free）不挑。"""
    choices = page.locator('#page .options button[data-act="choose"][data-id^="choice:"]:not([disabled]):not([data-id="choice:free"])')
    n = choices.count()
    if n == 0:
        return None
    labels = [choices.nth(i).inner_text() for i in range(n)]
    for i in reversed(range(n)):
        if not re.search(r"出手|戰|打|殺|攻|闖|對手", labels[i]):
            return choices.nth(i)
    return choices.nth(n - 1)


def idle(page) -> bool:
    """平常閒著（行動列）或在路上：沒有事件卡著。"""
    return has(page.locator('#page .act-bar')) or has(option(page, "move:")) or has(option(page, "act:stand"))


def clear_events(page, limit: int = 5) -> None:
    """有事件、對話卡著（只剩一排選項）就隨手選掉，不拍。"""
    for _ in range(limit):
        if idle(page):
            return
        c = pick_choice(page)
        if c is None:
            back = page.locator('#page .options button[data-act="choose"]:not([disabled])')
            if not has(back):
                return
            c = back.last
        tap(page, c, "/api/choose")


def label_of(loc) -> str:
    return " ".join(loc.first.inner_text().split())


def login_ui(page, base: str, login: str, password: str) -> None:
    page.goto(base + "/")
    page.wait_for_selector("#gate-form")
    page.fill('#gate-form input[name="login"]', login)
    page.fill('#gate-form input[name="password"]', password)
    with page.expect_response(api_path("/api/login")):
        page.locator('#gate-form button[type="submit"]').click()
    page.wait_for_selector(".tabs")
    page.wait_for_timeout(600)


def register_ui(page, base: str, login: str, password: str, name: str) -> None:
    page.goto(base + "/")
    page.wait_for_selector("#gate-form")
    page.locator('.gate .seg button[data-mode="register"]').click()
    page.fill('#gate-form input[name="login"]', login)
    page.fill('#gate-form input[name="password"]', password)
    page.fill('#gate-form input[name="again"]', password)
    with page.expect_response(api_path("/api/register")):
        page.locator('#gate-form button[type="submit"]').click()
    page.wait_for_selector("#create-form")
    page.fill('#create-form input[name="name"]', name)
    with page.expect_response(api_path("/api/character")):
        page.locator('#create-form button[type="submit"]').click()
    page.wait_for_selector(".tabs")
    page.wait_for_timeout(800)


def open_sheet(page) -> None:
    btn = page.locator('button[data-act="sheet"]')
    if page.evaluate("() => !!document.querySelector('.sheet')"):
        return
    btn.click()
    page.wait_for_timeout(700)


def admin_op(page, op: str, sh: Shooter | None = None, shots: tuple[str, str] | None = None, **extra) -> None:
    """管理者抽屜裡的一個動作：打開抽屜 → 按 → 確認框按確定。shots 給了就在按之前、確認之前各拍一張。"""
    open_sheet(page)
    btn = page.locator(f'.sheet button[data-act="admin"][data-op="{op}"]' + "".join(f'[data-{k}="{v}"]' for k, v in extra.items()))
    if sh and shots:
        sh.shot(shots[0], f"按「{label_of(btn)}」", btn)
    btn.first.click()
    page.wait_for_timeout(500)
    yes = page.locator('.ask button[data-act="ask-yes"]')
    if sh and shots:
        sh.shot(shots[1], f"按「{label_of(yes)}」", yes)
    with page.expect_response(api_path(f"/api/do/{op}"), timeout=120_000):
        yes.click()
    page.wait_for_timeout(900)


# ── 各段流程（預設設定）──────────────────────────────────────────


def flow_admin(sh: Shooter, browser, srv: Server, ctx_opts: dict) -> None:
    sh.flow("G", "管理者開季")
    ctx = browser.new_context(**ctx_opts)
    page = sh.page = ctx.new_page()
    page.goto(srv.base + "/")
    page.wait_for_selector("#gate-form")
    page.wait_for_timeout(400)
    page.fill('#gate-form input[name="login"]', ADMIN_ACCOUNT)
    page.fill('#gate-form input[name="password"]', srv.admin_pw)
    page.locator('#gate-form input[name="password"]').blur()
    sh.shot("登入頁，管理者的帳號密碼已填好（密碼顯示成圓點）", "按「登入」", page.locator('#gate-form button[type="submit"]'))
    tap(page, page.locator('#gate-form button[type="submit"]'), "/api/login")
    page.wait_for_selector(".tabs")
    to_top(page)
    sh.shot("管理者進到江湖頁：賽季還在籌備中", "按右上角的 ⚙", page.locator('button[data-act="sheet"]'))
    with page.expect_response(api_path("/api/admin")):
        page.locator('button[data-act="sheet"]').click()
    page.wait_for_timeout(700)
    admin_op(page, "open_season", sh, ("設定抽屜：一般設定下面多一塊「管理者工具」", "確認框：先說清楚開季會怎樣，再問一次"))
    to_top(page)
    sh.shot("確定開季之後：抽屜自己關掉、回到江湖頁，底下跳出一句提示")
    page.wait_for_timeout(3500)  # 等提示消失
    sh.shot("管理者的江湖頁：賽季開始，行動列都亮了")
    ctx.close()


def flow_first_visit(sh: Shooter, browser, srv: Server, ctx_opts: dict):
    sh.flow("A", "第一次進來")
    ctx = browser.new_context(**ctx_opts)
    page = sh.page = ctx.new_page()
    page.goto(srv.base + "/")
    page.wait_for_selector("#gate-form")
    page.wait_for_timeout(400)
    sh.shot("登入頁（預設在「登入」）", "按「註冊」", page.locator('.gate .seg button[data-mode="register"]'))
    tap(page, page.locator('.gate .seg button[data-mode="register"]'), settle=300)
    page.fill('#gate-form input[name="login"]', srv.player_login)
    page.fill('#gate-form input[name="password"]', srv.player_pw)
    page.fill('#gate-form input[name="again"]', srv.player_pw)
    page.locator('#gate-form input[name="again"]').blur()
    sh.shot("註冊表單已填好（帳號、密碼、再輸入一次）", "按「註冊」", page.locator('#gate-form button[type="submit"]'))
    tap(page, page.locator('#gate-form button[type="submit"]'), "/api/register")
    page.wait_for_selector("#create-form")
    page.fill('#create-form input[name="name"]', PLAYER_NAME)
    page.locator('#create-form input[name="name"]').blur()
    sh.shot(f"取名號頁，已輸入「{PLAYER_NAME}」", "按「建立角色」", page.locator('#create-form button[type="submit"]'))
    tap(page, page.locator('#create-form button[type="submit"]'), "/api/character")
    page.wait_for_selector(".tabs")
    page.wait_for_timeout(600)
    to_top(page)
    more = page.locator('#page .now-more')
    if has(more) and more.first.is_visible():
        sh.shot("進入江湖的第一個畫面：主線與目標（收著）、「剛剛」收著開場故事、場景、一排五顆行動、小地圖，一屏看得完",
                "點「展開全文」", more)
        tap(page, more, settle=500)
        to_top(page)
        sh.shot("開場故事展開：最後一句是老說書人的第一步引導")
    else:
        sh.shot("進入江湖的第一個畫面：「剛剛」、場景與一排五顆行動")
    if has(more):
        to_top(page)
        m = page.locator('#page .now-more')
        if has(m) and "收起" in m.first.inner_text():
            m.first.click()  # 收回，後面的畫面照平常的樣子
            page.wait_for_timeout(300)
    return ctx, page


def flow_turn_start(sh: Shooter, page) -> None:
    sh.flow("B", "江湖的一回合")
    to_top(page)
    explore = option(page, "act:explore")
    sh.shot("江湖頁，準備探索（行動列：探索、遊歷、打坐、交友、移動，每顆底下寫消耗）", "按「探索」", explore)
    tap(page, explore, "/api/choose")
    to_top(page)
    choice = pick_choice(page)
    if choice is not None:
        label = re.sub(r"^\d+\s*", "", label_of(choice))
        sh.shot("探索的結果：「剛剛」寫這次遇上了什麼，場景換成事件，行動列換成事件的選項", f"按「{label}」", choice)
        tap(page, choice, "/api/choose")
        clear_events(page)
        to_top(page)
    else:
        sh.miss("探索遇上的事件（這一次探索沒有撞到事件）")
    rest = option(page, "act:rest")
    if has(rest):
        sh.shot("事件處理完，行動列回來了", "按「打坐」", rest)
        tap(page, rest, "/api/choose")
        to_top(page)
        stand = option(page, "act:stand")
        if has(stand):
            sh.shot("打坐中：狀態列寫「🧘 打坐中」，選項只剩「起身」", "按「起身」", stand)
            tap(page, stand, "/api/choose")
    else:
        sh.miss("打坐（這一回合沒有出現打坐）")


def flow_socialize(sh: Shooter, page) -> None:
    sh.flow("J", "交友")
    clear_events(page)
    to_top(page)
    social = option(page, "act:socialize")
    if not has(social):
        social = option(page, "act:call")
    if not has(social):
        sh.miss("交友（這裡沒有交友選項）")
        return
    sh.shot("起身之後回到江湖頁", "按「交友」", social)
    tap(page, social, "/api/choose", timeout=180_000)
    to_top(page)
    talk = has(page.locator('#page button[data-id^="talk:"]')) or has(page.locator('#page button[data-id^="call:"]'))
    if talk:
        sh.shot("交友找上這裡的人物說話（對話要本機模型生成）", note="這次沒有開本機模型")
    else:
        sh.shot("交友的結果：這次在城裡遇上一則交友事件（不是人物對話）",
                note="這一則是手寫的交友事件；找龍頭人物深談要本機模型，這次沒有開，沒拍到")
        sh.missed.append("交友找上龍頭人物的 AI 對話：要開著本機模型才拍得到，這次交友遇上的是手寫的交友事件（J2）")
    clear_events(page)


def flow_practice(sh: Shooter, page) -> None:
    sh.flow("C", "修練")
    clear_events(page)
    to_top(page)
    tab = page.locator('.tabs button[data-tab="practice"]')
    sh.shot("江湖頁", "按底下的「修練」分頁", tab)
    tap(page, tab, "/api/menxia")
    to_top(page)
    practice = page.locator('button[data-op="practice"]:not([disabled])')
    sh.shot("修練頁剛打開（武學／內功切換、「練成」鈕上寫著下一成要的心得、療傷、身上的功法）",
            "按「練成武學」", practice if has(practice) else None)
    tap(page, practice, "/api/menxia/practice")
    for _ in range(14):  # 心得付得起就連按下去，中間不拍（開局只有一點心得，練不到第十成）
        view = api(page, "/api/menxia")
        card = next((c for c in view["slot_cards"] if c["kind"] == "武學"), None)
        if card is None or card["price"] is None or card["price"] > view["xinde"]:
            break
        btn = page.locator('button[data-op="practice"]:not([disabled])')
        if not has(btn):
            break
        tap(page, btn, "/api/menxia/practice", settle=400)
    to_top(page)
    sh.shot("連按「練成武學」到心得花完之後的修練頁（心得少了，功法卡上的圓點多亮幾顆）", "往下捲到「武學」清單")
    arts = page.locator('#page button.art')
    if has(arts):
        scroll_to(page, arts, 150)
        sh.shot("武學清單：每門一列（身上的前面標◆），寫著品質、屬性、第幾成", "點開第一門", arts)
        tap(page, arts, settle=500)
        sh.shot("點開一門武學：功法卡、「修練」「改練這一門」「熔煉」三個按鈕與各自的說明（要勾「服下破境丹」得先撿到丹、而且下一步是衝絕學）")
    else:
        sh.miss("武學清單（身上沒有武學）")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(400)
    sh.shot("修練頁下半：閉關、悟得的意境（可以化成心得）、門下的「本人」角色卡")


def flow_map(sh: Shooter, page) -> bool:
    sh.flow("E", "輿圖")
    to_top(page)
    tab = page.locator('.tabs button[data-tab="map"]')
    sh.shot("修練頁", "按底下的「輿圖」分頁", tab)
    with page.expect_response(api_path("/api/map")):
        tab.click()
    page.wait_for_timeout(1200)
    to_top(page)
    enemies = page.locator('.seg button[data-layer="enemies"]')
    sh.shot("輿圖剛打開（局勢圖層，設色山水，以所在地為中心、原尺寸；可拖移、雙指縮放，右上角有回到所在地、放大、縮小）",
            "按「敵情」圖層", enemies)
    tap(page, enemies, "/api/map", settle=1000)
    node = page.locator(f'#map g[data-loc="{WILDS}"] > circle[fill-opacity="0"]')
    if not has(node):
        sh.miss("輿圖上點地點（地圖上找不到潁川郊野）")
        return False
    sh.shot("敵情圖層", "在地圖上點「潁川郊野」", node)
    box = node.first.bounding_box()
    with page.expect_response(api_path("/api/map")):
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(1000)
    dash = page.locator('.travel-row button[data-mode="dash"]:not([disabled])')
    if not has(dash):
        to_top(page)
        sh.shot("潁川郊野的地點詳情（沒辦法疾行）", note="疾行按鈕是灰的")
        sh.miss("疾行（按鈕是灰的）")
        return False
    detail = page.locator("#page .msg + .card")
    if has(detail):
        scroll_to(page, detail, 140)
    sh.shot("選了潁川郊野：地點詳情，底下黏著步行／趕路／疾行三個按鈕", "按「疾行」（立刻抵達、自動跳回江湖頁，接 B 流程的遊歷）", dash)
    tap(page, dash, "/api/travel")
    to_top(page)
    return True


def flow_fight(sh: Shooter, page) -> None:
    """接在 B 後面：到了有敵人的地點，遊歷一場。"""
    sh.resume("B")
    clear_events(page)
    to_top(page)
    train = option(page, "act:train")
    if not has(train):
        sh.miss("遊歷（這裡沒有對手）")
        return
    full = next((o["label"] for o in api(page, "/api/main")["options"] if o["id"] == "act:train"), "")
    sh.shot("從輿圖疾行到潁川郊野，自動跳回江湖頁；「遊歷」亮了，底下寫「體力 10」", "按「遊歷」", train,
            note=f"選單上這一顆的完整說明是「{full}」，行動列只露出體力，勝算沒有顯示在畫面上" if "・" in full else "")
    tap(page, train, "/api/choose")
    to_top(page)
    if has(page.locator(".battle-card")) and pick_choice(page) is not None:
        sh.shot("遭遇戰的戰鬥卡片（放在「剛剛」的位置），下面接著打完之後遇上的事件與它的選項")
    elif has(page.locator(".battle-card")):
        sh.shot("遭遇戰的戰鬥卡片（放在「剛剛」的位置），下面接著場景與行動列")
    else:
        sh.shot("遊歷的結果")


def gather_insights(page, want: int = 1, budget: int = 12) -> int:
    """悟到 want 個意境（不拍）：探索最容易有所領悟，探索不了就遊歷。回傳手上意境數。"""
    for _ in range(budget):
        held = len(api(page, "/api/menxia")["insights"])
        if held >= want:
            return held
        clear_events(page)
        act = option(page, "act:explore")
        if not has(act):
            act = option(page, "act:train")
        if not has(act):
            return held
        tap(page, act, "/api/choose", settle=400)
        clear_events(page)
    return len(api(page, "/api/menxia")["insights"])


def flow_craft(sh: Shooter, page, llm_wait: int) -> None:
    sh.flow("D", "煉製")
    held = gather_insights(page)
    clear_events(page)
    to_top(page)
    tab = page.locator('.tabs button[data-tab="craft"]')
    sh.shot("江湖頁（先探索、遊歷悟到一個意境）", "按底下的「煉製」分頁", tab)
    tap(page, tab, "/api/menxia", settle=1200)
    to_top(page)
    arts = page.locator('.chips button.chip[data-type="art"]:not([disabled])')
    if held < 1 or not has(arts):
        sh.shot("煉製頁（還沒悟到意境，開爐是灰的）")
        sh.miss(f"開爐（意境只有 {held} 個）")
        return
    sh.shot("煉製頁：上面是太極火爐（左右兩格放一門武學與一個意境），底下是成本說明、武學與意境的清單、背包",
            "點一門武學放進爐裡", arts)
    tap(page, arts, "/api/forge_line", settle=600)
    to_top(page)
    ins = page.locator('.chips button.chip[data-type="ins"]:not([disabled])')
    sh.shot("放進武學之後：爐子左邊那一格填上了，那門武學在清單上變灰", "再點一個意境", ins)
    tap(page, ins, "/api/forge_line", settle=600)
    to_top(page)
    forge = page.locator("#forge")
    sh.shot("兩格都放好了：火舌竄高、太極轉快，「開爐」亮起來（成本說明寫著合成要的心得；點爐身也能開爐）", "按「開爐」", forge)
    # 本機模型連不上時退路的名字一下就出爐：把回應攔住幾秒，拍等待中的畫面（首次發現的配方實際要等模型取名）
    def hold(route):
        time.sleep(4)
        route.continue_()

    page.route("**/api/menxia/forge", hold)
    started = time.time()
    try:
        with page.expect_response(api_path("/api/menxia/forge"), timeout=llm_wait * 1000 + 10_000):
            forge.click()
            page.wait_for_timeout(1500)
            if page.locator("#forge.forging").count():
                to_top(page)
                sh.shot("爐火正旺：等結果的時候整座爐子晃動，按鈕寫「爐火正旺…」，最上面說首次合成要等取名",
                        note="這一張是把合成的回應攔住幾秒拍的：本機模型沒開時，退路的名字一下就出爐，平常看不到這個畫面這麼久")
    except PWTimeout:
        sh.miss(f"合成結果（等了 {llm_wait} 秒，本機模型還沒取好名字）")
        page.unroute("**/api/menxia/forge")
        return
    page.unroute("**/api/menxia/forge")
    waited = round(time.time() - started)
    page.wait_for_timeout(1000)
    to_top(page)
    sh.shot("合成的結果寫在最上面（新武學從下品練起），爐子空了",
            note=f"本機模型沒開，用的是退路的名字；連同攔住的 4 秒，從按下到出爐約 {waited} 秒")


def flow_news(sh: Shooter, page) -> None:
    sh.flow("F", "見聞")
    to_top(page)
    tab = page.locator('.tabs button[data-tab="news"]')
    sh.shot("煉製頁（見聞分頁上有紅點：有新戰報）", "按底下的「見聞」分頁", tab)
    tap(page, tab, "/api/reports")
    to_top(page)
    report = page.locator('.list button[data-act="report"]')
    if has(report):
        sh.shot("見聞・戰報清單", "點第一場戰報", report)
        tap(page, report, "/api/reports")
        to_top(page)
        sh.shot("一場戰報的詳細內容", "按「大勢」", page.locator('.seg button[data-news="trends"]'))
    else:
        sh.shot("見聞・戰報（還沒有戰報）", "按「大勢」", page.locator('.seg button[data-news="trends"]'))
    tap(page, page.locator('.seg button[data-news="trends"]'), settle=400)
    sh.shot("見聞・大勢", "按「傳聞」", page.locator('.seg button[data-news="rumors"]'))
    tap(page, page.locator('.seg button[data-news="rumors"]'), settle=400)
    sh.shot("見聞・傳聞", "按「江湖史」", page.locator('.seg button[data-news="chronicle"]'))
    tap(page, page.locator('.seg button[data-news="chronicle"]'), settle=400)
    sh.shot("見聞・江湖史", "按「紀錄」", page.locator('.seg button[data-news="journal"]'))
    tap(page, page.locator('.seg button[data-news="journal"]'), settle=400)
    sh.shot("見聞・紀錄（江湖紀錄）")


def flow_settings(sh: Shooter, page) -> None:
    sh.flow("S", "狀態列與設定（一般玩家）")
    tab = page.locator('.tabs button[data-tab="jianghu"]')
    tap(page, tab, settle=600)
    clear_events(page)
    to_top(page)
    who = page.locator(".who")
    sh.shot("江湖頁頂上的狀態列（名號旁有 ▾）", "點名號那一塊（展開更多數值）", who)
    tap(page, who, settle=400)
    sh.shot("狀態列展開（▾ 變成 ▴）：名望、善名、惡名與四項屬性", "按右上角的 ⚙", page.locator('button[data-act="sheet"]'))
    tap(page, page.locator('button[data-act="sheet"]'), settle=700)
    sh.shot("一般玩家的設定抽屜：匿名、略過引導、改密碼、登出")
    tap(page, page.locator('.sheet .btn[data-act="sheet-close"]'), settle=400)
    tap(page, page.locator(".who"), settle=300)  # 收回狀態列


def flow_walk(sh: Shooter, page) -> None:
    """最後才走路：步行要真的等幾分鐘，路上只能做路上的事。"""
    sh.resume("B")
    clear_events(page)
    to_top(page)
    move = page.locator('#page .act-ink[data-key="move"]:not([disabled])')
    if not has(move):
        sh.miss("步行（沒有可以走的路）")
        return
    sh.shot("江湖頁的行動列，最右邊是「移動」（底下寫有幾條路）", "按「移動」", move)
    tap(page, move, settle=900)
    go = option(page, "move:")
    if not has(go):
        sh.miss("步行（展開之後沒有可以走的路）")
        return
    sh.shot("移動展開：上面切換步行／趕路／疾行，下面每條路寫著時間與體力", f"按「{label_of(go).lstrip('→ ')}」", go)
    tap(page, go, "/api/choose")
    to_top(page)
    sh.shot("在路上：狀態列多一行「🐎 往…，還要約 N 分鐘」，場景換成「在路上」，行動列換成路上的選項", "往下捲")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(400)
    sh.shot("在路上往下捲：路上能做的事（折返、邊走邊想、沿途打聽…），最下面三個捷徑（輿圖、修練、煉製）")


# ── 第一季（TIANXIA_PROFILE=weekend）──────────────────────────────────────────


def grind_clue(page, apage, tries: int = 45) -> list[dict]:
    """（不拍）投靠官軍之後到潁川郊野一直探索，碰上「河灘蘆葦」就割一捆，拿到伏筆物品為止。體力不夠就請管理者快轉一小時。"""
    api(page, "/api/travel", {"place": CLUE_AT, "mode": "dash", "layer": "situation"})
    for _ in range(tries):
        held = api(page, "/api/menxia")["clue_items"]
        if held:
            return held
        m = api(page, "/api/main")
        opts = {o["id"]: o for o in m["options"] if o["enabled"]}
        choices = [i for i in opts if i.startswith(("choice:", "talk:", "call:")) and i != "choice:free"]
        if choices:
            pick = choices[0] if "蘆葦" in m["scene"] else choices[-1]
            api(page, "/api/choose", {"id": pick})
            continue
        if "act:stand" in opts:
            api(page, "/api/choose", {"id": "act:stand"})
            continue
        if m["status"]["stamina"] < 10:
            api(apage, "/api/do/fast_forward", {"hours": 1})
            continue
        if "act:explore" not in opts:
            break
        api(page, "/api/choose", {"id": "act:explore"})
    return api(page, "/api/menxia")["clue_items"]


def flow_season_one(sh: Shooter, browser, srv: Server, ctx_opts: dict) -> None:
    sh.flow("W", "第一季濃縮版（週末測試的設定）", profile="weekend")
    # 管理者開季（G 已經拍過，這裡不拍）
    actx = browser.new_context(**ctx_opts)
    apage = actx.new_page()
    login_ui(apage, srv.base, ADMIN_ACCOUNT, srv.admin_pw)
    admin_op(apage, "open_season")
    # 新玩家（A 已經拍過註冊，這裡不拍）
    ctx = browser.new_context(**ctx_opts)
    page = sh.page = ctx.new_page()
    register_ui(page, srv.base, srv.player_login, srv.player_pw, PLAYER_NAME)
    to_top(page)
    who = page.locator(".who")
    board = page.locator("#page details.bulletin > summary")
    if has(board):
        sh.shot("第一季的江湖頁：狀態列寫「第 1 週・週一 00:00」與「下一件：朝廷出兵，約 N 小時後」，最上面是收成一行的「本週江湖大事」，"
                "行動列下面是三條戰況", "點「本週江湖大事」展開", board)
        tap(page, board, settle=600)
        to_top(page)
        sh.shot("本週江湖大事展開：這一週已經發生的大事全文", "點名號（展開狀態列）", who)
        tap(page, board, settle=300)  # 收回去，後面的畫面照平常的樣子
    else:
        sh.shot("第一季的江湖頁：狀態列寫週次與下一件大事的倒數", "點名號（展開狀態列）", who)
        sh.miss("本週江湖大事卡（這一週還沒有大事）")
    tap(page, who, settle=500)
    to_top(page)
    sh.shot("狀態列展開：最後一行是三方「態勢」官軍・黃巾・豪強", "往下捲到戰況")
    tap(page, who, settle=300)
    fronts = page.locator("#page .fronts")
    if has(fronts):
        scroll_to(page, fronts, 330)
        sh.shot("三條戰況（潁川汝南、南陽、冀州）排在行動列下面、小地圖上面", "按底下的「輿圖」分頁", page.locator('.tabs button[data-tab="map"]'))
    else:
        sh.miss("戰況條（江湖頁沒有戰況）")
    with page.expect_response(api_path("/api/map")):
        page.locator('.tabs button[data-tab="map"]').click()
    page.wait_for_timeout(1200)
    to_top(page)
    sh.shot("輿圖（以所在地潁川郡為中心）", "在上面的下拉選單選「長社」（官軍的投靠地點之一）", page.locator("#place"))
    with page.expect_response(api_path("/api/map")):
        page.select_option("#place", JOIN_AT)
    page.wait_for_timeout(1200)
    to_top(page)
    dash = page.locator('.travel-row button[data-mode="dash"]:not([disabled])')
    sh.shot("選了長社：地圖移到長社，底下黏著步行／趕路／疾行（地點詳情在地圖下面）", "按「疾行」", dash)
    tap(page, dash, "/api/travel")
    clear_events(page)
    to_top(page)
    call = option(page, "act:call")
    if has(call):
        full = next((o["label"] for o in api(page, "/api/main")["options"] if o["id"] == "act:train"), "")
        sh.shot("到了長社：第四顆變成「求見」（這裡有龍頭人物），行動列下面多一行「此地還能做 1 件事」", "按「求見」", call,
                note=f"「遊歷」底下只寫體力，選單上的完整說明是「{full}」，勝算沒有顯示在畫面上" if "・" in full else "")
        tap(page, call, "/api/choose")
        to_top(page)
        back = option(page, "call:back")
        sh.shot("求見：列出這裡能見的人物，挑一位才開始對話（對話要本機模型）", "按「返回」", back)
        tap(page, back, "/api/choose")
        to_top(page)
    else:
        sh.miss("求見（長社沒有求見）")
    here = page.locator("#page details.here > summary")
    if not has(here):
        sh.miss("投靠（長社沒有「此地還能做」）")
    else:
        sh.shot("回到長社的江湖頁", "點「此地還能做 1 件事」", here)
        tap(page, here, settle=500)
        join = option(page, f"faction:{JOIN_FACTION}")
        sh.shot("摺疊打開：投靠官軍", "按「投靠官軍」", join)
        tap(page, join, "/api/choose")
        to_top(page)
        confirm = option(page, "faction:confirm")
        sh.shot("投靠要再確認一次：寫明投靠後這一季不能改投，與目前各陣營的人數", "按「確定投靠官軍」", confirm)
        tap(page, confirm, "/api/choose")
        to_top(page)
        orders = page.locator("#page details.orders")
        if has(orders):
            scroll_to(page, orders, 170)
            sh.shot("投靠之後：名號旁寫「官軍」，行動列下面多一張「本週軍令」（預設展開）：三道軍令，各有陣營進度條、你做了幾次與截止時間")
        else:
            sh.miss("本週軍令卡（投靠之後沒有軍令）")
        here = page.locator("#page details.here")
        if has(here):
            if not here.first.evaluate("(el) => el.open"):
                page.locator("#page details.here > summary").first.click()
                page.wait_for_timeout(400)
            scroll_to(page, here, 330)
            sh.shot("投靠之後「此地還能做」多了「巡哨」與伏筆的「束苣乘城（時候未到）」")
    # 伏筆物品：到潁川郊野探索，碰上「河灘蘆葦」割一捆（不拍）
    held = grind_clue(page, apage)
    reload(page)
    clear_events(page)
    tap(page, page.locator('.tabs button[data-tab="craft"]'), "/api/menxia", settle=1200)
    clues = page.locator("#page .clues")
    if held and has(clues):
        to_top(page)
        sh.shot("（中間到潁川郊野探索，碰上「河灘蘆葦」割了一捆）煉製頁：意境清單下面多一塊「伏筆物品」，只有名字與數量",
                note="伏筆物品是官軍才碰得到的事件給的；這一張是探索到拿到為止才拍")
    else:
        sh.miss("伏筆物品（探索了好幾回都沒碰上「河灘蘆葦」）")
    # 推進到第 4 週，讓結算卡的大事多幾件（不拍）；不推到第 6 週的長社決戰
    api(apage, "/api/do/fast_forward", {"hours": 8})
    api(apage, "/api/do/fast_forward", {"hours": 8})
    # 管理者立刻收季
    reload(apage)
    sh.page = apage
    to_top(apage)
    with apage.expect_response(api_path("/api/admin")):
        apage.locator('button[data-act="sheet"]').click()
    apage.wait_for_timeout(700)
    admin_op(apage, "end_season", sh, ("（管理者，快轉到第 4 週之後）設定抽屜的管理者工具：開季、⚠ 立刻收季、⚠ 開啟下一季",
                                       "（管理者）確認框：寫明收季會算出結局與武學榜、全服進入休季"))
    sh.page = page
    reload(page)
    to_top(page)
    result = page.locator("#page .result")
    if not has(result):
        sh.miss("休季結算卡（收季之後江湖頁沒有結算卡）")
    else:
        events = page.locator("#page .result details.fold > summary", has_text="大事")
        sh.shot("（玩家）休季：江湖頁最上面是「賽季落幕」結算卡：結局、最終態勢、最終戰況，底下兩個摺疊", "點「這一季的十二件大事」", events)
        tap(page, events, settle=500)
        scroll_to(page, events, 150)
        sh.shot("十二件大事展開：發生過的寫結果，還沒輪到的寫「季已落幕，沒有發生」", "往下捲，點「各陣營出力前五」")
        ranks = page.locator("#page .result details.fold > summary", has_text="出力")
        scroll_to(page, ranks, 300)
        ranks.first.click()
        page.wait_for_timeout(500)
        scroll_to(page, ranks, 150)
        sh.shot("各陣營出力前五展開", "往下捲")
        stuck = page.locator('#page .options button[data-id^="season:"]')
        if has(stuck):
            scroll_to(page, stuck, 330)
            sh.shot("結算卡下面照舊是本週大事、「剛剛」與場景；行動只剩灰的「休季中，等待管理者開啟下一季」")
    actx.close()
    ctx.close()


# ── 主程式 ──────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="拍天下大勢網頁介面的手機截圖")
    parser.add_argument("--src", required=True, help="匯出的程式碼樹（有 server.py 與 web/）")
    parser.add_argument("--python", required=True, help="裝了 fastapi／uvicorn 的 python.exe（專案的 .venv）")
    parser.add_argument("--port", type=int, default=7882, help="預設設定的伺服器；第一季那一台用下一個 port")
    parser.add_argument("--out", required=True, help="截圖與 manifest.json 的輸出資料夾")
    parser.add_argument("--work", default=str(Path(os.environ.get("TEMP", "/tmp")) / "tianxia-webcap"),
                        help="暫存資料夾：資料庫、密碼、伺服器記錄都放這裡")
    parser.add_argument("--commit", default="", help="寫進 manifest 的版本（不給就讀 --src 裡的 .webcap-commit，沒有就留白）")
    parser.add_argument("--channel", default="msedge", help="瀏覽器：msedge 或 chrome")
    parser.add_argument("--llm-wait", type=int, default=180, help="煉製等本機模型最多幾秒")
    parser.add_argument("--quality", type=int, default=80, help="JPEG 品質")
    parser.add_argument("--only", choices=["main", "season-one"], default=None, help="只拍其中一台（測試腳本用）")
    args = parser.parse_args(argv)

    ports = [args.port, args.port + 1]
    if any(p in RESERVED_PORTS for p in ports):
        print("7860～7871 是開發與試玩伺服器在用的 port，換一個。")
        return 2
    for p in ports:
        if port_busy(p):
            print(f"port {p} 已經有人在聽，先關掉或換一個。")
            return 2
    src, out, work = Path(args.src).resolve(), Path(args.out).resolve(), Path(args.work).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    # manifest 裡標了 "external": true 的流程（例如從別的預覽伺服器手動拍的）不是這支腳本拍的：保留圖檔與紀錄
    external: list[dict] = []
    if (out / "manifest.json").exists():
        old_manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        external = [f for f in old_manifest.get("flows", []) if f.get("external")]
    keep = {s["file"] for f in external for s in f["steps"]}
    for old in out.glob("*.jpg"):
        if old.name not in keep:
            old.unlink()

    commit = args.commit or ((src / ".webcap-commit").read_text(encoding="utf-8").strip() if (src / ".webcap-commit").exists() else "")
    sh = Shooter(out, args.quality)
    ctx_opts = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                    locale="zh-TW", color_scheme="light")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel)
        try:
            if args.only in (None, "main"):
                with Server(args, work / "main", args.port, None, "預設") as srv:
                    flow_admin(sh, browser, srv, ctx_opts)
                    ctx, page = flow_first_visit(sh, browser, srv, ctx_opts)
                    flow_turn_start(sh, page)
                    flow_socialize(sh, page)
                    flow_practice(sh, page)
                    if flow_map(sh, page):
                        flow_fight(sh, page)
                    flow_craft(sh, page, args.llm_wait)
                    flow_news(sh, page)
                    flow_settings(sh, page)
                    flow_walk(sh, page)
                    ctx.close()
            if args.only in (None, "season-one"):
                with Server(args, work / "season-one", args.port + 1, "weekend", "第一季") as srv:
                    flow_season_one(sh, browser, srv, ctx_opts)
        finally:
            browser.close()

    order = ["G", "A", "B", "J", "C", "D", "E", "F", "S", "W", "H"]
    flows = sorted(sh.flows + external, key=lambda f: order.index(f["id"]) if f["id"] in order else 99)
    manifest = {
        "source": commit,
        "captured": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "viewport": "390x844@2x",
        "capture_order": "實際拍攝順序：預設設定那一台（同一個玩家一路玩下來）G → A → B（探索、打坐）→ J → C → E → B（遊歷）→ D → F → S → B（移動、步行）；"
                         "第一季那一台（TIANXIA_PROFILE=weekend，另一個資料庫）W",
        "flows": flows,
    }
    if sh.missed:
        manifest["missed"] = sh.missed
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in out.glob("*.jpg"))
    print(f"完成：{sum(len(f['steps']) for f in flows)} 張，共 {size / 1024 / 1024:.2f} MB → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

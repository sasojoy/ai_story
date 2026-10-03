"""拍《天下大勢》網頁介面（server.py + web/）的手機截圖：照真實操作一步一步拍，輸出 <ID>.jpg 與 manifest.json。

每一張都是「下一步要按的東西已經框起來」的畫面（朱紅外框＋步驟編號），每段流程最後再拍一張結果。
用途是跟企劃者一頁一頁討論介面，不是測試：遊戲有亂數，每次重拍的事件、戰果、素材都可能不同。

準備（只要做一次）：
  1. 另開一個虛擬環境裝 playwright（不要裝進專案的 .venv）：
       <python 3.14>/python.exe -m venv <暫存>/capvenv
       <暫存>/capvenv/Scripts/python.exe -m pip install playwright
     不用跑 `playwright install`，直接開電腦上的 Edge（--channel msedge；也可以 --channel chrome）。
  2. 把要拍的版本匯出成一份乾淨的樹（不碰任何 worktree）：
       git -C C:/Ray/專案/天下大勢 archive <commit> | tar -x -C <暫存>/webcap-src

重拍：
  <暫存>/capvenv/Scripts/python.exe capture_screens.py --src <暫存>/webcap-src
      --python C:/Ray/專案/天下大勢/.venv/Scripts/python.exe --port 7880 --out <輸出資料夾>
      [--work <暫存>/webcap] [--commit <版本>]

腳本會在 --work 開全新的資料庫（環境變數 TIANXIA_DB），用 scripts/set_password.py 建管理者 Rayal，
自己啟動 server.py、拍完就關掉（連同子行程）。管理者與玩家的密碼只寫在 --work 裡，不印在畫面上、不進輸出資料夾。
不要用 7860～7871（開發與試玩伺服器在用）。首次煉成的配方要等本機模型取名，最多等 --llm-wait 秒。
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
SKILL_NAME = "回風掌"
WILDS = "yingchuan_wilds"  # 潁川郊野：離起點最近、有敵人的地點

# 框起「下一步要按的東西」：朱紅外框＋步驟編號。position:fixed，所以先把元素捲進畫面（避開頂上狀態列與底部分頁列）。
MARK_JS = """(el, label) => {
  document.getElementById('__tap_mark')?.remove();
  el.scrollIntoView({block: 'center', inline: 'center'});
  let r = el.getBoundingClientRect();
  const fixed = getComputedStyle(el).position === 'fixed' || el.closest('.tabs, .sheet, .top, .sticky-act');
  if (!fixed) {
    const bottomLimit = innerHeight - 84, topLimit = 120;
    if (r.bottom > bottomLimit) window.scrollBy(0, r.bottom - bottomLimit);
    else if (r.top < topLimit && r.height < innerHeight - 220) window.scrollBy(0, r.top - topLimit);
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
            raise RuntimeError("server.py 啟動失敗，看 --work 裡的 server.log")
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

    def flow(self, fid: str, title: str) -> None:
        self.cur = {"id": fid, "title": title, "steps": []}
        self.flows.append(self.cur)
        self.n = 0

    def shot(self, screen: str, action: str = "", target=None, note: str = "") -> str:
        """拍目前的畫面。target 是下一步要按的元素（Locator），會先框起來、拍完再拿掉。"""
        self.n += 1
        sid = f"{self.cur['id']}{self.n}"
        if target is not None:
            target.first.evaluate(MARK_JS, sid)
            self.page.wait_for_timeout(150)
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
    page.wait_for_timeout(250)


def fetch_json(page, path: str) -> dict:
    return page.evaluate("(p) => fetch(p, {credentials: 'same-origin'}).then(r => r.json())", path)


def option(page, prefix: str):
    return page.locator(f'.options button[data-id^="{prefix}"]:not([disabled])')


def has(loc) -> bool:
    return loc.count() > 0


def pick_choice(page):
    """事件選項裡挑一個不用動手的（看熱鬧、離開之類）；都要動手就挑最後一個。"""
    choices = option(page, "choice:")
    n = choices.count()
    if n == 0:
        return None
    labels = [choices.nth(i).inner_text() for i in range(n)]
    for i in reversed(range(n)):
        if not re.search(r"出手|戰|打|殺|攻|闖", labels[i]):
            return choices.nth(i)
    return choices.nth(n - 1)


def clear_events(page, limit: int = 4) -> None:
    """有事件卡著（只剩事件選項）就隨手選掉，不拍。"""
    for _ in range(limit):
        if has(option(page, "act:")) or has(option(page, "move:")):
            return
        c = pick_choice(page)
        if c is None:
            return
        tap(page, c, "/api/choose")


def scene_title(page) -> str:
    el = page.locator(".scene p").first
    return el.inner_text().strip()[:30] if el.count() else ""


# ── 各段流程 ──────────────────────────────────────────


def flow_admin(sh: Shooter, browser, base: str, ctx_opts: dict, password: str) -> None:
    sh.flow("G", "管理者開季")
    ctx = browser.new_context(**ctx_opts)
    page = sh.page = ctx.new_page()
    page.goto(base + "/")
    page.wait_for_selector("#gate-form")
    page.wait_for_timeout(400)
    page.fill('#gate-form input[name="login"]', ADMIN_ACCOUNT)
    page.fill('#gate-form input[name="password"]', password)
    page.locator('#gate-form input[name="password"]').blur()
    sh.shot("登入頁，管理者的帳號密碼已填好（密碼顯示成圓點）", "按「登入」", page.locator('#gate-form button[type="submit"]'))
    tap(page, page.locator('#gate-form button[type="submit"]'), "/api/login")
    page.wait_for_selector(".options")
    sh.shot("管理者進到江湖頁：賽季還在籌備中，唯一的選項是灰的", "按右上角的 ⚙", page.locator('button[data-act="sheet"]'))
    with page.expect_response(api_path("/api/admin")):
        page.locator('button[data-act="sheet"]').click()
    page.wait_for_timeout(600)
    sh.shot("設定抽屜（管理者多一塊「管理者」）", "按「開季」", page.locator('.sheet button[data-op="open_season"]'))
    tap(page, page.locator('.sheet button[data-op="open_season"]'), "/api/do/open_season", settle=500)
    sh.shot("開季之後：底下跳出一句提示，抽屜還開著", "按「關閉」", page.locator('.sheet .btn[data-act="sheet-close"]'))
    tap(page, page.locator('.sheet .btn[data-act="sheet-close"]'))
    to_top(page)
    sh.shot("管理者的江湖頁：賽季開始，選項都出來了")
    ctx.close()


def flow_first_visit(sh: Shooter, browser, base: str, ctx_opts: dict, login: str, password: str):
    sh.flow("A", "第一次進來")
    ctx = browser.new_context(**ctx_opts)
    page = sh.page = ctx.new_page()
    page.goto(base + "/")
    page.wait_for_selector("#gate-form")
    page.wait_for_timeout(400)
    sh.shot("登入頁（預設在「登入」）", "按「註冊」", page.locator('.gate .seg button[data-mode="register"]'))
    tap(page, page.locator('.gate .seg button[data-mode="register"]'), settle=300)
    page.fill('#gate-form input[name="login"]', login)
    page.fill('#gate-form input[name="password"]', password)
    page.fill('#gate-form input[name="again"]', password)
    page.locator('#gate-form input[name="again"]').blur()
    sh.shot("註冊表單已填好（帳號、密碼、再輸入一次）", "按「註冊」", page.locator('#gate-form button[type="submit"]'))
    tap(page, page.locator('#gate-form button[type="submit"]'), "/api/register")
    page.wait_for_selector("#create-form")
    page.fill('#create-form input[name="name"]', PLAYER_NAME)
    page.locator('#create-form input[name="name"]').blur()
    sh.shot(f"取名號頁，已輸入「{PLAYER_NAME}」", "按「建立角色」", page.locator('#create-form button[type="submit"]'))
    tap(page, page.locator('#create-form button[type="submit"]'), "/api/character")
    page.wait_for_selector(".options")
    to_top(page)
    sh.shot("進入江湖的第一個畫面（第一屏）", "往下捲")
    page.locator(".options").scroll_into_view_if_needed()
    page.evaluate("window.scrollBy(0, 200)")
    page.wait_for_timeout(300)
    sh.shot("第一個畫面往下捲：選項、小地圖、看江湖紀錄")
    return ctx, page


def flow_turn_start(sh: Shooter, page) -> None:
    sh.flow("B", "江湖的一回合")
    to_top(page)
    explore = option(page, "act:explore")
    sh.shot("江湖頁，準備探索", "按「探索」", explore)
    tap(page, explore, "/api/choose")
    to_top(page)
    title = scene_title(page)
    choice = pick_choice(page)
    if choice is not None:
        sh.shot(f"探索的結果：「剛剛」卡片與遇上的事件（{title}）", "往下捲看事件選項")
        label = choice.inner_text().split("\n")[-1].strip()
        sh.shot("事件的選項（還沒處理完之前，其他選項都不見了）", f"按「{label}」", choice)
        tap(page, choice, "/api/choose")
        clear_events(page)
        to_top(page)
    rest = option(page, "act:rest")
    if has(rest):
        sh.shot("事件處理完，回到一般選項；打坐排在選項最底下", "按「打坐」", rest)
        tap(page, rest, "/api/choose")
        to_top(page)
        stand = option(page, "act:stand")
        if has(stand):
            sh.shot("打坐中：體力回復加倍，選項只剩「起身」", "按「起身」", stand)
            tap(page, stand, "/api/choose")
    else:
        sh.miss("打坐（這一回合沒有出現打坐選項）")


def flow_socialize(sh: Shooter, page) -> None:
    sh.flow("J", "交遊（只拍到按下去之前）")
    to_top(page)
    social = option(page, "act:socialize")
    if has(social):
        sh.shot("起身之後回到江湖頁；交遊會找這裡的龍頭人物說話", "（不按：按下去要等本機模型生成對話）", social,
                note="需要本機模型，這次沒拍按下去之後的畫面")
    else:
        sh.miss("交遊（這裡沒有交遊選項）")


def flow_practice(sh: Shooter, page) -> None:
    sh.flow("C", "修練")
    tab = page.locator('.tabs button[data-tab="practice"]')
    sh.shot("江湖頁", "按底下的「修練」分頁", tab)
    tap(page, tab, "/api/menxia")
    to_top(page)
    sh.shot("修練頁剛打開（武學／內功切換、鍛鍊、療傷、自創、閉關、功法庫、門下）", "往下捲到「自創功法」")
    box = page.locator('#create-skill input[name="name"]')
    box.fill(SKILL_NAME)
    box.blur()
    sh.shot(f"自創功法：已輸入「{SKILL_NAME}」", "按「自創」", page.locator('#create-skill button[type="submit"]'))
    tap(page, page.locator('#create-skill button[type="submit"]'), "/api/menxia/create")
    to_top(page)
    practice = page.locator('button[data-op="practice"]')
    sh.shot("自創的結果寫在最上面", "按「鍛鍊武學」", practice)
    tap(page, practice, "/api/menxia/practice")
    for _ in range(12):  # 連按到第十成，中間不拍
        msg = page.locator("#mx-msg").inner_text()
        if "第10成" in msg or "已經" in msg or "練滿" in msg or "十成" in msg:
            break
        tap(page, page.locator('button[data-op="practice"]'), "/api/menxia/practice", settle=400)
    to_top(page)
    sh.shot("連按「鍛鍊武學」練到第十成之後的修練頁（每按一次只換掉最上面那一句）", "往下捲看「本人」角色卡")
    card = page.locator("details.fold summary", has_text="本人")
    if has(card):
        card.first.evaluate("(el) => window.scrollBy(0, el.getBoundingClientRect().top - 150)")  # 「功法庫」在上、角色卡在下
        page.wait_for_timeout(300)
        sh.shot("修練頁下半：功法庫與「本人」角色卡")


def flow_map(sh: Shooter, page) -> bool:
    sh.flow("E", "輿圖")
    tab = page.locator('.tabs button[data-tab="map"]')
    sh.shot("修練頁", "按底下的「輿圖」分頁", tab)
    tap(page, tab, "/api/map")
    to_top(page)
    enemies = page.locator('.seg button[data-layer="enemies"]')
    sh.shot("輿圖剛打開（局勢圖層，整張縮小到螢幕寬）", "按「敵情」圖層", enemies)
    tap(page, enemies, "/api/map")
    node = page.locator(f'#map [data-loc="{WILDS}"]')
    if not has(node):
        sh.miss("輿圖上點地點（地圖上找不到潁川郊野）")
        return False
    sh.shot("敵情圖層", "在地圖上點「潁川郊野」", node)
    tap(page, node, "/api/map")
    dash = page.locator('.travel-row button[data-mode="dash"]:not([disabled])')
    if not has(dash):
        to_top(page)
        sh.shot("潁川郊野的地點詳情（沒辦法疾行）", note="疾行按鈕是灰的")
        sh.miss("疾行（按鈕是灰的）")
        return False
    page.locator(".travel-row").scroll_into_view_if_needed()
    page.evaluate("window.scrollBy(0, 400)")
    page.wait_for_timeout(300)
    sh.shot("選了潁川郊野：地點詳情與步行／趕路／疾行三個按鈕", "按「疾行」（立刻抵達、自動跳回江湖頁，接 B 流程的歷練）", dash)
    tap(page, dash, "/api/travel")
    to_top(page)
    return True


def flow_fight(sh: Shooter, page) -> None:
    """接在 B 後面：到了有敵人的地點，歷練一場。"""
    sh.cur = next(f for f in sh.flows if f["id"] == "B")
    sh.n = len(sh.cur["steps"])
    clear_events(page)
    train = option(page, "act:train")
    if not has(train):
        sh.miss("歷練（這裡沒有歷練選項）")
        return
    sh.shot("從輿圖疾行到潁川郊野，自動跳回江湖頁；歷練按鈕寫著體力、對手數與勝算", "按「歷練」", train)
    tap(page, train, "/api/choose")
    to_top(page)
    if has(page.locator(".battle-card")):
        sh.shot("遭遇戰的戰鬥卡片（放在「剛剛」的位置），下面接著場景與選項")
    else:
        sh.shot("歷練的結果")


def gather_materials(page, want: int = 2, budget: int = 8) -> int:
    """湊到 want 個素材（不拍）：先歷練，沒得歷練就探索。回傳手上素材總數。"""
    for _ in range(budget):
        bag = fetch_json(page, "/api/menxia")
        total = sum(m["count"] for m in bag["materials"])
        if total >= want:
            return total
        clear_events(page)
        act = option(page, "act:train")
        if not has(act):
            act = option(page, "act:explore")
        if not has(act):
            return total
        tap(page, act, "/api/choose", settle=400)
        clear_events(page)
    bag = fetch_json(page, "/api/menxia")
    return sum(m["count"] for m in bag["materials"])


def flow_craft(sh: Shooter, page, llm_wait: int) -> None:
    sh.flow("D", "煉製")
    total = gather_materials(page)
    to_top(page)
    tab = page.locator('.tabs button[data-tab="craft"]')
    sh.shot("江湖頁（先歷練、探索湊了幾樣素材）", "按底下的「煉製」分頁", tab)
    tap(page, tab, "/api/menxia")
    to_top(page)
    if total < 2:
        sh.shot("煉製頁（素材不夠，開爐是灰的）")
        sh.miss(f"開爐（素材只有 {total} 個）")
        return
    chips = page.locator(".chips button.chip:not([disabled])")
    sh.shot("煉製頁：上面兩格爐位、底下是背包裡的素材", "點第一樣素材放進爐裡", chips)
    first_id = chips.first.get_attribute("data-id")
    tap(page, chips, "/api/craft_line", settle=400)
    chips = page.locator(".chips button.chip:not([disabled])")
    other = page.locator(f'.chips button.chip:not([disabled]):not([data-id="{first_id}"])')
    pick = other if has(other) else chips
    sh.shot("放進一樣之後：左邊爐位填上了，底下的素材數量少一個", "再點一樣素材", pick)
    tap(page, pick, "/api/craft_line", settle=400)
    forge = page.locator("#forge")
    sh.shot("兩格都放好了：開爐亮起來", "按「開爐煉製」", forge)
    started = time.time()
    try:
        with page.expect_response(api_path("/api/menxia/craft"), timeout=llm_wait * 1000):
            forge.click()
            page.wait_for_timeout(1500)
            if page.locator("#forge.forging").count():
                to_top(page)
                sh.shot("爐火正旺：等本機模型幫新配方取名（按鈕會發光）")
    except PWTimeout:
        sh.miss(f"煉製結果（等了 {llm_wait} 秒，本機模型還沒取好名字）")
        return
    waited = round(time.time() - started)
    page.wait_for_timeout(800)
    to_top(page)
    sh.shot("煉製的結果寫在最上面", note=f"這一爐從按下到出爐約 {waited} 秒")


def flow_news(sh: Shooter, page) -> None:
    sh.flow("F", "見聞")
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
    tap(page, tab, settle=500)
    clear_events(page)
    to_top(page)
    who = page.locator(".who")
    sh.shot("江湖頁頂上的狀態列", "點名號那一塊（展開更多數值）", who)
    tap(page, who, settle=400)
    sh.shot("狀態列展開：名望、善惡、四項屬性", "按右上角的 ⚙", page.locator('button[data-act="sheet"]'))
    tap(page, page.locator('button[data-act="sheet"]'), settle=600)
    sh.shot("一般玩家的設定抽屜：匿名、略過引導、改密碼、登出")
    tap(page, page.locator('.sheet .btn[data-act="sheet-close"]'), settle=400)
    who = page.locator(".who")
    tap(page, who, settle=300)  # 收回狀態列


def flow_walk(sh: Shooter, page) -> None:
    """最後才走路：步行要真的等幾分鐘，路上什麼都不能做。"""
    sh.cur = next(f for f in sh.flows if f["id"] == "B")
    sh.n = len(sh.cur["steps"])
    clear_events(page)
    move = option(page, "move:")
    if not has(move):
        sh.miss("步行（沒有可以走的路）")
        return
    label = move.first.inner_text().split("\n")[-1].strip()
    sh.shot("江湖頁的「前往」選項（步行，不花體力只花時間）", f"按「{label}」", move)
    tap(page, move, "/api/choose")
    to_top(page)
    sh.shot("在路上：選項只剩一個灰的「在路上」，到了會自己抵達")


# ── 主程式 ──────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="拍天下大勢網頁介面的手機截圖")
    parser.add_argument("--src", required=True, help="匯出的程式碼樹（有 server.py 與 web/）")
    parser.add_argument("--python", required=True, help="裝了 fastapi／uvicorn 的 python.exe（專案的 .venv）")
    parser.add_argument("--port", type=int, default=7880)
    parser.add_argument("--out", required=True, help="截圖與 manifest.json 的輸出資料夾")
    parser.add_argument("--work", default=str(Path(os.environ.get("TEMP", "/tmp")) / "tianxia-webcap"),
                        help="暫存資料夾：資料庫、密碼、伺服器記錄都放這裡")
    parser.add_argument("--commit", default="", help="寫進 manifest 的版本（不給就讀 --src 裡的 .webcap-commit，沒有就留白）")
    parser.add_argument("--channel", default="msedge", help="瀏覽器：msedge 或 chrome")
    parser.add_argument("--llm-wait", type=int, default=180, help="煉製等本機模型最多幾秒")
    parser.add_argument("--quality", type=int, default=80, help="JPEG 品質")
    args = parser.parse_args(argv)

    if args.port in RESERVED_PORTS:
        print("7860～7871 是開發與試玩伺服器在用的 port，換一個。")
        return 2
    if port_busy(args.port):
        print(f"port {args.port} 已經有人在聽，先關掉或換一個。")
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
    db = work / "tianxia.db"
    for f in (db, Path(f"{db}-wal"), Path(f"{db}-shm")):
        if f.exists():
            f.unlink()
    env = dict(os.environ, TIANXIA_DB=str(db), PYTHONIOENCODING="utf-8")

    print("建立管理者……")
    admin_pw = make_admin(args.python, src, db, work / "local", env)
    player_login = "jianke_" + secrets.token_hex(3)
    player_pw = secrets.token_urlsafe(9)
    (work / "player_credentials.txt").write_text(f"{player_login}\n{player_pw}\n", encoding="utf-8")

    commit = args.commit or ((src / ".webcap-commit").read_text(encoding="utf-8").strip() if (src / ".webcap-commit").exists() else "")
    base = f"http://127.0.0.1:{args.port}"
    log = open(work / "server.log", "w", encoding="utf-8")
    print(f"啟動 server.py（{base}）……")
    srv = subprocess.Popen([args.python, "-u", "server.py", "--port", str(args.port)], cwd=src, env=env, stdout=log, stderr=subprocess.STDOUT)
    sh = Shooter(out, args.quality)
    try:
        wait_until_up(base, srv)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel=args.channel)
            ctx_opts = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                            locale="zh-TW", color_scheme="light")
            flow_admin(sh, browser, base, ctx_opts, admin_pw)
            ctx, page = flow_first_visit(sh, browser, base, ctx_opts, player_login, player_pw)
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
            browser.close()
    finally:
        kill_tree(srv)
        log.close()
        if port_busy(args.port):
            print(f"警告：port {args.port} 還有人在聽，請手動關掉。")

    order = ["G", "A", "B", "J", "C", "D", "E", "F", "S", "H"]
    flows = sorted(sh.flows + external, key=lambda f: order.index(f["id"]) if f["id"] in order else 99)
    manifest = {
        "source": commit,
        "captured": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "viewport": "390x844@2x",
        "capture_order": "實際拍攝順序（同一個玩家一路玩下來）：G → A → B（探索、打坐）→ J → C → E → B（歷練）→ D → F → S → B（步行）",
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

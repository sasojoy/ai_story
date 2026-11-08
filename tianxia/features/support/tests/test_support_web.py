"""客服的畫面（帳號與客服第 211 批；web/support.js）：關著時設定抽屜一個位元組都不變；抽屜一行「客服 ›」與紅點；客服自己一頁（我的單／寫新單／一張單）；
送單與再回一句打對的路；客服身分的管理頁分流（不叫 /api/admin）；玩家與客服寫的字塞 HTML 只會變成字（XSS）。
照 tests/web/test_prologue_web.py 的做法把整支 app.js 放進 node 的假瀏覽器；沒有 node 就略過。"""
# 畫法在 web/support.js、web/app.js（sheetHtml 那三處）、web/admin.js（renderAdmin 開頭）；寫在這裡 test_for 改這幾個檔時才挑得到
from __future__ import annotations

import random

import pytest
import webharness
from test_prologue_web import DRIVER

import server
from tianxia.engine import Game

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.whole_content]

NAMES = '"bookHtml", "peerHtml"]'
SUPPORT_DRIVER = DRIVER.replace(NAMES, '"bookHtml", "peerHtml", "supportRow", "supportPageHtml", "supportDeskHtml", "supportDeskLink", "supportForm", "supportClick", "supportCardHtml"]')
assert SUPPORT_DRIVER != DRIVER

XSS = ('<img src=x onerror="globalThis.__pwned=1">', "<script>globalThis.__pwned=1</script>", '"><svg onload=alert(1)>')


def run(m, script, *, S=None, responses=None, app=None):
    payload = {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}}
    if app is not None:  # 沒有 support.js 的那一份：support 的名字不在，用原本那一張名字
        payload["app"] = str(app)
    return webharness.run(DRIVER if app is not None else SUPPORT_DRIVER, payload)


@pytest.fixture
def main(content):
    g = Game.new(content, "沈浪", rng=random.Random(0))
    g.client = None
    return server.main_view(g)


def _without_support(tmp_path):
    """沒有 support.js、app.js 那三處換回原本的寫法：開關關著時抽屜要跟這一份一模一樣。"""
    parts = []
    for name in webharness.APP_FILES:
        if name == "support.js":
            continue
        text = (webharness.WEB / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        if name == "app.js":
            for new, old in (("${pushRow()}${supportRow()}", "${pushRow()}"), (': supportDeskLink()}<button', ': ""}<button'),
                             ('    if (S.supportPage && typeof supportPageHtml === "function") return supportPageHtml(); // 客服自己一頁（support.js；開關關著時進不來）\n', "")):
                assert text.count(new) == 1, new
                text = text.replace(new, old)
        parts.append(text)
    path = tmp_path / "app_without_support.js"
    path.write_text("(() => {\n" + "".join(parts) + "})();\n", encoding="utf-8")
    return path


def test_drawer_html_same_while_closed(main, tmp_path):
    assert not [k for k in main if k.startswith("support")]
    for extra in ({}, {"admin": True}):
        m = {**main, **extra}
        now = run(m, "return H.sheetHtml();", S={"sheet": True})
        before = run(m, "return H.sheetHtml();", S={"sheet": True}, app=_without_support(tmp_path))
        assert now == before
    assert run(main, "return [H.supportRow(), H.supportDeskLink()];") == ["", ""]


def test_the_drawer_row_and_the_red_dot(main):
    drawer = run({**main, "support_unread": 0}, "return H.sheetHtml();", S={"sheet": True})
    assert 'data-act="support-open"' in drawer and "客服 ›" in drawer and "sup-dot" not in drawer
    assert "sup-dot" in run({**main, "support_unread": 2}, "return H.sheetHtml();", S={"sheet": True})
    staff = run({**main, "support_unread": 0, "support_staff": True}, "return H.sheetHtml();", S={"sheet": True})
    assert 'href="/admin">客服單 ›' in staff
    admin = run({**main, "support_unread": 0, "support_staff": True, "admin": True}, "return H.sheetHtml();", S={"sheet": True})
    assert "管理者工具 ›" in admin and "客服單 ›" not in admin


def test_the_push_kind_shows_only_when_the_server_has_it(main):
    """notify.js：「客服」那一種只在伺服器的 kinds 有這個鍵才畫（客服關著時 /api/push 沒有它，設定頁不變）。"""
    script = """T.ctx.navigator.serviceWorker = {}; T.ctx.window.PushManager = {};
      T.ctx.Notification = T.ctx.window.Notification = { permission: "granted" }; return H.sheetHtml();"""
    five = {"letter": True, "duel": True, "rally": True, "raid": True, "xingshi": True}
    m = {**main, "web_push": True}
    closed = run(m, script, S={"sheet": True, "pushOn": True, "pushKinds": five})
    assert 'data-kind="xingshi"' in closed and 'data-kind="support"' not in closed
    opened = run(m, script, S={"sheet": True, "pushOn": True, "pushKinds": {**five, "support": False}})
    assert 'data-kind="support"' in opened and "> 客服</label>" in opened


def _ticket(**over):
    t = {"id": 7, "category": "mall", "category_name": "商城", "body": "月卡沒到", "status": "answered", "created": 1762581600, "updated": 1762585200,
         "replies": [{"staff": True, "body": "已補上", "created": 1762585200}]}
    t.update(over)
    return t


def test_the_support_page_mine_new_and_one_ticket(main):
    m = {**main, "support_unread": 1}
    mine = {"tickets": [_ticket()], "categories": {}, "body_max": 1000}
    page = run(m, "return H.sheetHtml();", S={"sheet": True, "supportPage": True, "supportMine": mine})
    assert 'aria-label="客服"' in page and "我的單" in page and "寫新單" in page and "‹ 回設定" in page
    assert "#7・商城" in page and "已回覆" in page and "客服：已補上" in page and "＋ 寫一張新單" in page
    new = run(m, "return H.sheetHtml();", S={"sheet": True, "supportPage": True, "supportMine": mine, "supportTab": "new"})
    assert 'id="support-new-form"' in new and "寫一張單" in new and "遊戲問題" in new and "想說的事（1,000 字內）" in new
    assert "帳號、名號、時間、版本會自動附上" in new
    one = run(m, "return H.sheetHtml();", S={"sheet": True, "supportPage": True, "supportMine": mine, "supportTicket": 7})
    assert "‹ 回客服" in one and "客服・回覆" in one and 'id="support-reply-form"' in one
    closed = run(m, "return H.sheetHtml();", S={"sheet": True, "supportPage": True, "supportMine": {"tickets": [_ticket(status="closed")]}, "supportTicket": 7})
    assert "已結" in closed and "support-reply-form" not in closed


def test_filing_and_replying_hit_the_right_routes(main):
    m = {**main, "support_unread": 0}
    out = run(m, """return (async () => {
        await H.supportForm({ id: "support-new-form", dataset: {} }, { category: "mall", body: "月卡沒到" });
        const after = [H.S.supportTab, H.S.supportTicket];
        await H.supportForm({ id: "support-reply-form", dataset: { id: "7" } }, { body: "還是沒有" });
        return { calls: T.calls, after };
      })();""", S={"sheet": True, "supportPage": True},
        responses={"/api/support/ticket": {"id": 7, "mine": {"tickets": [_ticket()]}}, "/api/support/reply": {"mine": {"tickets": [_ticket()]}}})
    assert out["calls"] == [["/api/support/ticket", {"category": "mall", "body": "月卡沒到"}], ["/api/support/reply", {"id": 7, "body": "還是沒有"}]]
    assert out["after"] == ["mine", 7]


def test_the_admin_page_for_staff_does_not_call_api_admin(main):
    m = {**main, "support_unread": 0, "support_staff": True, "admin": False}
    out = run(m, """return (async () => {
        H.render();
        await new Promise((r) => setTimeout(r, 0));
        return { html: T.els.app.innerHTML, calls: T.calls.map((c) => c[0]) };
      })();""", S={"adminPage": True}, responses={"/api/support/queue": {"open": 2, "waiting": 1, "fresh": 3, "tickets": []}})
    assert "/api/support/queue" in out["calls"] and not [c for c in out["calls"] if c.startswith("/api/admin")]
    assert "sup-wide" in out["html"] and "客服" in out["html"]
    desk = run(m, "return H.supportDeskHtml();", S={"supportDesk": {"open": 2, "waiting": 1, "fresh": 3, "tickets": [
        {"id": 3, "category": "account", "category_name": "帳號", "body": "登不進去", "status": "open", "admin_flag": False, "character": "沈青衫", "login": "shen_01",
         "created": 1762581600, "updated": 1762581600}]}})
    assert "沒回的" in desk and "等玩家" in desk and "今天" in desk and "新單" in desk and "客服單" in desk and "#3" in desk and "（帳號 shen_01）" in desk
    player = run({**main, "support_unread": 0}, "H.render(); return T.els.app.innerHTML;", S={"adminPage": True})
    assert "sup-wide" not in player  # 不是客服、不是管理者：照舊回江湖


def test_ticket_body_xss(main):
    """單的內容、客服的回覆、名號、帳號、版本塞 HTML：畫出來只會是字，沒有多出任何元素、也沒有跑。"""
    m = {**main, "support_unread": 1, "support_staff": True}
    for payload in XSS:
        t = _ticket(body=payload, category_name=payload, replies=[{"staff": True, "body": payload, "created": 1}, {"staff": False, "body": payload, "created": 2}])
        pages = [
            run(m, "return H.sheetHtml();", S={"sheet": True, "supportPage": True, "supportMine": {"tickets": [t]}}),
            run(m, "return H.sheetHtml();", S={"sheet": True, "supportPage": True, "supportMine": {"tickets": [t]}, "supportTicket": 7}),
            run(m, "return H.supportDeskHtml();", S={
                "supportDesk": {"open": 1, "waiting": 0, "fresh": 1, "tickets": [{**t, "character": payload, "login": payload, "admin_flag": False}]},
                "supportDeskTicket": {**t, "version": payload, "admin_flag": False,
                                      "account": {"id": 1, "login": payload, "character": payload, "created": 1},
                                      "replies": [{"staff": True, "internal": True, "body": payload, "created": 3}]}}),
        ]
        for html in pages:
            for tag in ("<img", "<script", "<svg"):
                assert tag not in html, (payload, tag)
            assert "onerror=\"" not in html and "&lt;" in html
    assert run(m, "return globalThis.__pwned || null;") is None


# ── 第 212 批：帳號卡與查帳號 ──

def _card(**over):
    c = {"id": 5, "login": "shen_01", "character": "沈青衫", "created": 1762000000, "balance": 2700,
         "binds": [{"provider": "password", "name": "密碼", "shown": ""}, {"provider": "phone", "name": "手機", "shown": "09*****678"}],
         "ledger": [{"time": 1762100000, "delta": -300, "reason": "購買", "note": ""}, {"time": 1762000000, "delta": 3000, "reason": "封測發放", "note": "封測"}]}
    c.update(over)
    return c


def _desk_state(card, **over):
    q = {"open": 1, "waiting": 0, "fresh": 1, "lookups_left": 18, "tickets": [
        {"id": 3, "category": "mall", "category_name": "商城", "body": "月卡沒到", "status": "open", "admin_flag": False, "character": "沈青衫",
         "login": "shen_01", "created": 1762581600, "updated": 1762581600}]}
    t = {**_ticket(id=3, status="open"), "version": "11/08", "admin_flag": False,
         "account": {"id": 5, "login": "shen_01", "character": "沈青衫", "created": 1762000000}, "card": card}
    return {"supportDesk": q, "supportDeskTicket": t, "supportDeskPick": 3, **over}


def test_desk_card_and_lookup_form(main):
    m = {**main, "support_unread": 0, "support_staff": True}
    desk = run(m, "return H.supportDeskHtml();", S=_desk_state(_card()))
    assert "查帳剩" in desk and "<b>18</b>" in desk and "這一小時" in desk
    assert 'id="support-lookup-form"' in desk and 'name="kind"' in desk and 'name="text"' in desk and 'name="ticket"' in desk and 'name="id"' not in desk and 'value="3"' in desk  # 欄位不能叫 id：瀏覽器會拿它蓋掉 form.id，殼就找不到處理函式
    assert "查別的帳號" in desk and "不收名號" in desk and "每小時 20 次" in desk
    assert "帳號 shen_01" in desk and "密碼、手機 09*****678" in desk and "2700 元寶" in desk and "元寶帳本" in desk
    assert "−300" in desk and "+3000" in desk and "封測發放" in desk and "購買" in desk
    nochar = run(m, 'return H.supportCardHtml({"login": "id:9", "created": 1, "character": null, "binds": [], "balance": 0, "ledger": []});')
    assert "還沒建角色。" in nochar and "id:9" in nochar
    gone = run(m, "return H.supportDeskHtml();", S=_desk_state({"gone": True}))
    assert "單上的帳號已經不在了。" in gone and "元寶帳本" not in gone
    out = run(m, """return (async () => {
        await H.supportForm({ id: "support-lookup-form", dataset: {} }, { kind: "email", text: "a@b.com", ticket: "3" });
        return { calls: T.calls, msg: H.S.supportLookupMsg, left: H.S.supportDesk.lookups_left, card: H.S.supportDeskCard.login, html: H.supportDeskHtml() };
      })();""", S=_desk_state(_card()), responses={"/api/support/lookup": {"found": True, "card": _card(login="li_02"), "left": 17, "message": ""}})
    assert out["calls"] == [["/api/support/lookup", {"id": 3, "kind": "email", "text": "a@b.com"}]]
    assert out["msg"] == "已查到 li_02（這一小時還剩 17 次）。" and out["left"] == 17 and out["card"] == "li_02"
    assert "帳號 li_02" in out["html"] and "已查到 li_02" in out["html"] and 'value="a@b.com"' in out["html"]
    none = run(m, """return (async () => {
        await H.supportForm({ id: "support-lookup-form", dataset: {} }, { kind: "login", text: "nobody", ticket: "3" });
        return [H.S.supportLookupMsg, H.S.supportDeskCard];
      })();""", S=_desk_state(_card()), responses={"/api/support/lookup": {"found": False, "card": None, "left": 16, "message": "查無此帳號。"}})
    assert none == ["查無此帳號。這一小時還剩 16 次。", None]
    answered = {**_desk_state(_card())["supportDeskTicket"], "status": "answered"}
    answered.pop("card")
    kept = run(m, """return (async () => {
        await H.supportClick("support-answer", { dataset: { id: "3", then: "wait" } });
        return H.S.supportDeskTicket.card.login;
      })();""", S=_desk_state(_card()), responses={"/api/support/answer": answered, "/api/support/queue": _desk_state(None)["supportDesk"]})
    assert kept == "shen_01"  # 回單的回應不帶卡：沿用看單時的


def test_card_escapes_payload(main):
    m = {**main, "support_unread": 0, "support_staff": True}
    for payload in XSS:
        card = _card(login=payload, character=payload, binds=[{"provider": payload, "name": payload, "shown": payload}],
                     ledger=[{"time": 1, "delta": 1, "reason": payload, "note": payload}])
        pages = [run(m, "return H.supportDeskHtml();", S=_desk_state(card)),
                 run(m, "return H.supportDeskHtml();", S=_desk_state(None, supportDeskCard=card, supportLookupMsg=payload,
                                                                     supportLookupQ={"kind": payload, "text": payload, "id": payload}))]
        for html in pages:
            for tag in ("<img", "<script", "<svg"):
                assert tag not in html, (payload, tag)
            assert "&lt;" in html
    assert run(m, "return globalThis.__pwned || null;") is None

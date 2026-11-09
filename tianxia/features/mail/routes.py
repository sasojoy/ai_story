"""帖友書信的 API（功能包 tianxia/features/mail/；手冊 G10）：殼（server 模組，參數 shell）照 FEATURES 掛。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。

- GET  /api/mail：信匣（actions.inbox）
- GET  /api/mail/thread?name=&before=：跟一位帖友的往來（actions.thread；打開就記成看過）
- POST /api/mail/send {name, text}：三段式——A 鎖內問寫不寫得了、字表擋不擋（actions.screen）；B 鎖外請模型審（shell.screen_text，speech.LETTER）；
  C 鎖內再查一次才寄（actions.send）。信只寫進小檔、角色存檔不動。寄成了叫收件人開著的分頁刷新（紅點）。
- POST /api/mail/block {name, value}、/api/mail/report {id}
管理者工具（管理頁「書信檢舉」）：mail_remove、mail_keep {id}、mail_mute {name, days}。
"""
from fastapi import APIRouter, Body, HTTPException, Request

from tianxia import speech
from tianxia.core.features import AdminTool

from . import actions


def _gate(shell):
    """Config.mail.enabled 關著一律 404（先於登入；殼的 test_shell_stays_thin 守）。"""
    def gate() -> None:
        if shell.CONTENT.config.mail.enabled:
            return
        raise HTTPException(404)
    return gate


def admin_tools(shell) -> dict[str, AdminTool]:
    gate = _gate(shell)
    return {
        "mail_remove": AdminTool(gate, lambda g, b: actions.admin_settle(g, shell._int(b.get("id"), 0), True)),
        "mail_keep": AdminTool(gate, lambda g, b: actions.admin_settle(g, shell._int(b.get("id"), 0), False)),
        "mail_mute": AdminTool(gate, lambda g, b: actions.admin_mute(g, str(b.get("name", "")), shell._int(b.get("days"), 0))),
    }


def router(shell) -> APIRouter:
    r = APIRouter()
    gate = _gate(shell)

    def _view(game, name: str = "") -> dict:
        def build(g):
            out = {"inbox": actions.inbox(g)}
            if name:
                out["thread"] = actions.thread(g, name)
            out.update(actions.status(g))
            return out
        return shell.look(game, build)

    @r.get("/api/mail")
    def api_mail(request: Request):
        gate()
        game = shell._game(request)
        return shell.look(game, lambda g: {"inbox": actions.inbox(g), **actions.status(g)})

    @r.get("/api/mail/thread")
    def api_mail_thread(request: Request, name: str = "", before: int = 0):
        gate()
        game = shell._game(request)
        if before:
            return shell.look(game, lambda g: {"thread": actions.thread(g, name, before)})
        return _view(game, name)

    @r.post("/api/mail/{op}")
    def api_mail_do(op: str, request: Request, body: dict = Body(default={})):
        gate()
        game = shell._game(request)
        name = str(body.get("name", ""))[:40]
        sent = False
        if op == "send":
            limit = game.content.config.mail.max_chars
            text = actions.clean(str(body.get("text", ""))[: limit * 2])
            verdict = shell.screen_text(game, text, speech.LETTER) if shell.look(game, lambda g: actions.screen(g, name, text)) else ""

            def go(g):
                nonlocal sent
                sent, line = actions.send(g, name, text, verdict)
                return [line]
            msgs = shell.act(game, go)
        elif op == "block":
            value = bool(body.get("value", True))
            msgs = shell.act(game, lambda g: [actions.set_block(g, name, value)])
        elif op == "report":
            msgs = shell.act(game, lambda g: [actions.report(g, shell._int(body.get("id"), 0))])
        else:
            raise HTTPException(404)
        shell._tell_tabs(game, also=name if sent else "")
        return {**_view(game, name), "ok": sent if op == "send" else True, "message": shell.joined(msgs)}

    return r

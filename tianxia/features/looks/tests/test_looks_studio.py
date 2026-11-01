"""畫坊（studio.py；Joy 2026-11-01「一步到位」、審圖選 Claude）：抓等圖的單、畫、切、審，不過照意見改、最多三張，過了照管理者上傳那一條收
（到齊了變待審），還是不過停手寫在訂單上、管理者按「再畫一次」重來；畫的時候訂單被退回就不收。自建形象先畫定裝照、十張照它畫同一個人。
生圖與審圖都是假的（不叫外部服務、不花錢）。"""
from __future__ import annotations

import pytest
from test_looks import _game
from test_looks_moves import ART, BUDDHA, _admin, _art, on  # noqa: F401  fixture

from tianxia.features.looks import actions, moves, orders, studio
from tianxia.wallet import Wallet

SHEET = {s: (actions.WEB_IMG / "arena" / f"{s}.webp").read_bytes() for s in orders.SHEETS}  # 斗笠小子那一套：格數對的現成圖


class Painter:
    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    def paint(self, prompt, images, aspect, size):
        self.calls.append((prompt, len(images)))
        return b"raw"


class Critic:
    def __init__(self, verdicts=()):
        self.verdicts, self.seen = list(verdicts), []

    def review(self, checklist, image, refs):
        self.seen.append(checklist)
        return self.verdicts.pop(0) if self.verdicts else studio.Verdict(True)


def cut(job, raw):
    """假的切圖：絕招那幾樣回一張小的去背圖，形象回那一張格數對的現成圖，定裝照原樣。"""
    return ART if job.kind == "move" else raw if job.slot == studio.PORTRAIT else SHEET[job.slot]


def _tick(game, painter, critic, **kw):
    return studio.tick(game.content, game.world, actions.image_root(game), actions.WEB_IMG, painter, critic, cut, **kw)


def _move_order(on, game):
    _art(game)
    actions.order_move(game, BUDDHA, "move-ref-001")
    return actions.view(game)["moves"]["list"][0]["id"]


def test_a_move_gets_both_drawings_and_waits_for_the_admin(on):
    game = _game(on)
    pid = _move_order(on, game)
    painter, critic = Painter(), Critic()
    lines = _tick(game, painter, critic)
    assert lines == [f"#{pid} 大佛 收了"] and "「大佛」" in painter.calls[0][0] and "大佛" in critic.seen[0]
    assert BUDDHA in critic.seen[0]  # 審圖看得到玩家寫的那一句（系統提示寫明那是資料）
    assert _tick(game, painter, critic) == [f"#{pid} 佛掌 收了，到齊了等管理者上架"]
    wallet = Wallet(game.world.db)
    assert moves.of(wallet.purchase(pid)).status == orders.REVIEW
    assert _tick(game, painter, critic) == []  # 沒有要畫的了
    row = actions.admin_view(_admin(on, game.world))["moves"]["open"][0]
    assert row["studio"] == {"painted": 2, "failed": ""} and row["have"]
    assert "上架了" in actions.admin_move_release(_admin(on, game.world), pid)[-1]


def test_a_failed_review_is_fixed_from_the_last_picture(on):
    game = _game(on)
    pid = _move_order(on, game)
    painter = Painter()
    critic = Critic([studio.Verdict(False, ["佛像多了一隻手"], "Remove the extra arm.")])
    assert _tick(game, painter, critic) == [f"#{pid} 大佛 收了"]
    fix, refs = painter.calls[1]
    assert "Remove the extra arm." in fix and refs == 2  # 上一張＋參考圖
    assert Wallet(game.world.db).purchase(pid).data["studio"]["painted"] == 2


def test_three_misses_stop_until_the_admin_says_again(on):
    game = _game(on)
    pid = _move_order(on, game)
    painter = Painter()
    no = studio.Verdict(False, ["有字"], "Remove the text.")
    lines = _tick(game, painter, Critic([no, no, no]))
    assert len(painter.calls) == studio.MAX_TRIES and "停手等管理者" in lines[0] and "有字" in lines[0]
    assert _tick(game, painter, Critic()) == []  # 停手了不再畫（不燒錢）
    admin = _admin(on, game.world)
    row = actions.admin_view(admin)["moves"]["open"][0]
    assert row["studio"]["painted"] == 3 and "大佛：有字" in row["studio"]["failed"]
    assert "交回畫坊" in actions.admin_studio_retry(admin, pid)[-1]
    assert "沒有停手" in actions.admin_studio_retry(admin, pid)[-1]
    assert _tick(game, painter, Critic()) == [f"#{pid} 大佛 收了"]
    assert actions.admin_studio_retry(game, pid)[-1] == "（此刻無法這麼做。）"  # 不是管理者


def test_a_cut_that_fails_counts_as_a_miss(on):
    game = _game(on)
    pid = _move_order(on, game)
    tries = []

    def bad_cut(job, raw):
        tries.append(1)
        if len(tries) == 1:
            raise studio.CutError("去背之後什麼都不剩")
        return ART

    painter = Painter()
    assert studio.tick(game.content, game.world, actions.image_root(game), actions.WEB_IMG, painter, Critic(), bad_cut) == [f"#{pid} 大佛 收了"]
    assert "pure white background" in painter.calls[1][0]


def test_blocked_and_busy(on):
    game = _game(on)
    pid = _move_order(on, game)

    class Blocked(Painter):
        def paint(self, *a):
            raise studio.PaintBlocked("IMAGE_SAFETY")

    class Busy(Painter):
        def paint(self, *a):
            raise studio.PaintBusy("HTTP 503")

    assert "下一輪再來" in _tick(game, Busy(), Critic())[0]
    assert "studio" not in Wallet(game.world.db).purchase(pid).data  # 忙不算
    assert "生圖的拒畫（IMAGE_SAFETY）" in _tick(game, Blocked(), Critic())[0]


def test_a_rejected_order_is_not_drawn_into(on, monkeypatch):
    game = _game(on)
    pid = _move_order(on, game)
    admin = _admin(on, game.world)

    class Rejecting(Painter):
        def paint(self, *a):  # 畫的時候管理者退回了
            if not self.calls:
                actions.admin_move_reject(admin, pid, "不收")
            return super().paint(*a)

    assert "已經不在等圖" in _tick(game, Rejecting(), Critic())[0]
    assert orders.sheet_file(actions.image_root(game), moves.move_id(pid), "art1") is None


def test_a_wrong_size_from_the_cut_is_refused(on):
    game = _game(on)
    pid = _move_order(on, game)
    big = SHEET["hero_atk_slash"][:30]  # 不是圖
    lines = studio.tick(game.content, game.world, actions.image_root(game), actions.WEB_IMG, Painter(), Critic(), lambda j, r: big)
    assert "格式不對" in lines[0] and Wallet(game.world.db).purchase(pid).data["studio"]["failed"]


def test_a_look_starts_from_its_portrait_and_draws_ten_sheets(on):
    game = _game(on)
    actions.order(game, "雪衣", "長髮飄飄，仙氣十足的仙子", "look-ref-001")
    pid = orders.mine(Wallet(game.world.db), game._mall_owner())[0].pid
    painter, critic = Painter(), Critic()
    PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20

    class PortraitPainter(Painter):
        def paint(self, prompt, images, aspect, size):
            super().paint(prompt, images, aspect, size)
            return PNG

    painter = PortraitPainter()
    assert _tick(game, painter, critic) == [f"#{pid} 定裝照好了"]
    assert "長髮飄飄" in painter.calls[0][0] and "定裝照" in painter.calls[0][0]
    root = actions.image_root(game)
    assert (orders.folder(root, orders.look_id(pid)) / "ref.png").read_bytes() == PNG
    lines = []
    for _ in orders.SHEETS:
        lines += _tick(game, painter, critic)
    assert lines[-1].endswith("到齊了等管理者上架") and len(lines) == len(orders.SHEETS)
    assert all(refs == 2 for _, refs in painter.calls[1:])  # 每一張都附斗笠那一張＋定裝照
    assert "same face, hair, clothes" in painter.calls[1][0]
    assert orders.of(Wallet(game.world.db).purchase(pid)).status == orders.REVIEW
    row = actions.admin_view(_admin(on, game.world))["open"][0]
    assert row["studio"]["painted"] == 1 + len(orders.SHEETS)


def test_budget_and_fake_orders_are_skipped(on, monkeypatch):
    game = _game(on)
    _move_order(on, game)
    assert _tick(game, Painter(), Critic(), budget=0) == []
    monkeypatch.setenv(actions.GEN_ENV, "fake")  # 假的生圖器當場抄好了：畫坊不碰
    other = _game(on, "楚留香")
    actions.order(other, "雪衣", "長髮飄飄", "look-ref-002")
    jobs = studio.jobs(on, Wallet(game.world.db), actions.image_root(game), actions.WEB_IMG)
    assert [j.kind for j in jobs] == ["move"]


# ── 真的切圖（要 Pillow、numpy、scipy：畫坊程式才裝） ──


def test_the_real_cut_keeps_one_subject_and_cuts_a_sheet():
    pytest.importorskip("scipy")
    import io

    from PIL import Image

    from tianxia.features.looks import cutting

    im = Image.new("RGB", (1024, 1024), "white")
    for x in range(300, 700):
        for y in range(200, 800):
            im.putpixel((x, y), (180, 120, 40))
    im.putpixel((10, 10), (0, 0, 0))  # 雜點
    raw = io.BytesIO()
    im.save(raw, "PNG")
    out = Image.open(io.BytesIO(cutting.art_bytes(raw.getvalue())))
    assert out.mode == "RGBA" and out.size == (400, 600)
    with pytest.raises(studio.CutError):
        blank = io.BytesIO()
        Image.new("RGB", (512, 512), "white").save(blank, "PNG")
        cutting.art_bytes(blank.getvalue())
    flat = Image.open(io.BytesIO(SHEET["hero_atk_slash"])).convert("RGBA")
    white = Image.new("RGBA", flat.size, "white")
    white.alpha_composite(flat)
    src = Image.new("RGB", (660, 440), "white")  # 斗笠小子那六格排成 3×2 再切回來
    for k in range(6):
        src.paste(white.crop((k * 220, 0, k * 220 + 220, 220)).convert("RGB"), ((k % 3) * 220, (k // 3) * 220))
    buf = io.BytesIO()
    src.save(buf, "PNG")
    strip = cutting.sheet_bytes(buf.getvalue(), "hero_atk_slash")
    assert orders.sheet_problem("hero_atk_slash", strip) is None


def test_a_character_without_a_hat_is_not_scaled_until_its_head_is_cut_off():
    """切格照斗笠寬定比例；自建形象不一定戴斗笠（2026-11-02「魔教聖女」連十張都被擋下，理由都是頭頂被裁掉）：
    hat() 在沒有斗笠時量到的是頭髮或肩線，倍率算過大、整個人被放大出框。cutting.FIT 夾住它——
    頭頂要留在格子裡，而且上緣要有空白。"""
    pytest.importorskip("scipy")
    import io

    import numpy as np
    from PIL import Image

    from tianxia.features.looks import cutting

    # 四格：一個「高瘦、沒有斗笠」的人形——頭很窄（會讓 hat() 量到窄寬度）、身子長
    src = Image.new("RGB", (4 * 260, 400), "white")
    for k in range(4):
        ox = k * 260 + 130
        for y in range(40, 110):  # 頭：窄
            for x in range(ox - 18, ox + 18):
                src.putpixel((x, y), (40, 40, 60))
        for y in range(110, 360):  # 身子與腿：更窄
            for x in range(ox - 26, ox + 26):
                src.putpixel((x, y), (150, 40, 40))
    buf = io.BytesIO()
    src.save(buf, "PNG")

    strip = cutting.sheet_bytes(buf.getvalue(), "hero_bare_idle")
    assert orders.sheet_problem("hero_bare_idle", strip) is None
    out = Image.open(io.BytesIO(strip)).convert("RGBA")
    assert out.size == (4 * cutting.CELL, cutting.CELL)
    alpha = np.asarray(out)[..., 3]
    assert alpha[0].max() == 0, "最上面那一列有東西：頭被切到格子邊界了"
    for k in range(4):
        cell = alpha[:, k * cutting.CELL:(k + 1) * cutting.CELL]
        rows = np.nonzero(cell.max(1))[0]
        assert len(rows), f"第 {k + 1} 格是空的"
        assert rows.min() >= 2, f"第 {k + 1} 格的頭貼到上緣（y={rows.min()}）"
        assert rows.max() <= cutting.BY + 2, f"第 {k + 1} 格的腳超過地平線（y={rows.max()}）"


def test_we_catch_the_bad_cuts_ourselves_before_paying_for_a_review():
    """切完自己先驗一遍（cutting.sheet_problems；Joy 2026-11-02「把能過的方法模組化」）：空格、腳下的地面線、
    貼到上緣這幾樣機器看得出來，就不要花一次審圖的錢——丟 CutProblem，畫坊照它帶的那一句英文重畫。
    每一條都是實際踩過的（#3 hero_atk_slash：「第2格是空的，只有一條地面線」「各格腳下畫有多餘的地面橫線」）。"""
    pytest.importorskip("scipy")
    import io

    from PIL import Image

    from tianxia.features.looks import cutting

    def strip_of(cells):
        im = Image.new("RGBA", (len(cells) * cutting.CELL, cutting.CELL), (0, 0, 0, 0))
        for k, draw in enumerate(cells):
            draw(im, k * cutting.CELL)
        return im

    def person(im, ox, top=60, bottom=cutting.BY):
        for y in range(top, bottom):
            for x in range(ox + 80, ox + 140):
                im.putpixel((x, y), (40, 40, 60, 255))

    def ground(im, ox):
        for x in range(ox + 4, ox + cutting.CELL - 4):
            for y in range(cutting.BY - 2, cutting.BY):
                im.putpixel((x, y), (60, 60, 60, 255))

    good = strip_of([lambda im, ox: person(im, ox)] * 3)
    assert cutting.sheet_problems(good, 3) == ([], "")

    empty = strip_of([lambda im, ox: person(im, ox), lambda im, ox: None, lambda im, ox: person(im, ox)])
    bad, fix = cutting.sheet_problems(empty, 3)
    assert any("第 2 格幾乎是空的" in b for b in bad) and "frame 2 is empty" in fix

    lined = strip_of([lambda im, ox: (person(im, ox), ground(im, ox))] * 3)
    bad, fix = cutting.sheet_problems(lined, 3)
    assert any("橫跨整格的線" in b for b in bad) and "do NOT draw any ground line" in fix

    high = strip_of([lambda im, ox: person(im, ox, top=0)] * 3)
    bad, fix = cutting.sheet_problems(high, 3)
    assert any("貼到上緣" in b for b in bad) and "empty space above the head" in fix

    # 壞的那一條走的是 CutProblem（畫坊照它帶的那一句重畫，不叫審圖）。照實際踩到的樣子造：
    # 第二格沒有人、只有一條地面線（#3 hero_atk_slash「第2格是空的，只有一條地面線」）
    buf = io.BytesIO()
    src = Image.new("RGB", (3 * 260, 400), "white")
    for k in range(3):
        ox = k * 260
        if k == 1:
            for x in range(ox + 20, ox + 240):  # 只有線
                for y in range(352, 356):
                    src.putpixel((x, y), (60, 60, 60))
            continue
        for y in range(60, 356):
            for x in range(ox + 110, ox + 150):
                src.putpixel((x, y), (40, 40, 60))
    src.save(buf, "PNG")
    with pytest.raises(studio.CutProblem) as caught:
        cutting.sheet_bytes(buf.getvalue(), "hero_bare_hit")
    assert caught.value.fix, "要帶一句給生圖的改法"


def test_cut_sheets_come_out_the_same_height_as_the_hat_boy_so_weapons_line_up():
    """web/arena_anim.js 的 RING_HAND（每一格的手部座標）是照預設斗笠小子 155 高的身體寫死的，
    所以切出來的自建形象一定要跟它一樣高，兵器才掛得準（Joy 2026-11-02「兵器套用上去就破圖了」）。
    照斗笠寬縮放做不到這件事：沒戴斗笠量到的是頭髮，連預設的 hero_bare_idle 重切都算成 199 高。"""
    pytest.importorskip("scipy")
    import io

    import numpy as np
    from PIL import Image

    from tianxia.features.looks import cutting

    def heights(data, frames):
        a = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))[..., 3]
        out = []
        for k in range(frames):
            ys = np.nonzero((a[:, k * cutting.CELL:(k + 1) * cutting.CELL] > 32).max(1))[0]
            out.append(int(ys.max() - ys.min() + 1) if len(ys) else 0)
        return out

    # 預設的斗笠小子重切一次：身高要跟原圖一樣（新規則不能改掉既有的圖）
    for name in ("hero_bare_idle", "hero_atk_slash"):
        cols, rows = cutting.LAYOUT[name]
        flat = Image.open(actions.WEB_IMG / "arena" / f"{name}.webp").convert("RGBA")
        white = Image.new("RGBA", flat.size, "white")
        white.alpha_composite(flat)
        src = Image.new("RGB", (cols * cutting.CELL, rows * cutting.CELL), "white")
        for k in range(cols * rows):
            src.paste(white.crop((k * cutting.CELL, 0, (k + 1) * cutting.CELL, cutting.CELL)).convert("RGB"),
                      ((k % cols) * cutting.CELL, (k // cols) * cutting.CELL))
        buf = io.BytesIO()
        src.save(buf, "PNG")
        after = heights(cutting.sheet_bytes(buf.getvalue(), name), cols * rows)
        assert max(after) == pytest.approx(cutting.BODY[name], abs=2), (name, after)

    # 一個「高瘦、沒斗笠」的人：也要被縮到標準身高，不是塞滿格子
    src = Image.new("RGB", (4 * 260, 400), "white")
    for k in range(4):
        ox = k * 260 + 130
        for y in range(30, 370):
            for x in range(ox - 22, ox + 22):
                src.putpixel((x, y), (40, 40, 60))
    buf = io.BytesIO()
    src.save(buf, "PNG")
    tall = heights(cutting.sheet_bytes(buf.getvalue(), "hero_bare_idle"), 4)
    assert max(tall) == pytest.approx(cutting.BODY["hero_bare_idle"], abs=2), tall


def test_refit_rescales_an_old_oversized_sheet_without_redrawing_it():
    """2026-11-02 之前切的自建形象高 190～200（照斗笠寬），生圖的原圖沒留著：refit 直接把成品縮回標準身高。"""
    pytest.importorskip("scipy")
    import io

    import numpy as np
    from PIL import Image

    from tianxia.features.looks import cutting

    big = Image.new("RGBA", (4 * cutting.CELL, cutting.CELL), (0, 0, 0, 0))
    for k in range(4):
        for y in range(cutting.BY - 200, cutting.BY):
            for x in range(k * cutting.CELL + 80, k * cutting.CELL + 130):
                big.putpixel((x, y), (40, 40, 60, 255))
    buf = io.BytesIO()
    big.save(buf, "WEBP")
    fixed = cutting.refit(buf.getvalue(), "hero_bare_idle")
    a = np.asarray(Image.open(io.BytesIO(fixed)).convert("RGBA"))[..., 3]
    for k in range(4):
        ys = np.nonzero((a[:, k * cutting.CELL:(k + 1) * cutting.CELL] > 32).max(1))[0]
        assert int(ys.max() - ys.min() + 1) == pytest.approx(cutting.BODY["hero_bare_idle"], abs=2)
        assert ys.max() == pytest.approx(cutting.BY, abs=2), "腳底要還在地平線上"
    assert cutting.refit(fixed, "hero_bare_idle") == fixed, "已經對的那一條原樣回傳"


def test_the_sheet_checklist_judges_the_action_as_a_whole_not_frame_by_frame():
    """Joy 2026-11-02 定的標準：出招那四張不要求逐格對準手的位置（六格動作圖生圖做不到，#3 一直卡在
    「第2格雙拳未併攏舉至右肩上方」這種理由），但硬規則全留。寬袖、飄帶也不算「手上拿著東西」。"""
    check = studio.CHECK_SHEET
    assert "judge the action as a whole, not frame by frame" in check
    assert "small differences in limb position are fine" in check
    assert "loose sleeves, ribbons, sashes and long hair are not objects" in check
    for hard in ("exactly {frames} frames", "one whole character in each", "same character as reference 2",
                 "holds no weapon or object", "side view facing right", "feet roughly on the same ground line"):
        assert hard in check, hard


def test_the_sheet_prompt_forbids_a_drawn_ground_line():
    """提示詞原本只說 no ground shadow（不要陰影），生圖照樣畫地平線，去背留著它、切格被帶歪。"""
    order = orders.Order(pid=1, owner="甲", name="試", prompt="紅衣少女", status=orders.PENDING,
                         reason="", look="u1", time=0.0)
    for prompt in orders.gen_prompts(order).values():
        assert "NO ground line" in prompt and "no horizon line" in prompt


# ── 真的去叫的那兩家（假的連線：看送出去的長什麼樣、回來的怎麼讀） ──


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, str(body)

    def json(self):
        return self._body


class _Session:
    def __init__(self, resp):
        self.resp, self.sent = resp, []

    def post(self, url, headers, json, timeout):
        self.sent.append((url, headers, json))
        return self.resp


def test_the_painter_sends_prompt_and_pictures_and_reads_the_last_image():
    pytest.importorskip("PIL")
    import base64

    from tianxia.features.looks.studio_api import GeminiPainter

    img = base64.b64encode(b"png!").decode()
    ok = _Resp(200, {"candidates": [{"content": {"parts": [{"text": "draft"}, {"inlineData": {"data": base64.b64encode(b"a").decode()}},
                                                         {"inlineData": {"mimeType": "image/png", "data": img}}]}}]})
    session = _Session(ok)
    painter = GeminiPainter(key="k", model="gemini-3.1-flash-image", session=session)
    assert painter.paint("畫一尊大佛", [ART], "1:1", "1K") == b"png!"
    url, headers, body = session.sent[0]
    assert url.endswith("/gemini-3.1-flash-image:generateContent") and headers == {"x-goog-api-key": "k"}
    parts = body["contents"][0]["parts"]
    assert parts[0] == {"text": "畫一尊大佛"} and parts[1]["inlineData"]["mimeType"] == "image/png"
    assert body["generationConfig"] == {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1", "imageSize": "1K"}}
    with pytest.raises(studio.PaintBusy):
        GeminiPainter(key="k", session=_Session(_Resp(503, {}))).paint("x", [], "1:1", "1K")
    with pytest.raises(studio.PaintBlocked, match="SAFETY"):
        GeminiPainter(key="k", session=_Session(_Resp(200, {"promptFeedback": {"blockReason": "SAFETY"}}))).paint("x", [], "1:1", "1K")
    with pytest.raises(studio.PaintBlocked, match="IMAGE_SAFETY"):
        GeminiPainter(key="k", session=_Session(_Resp(200, {"candidates": [{"finishReason": "IMAGE_SAFETY"}]}))).paint("x", [], "1:1", "1K")


def test_the_critic_asks_for_a_verdict_and_reads_it():
    pytest.importorskip("PIL")
    from types import SimpleNamespace as NS

    from tianxia.features.looks.studio_api import CRITIC_MODEL, ClaudeCritic

    class Messages:
        def __init__(self, replies):
            self.replies, self.sent = list(replies), []

        def create(self, **kw):
            self.sent.append(kw)
            return self.replies.pop(0)

    text = lambda t, stop="end_turn": NS(stop_reason=stop, content=[NS(type="text", text=t)])  # noqa: E731
    msgs = Messages([text('{"pass": false, "problems": ["有字"], "fix": "Remove the text."}'), text('{"pass": true, "problems": [], "fix": ""}'),
                     NS(stop_reason="refusal", content=[]), text("not json")])
    critic = ClaudeCritic(client=NS(beta=NS(messages=msgs)))
    assert critic.review("checklist", ART, [ART]) == studio.Verdict(False, ["有字"], "Remove the text.")
    sent = msgs.sent[0]
    assert sent["model"] == CRITIC_MODEL and sent["extra_body"]["fallbacks"] == "default"
    assert sent["extra_body"]["output_config"]["format"]["type"] == "json_schema"
    kinds = [c["type"] for c in sent["messages"][0]["content"]]
    assert kinds == ["text", "image", "text", "image", "text"] and "player" in sent["system"]
    assert critic.review("c", ART, []).ok
    assert not critic.review("c", ART, []).ok
    assert critic.review("c", ART, []).problems == ["審圖的回答看不懂"]

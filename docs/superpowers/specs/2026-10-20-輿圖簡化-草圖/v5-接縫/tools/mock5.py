"""第 5 批對比圖的原型：只改 scratchpad 解出來的那一份 web/app.js（不改工作樹）。網址帶 ?mock=A甲 這種，三種時刻各三個做法，
三個做法照同一個想法排（甲＝地圖不加新記號、乙＝區圖名字框旁加一枚字印、丙＝抽屜收著那一行多一條），挑的時候可以一欄挑到底、也可以每種時刻各挑：
A 戰書下了、還沒開打（時程表那一場 planned／waiting）：甲 只在卡上；乙 區圖名字框旁一枚「戰」字印、天下圖那一格朱紅虛線框；丙 抽屜收著那一行多一條。
B 攻城戰正在打（open）：甲 借現有的「激戰」（天下圖那一格紅光一閃、區圖名字框一圈紅閃）；乙 區圖「戰」字印一閃、天下圖那一格朱紅實線框；丙 抽屜收著那一行多一條。
C 打完（done，到換天）：甲 只在卡上（天下圖、區圖本來就畫剛易手）；乙 區圖名字框旁一枚「克」（拿下）或「守」（守住）字印；丙 抽屜收著那一行多一條。
三個做法的卡都一樣（第 2 段底下一段：戰書／攻城／攻城戰果）。上一版（前一位開發）B 乙是地圖頂上一條橫幅、C 乙是那一處一圈閃圈
（跟區圖「你在這裡」的朱圈撞），這一版換掉。用法：python mock5.py <app.js>"""
import sys
from pathlib import Path

app = Path(sys.argv[1])
text = app.read_bytes().decode("utf-8")
crlf = "\r\n" in text
text = text.replace("\r\n", "\n")


def sub(old, new):
    global text
    assert text.count(old) == 1, old[:80]
    text = text.replace(old, new)


HELPERS = r'''
  // ── 第 5 批對比圖的原型（只在 scratchpad 那一份；網址 ?mock=A甲 這種）──
  const MOCK = (typeof location !== "undefined" && location.search && new URLSearchParams(location.search).get("mock")) || "";
  const mockOn = (state, v) => MOCK === state + v;
  const mockRows = () => (S.main && S.main.conquest && S.main.conquest.today) || [];
  const mockState = (row) => (row.status === "planned" || row.status === "waiting" ? "A" : row.status === "open" ? "B" : row.status === "done" ? "C" : "");
  const mockRow = (state) => mockRows().find((r) => mockState(r) === state);
  const MK_RED = "#A8322A";
  function mockCard(id) {
    const row = mockRows().find((r) => r.loc === id), st = row ? mockState(row) : "";
    if (!st || !MOCK.startsWith(st)) return "";
    const att = esc((row.attackers || []).join("、"));
    let head = "", body = "", btn = "";
    if (st === "A") { head = "戰書"; body = `${att}約戰 <b>${esc(row.time)}</b>；開打前 30 分鐘在這一帶集結，人要在這一區才加得進去。這一塊的進度凍結到打完。`; }
    if (st === "B") {
      // 鈕照看的人站哪一邊寫：攻方「去加入攻城」、守方「去守城」、其他人「去助陣」（散人、豪強可以臨時投效或助守）
      const blk = conquestBlock(id), me = S.mapState && S.mapState.faction, atk = (blk && blk.frozen && blk.frozen.attackers) || [];
      const join = atk.includes(me) ? "去加入攻城" : blk && blk.holder && blk.holder === me ? "去守城" : "去助陣";
      head = "攻城"; body = `${att}攻${esc(row.place)}：<b>${esc(row.status_text)}</b>（${esc(row.time)} 開打）。這一區的人加得進去。`;
      btn = `<button type="button" class="main" data-act="tab" data-tab="jianghu">${join}<small>回江湖頁</small></button>`;
    }
    if (st === "C") { head = "攻城戰果"; body = `${esc(row.time)} 那一仗：<b>${esc(row.status_text)}</b>（大勝）。`; btn = '<button type="button" data-act="tab" data-tab="news">看戰報<small>見聞</small></button>'; }
    return `<div class="m-sec m-flip"><h4>${head}</h4><div style="font-size:13px">${body}</div>${btn ? `<div class="m-acts" style="margin-top:6px">${btn}</div>` : ""}</div>`;
  }
  // 抽屜收著那一行的上面多一條（A丙、B丙、C丙）；點了選那一處（同找地點挑了一處）
  function mockLine() {
    const st = MOCK.endsWith("丙") ? MOCK[0] : "";
    const row = st && mockRow(st);
    if (!row) return "";
    const att = esc((row.attackers || []).join("、"));
    const tag = `<b style="display:inline-block;background:${MK_RED};color:#fff;border-radius:5px;padding:0 5px;font-size:11.5px;margin-right:6px;letter-spacing:1px">${{ A: "戰書", B: "攻城", C: "戰果" }[st]}</b>`;
    const words = st === "A" ? `${esc(row.time)}・${att}攻${esc(row.place)}` : st === "B" ? `${esc(row.place)}・${esc(row.status_text)}` : `${esc(row.place)}：${esc(row.status_text)}`;
    return `<div class="m-wline"><button type="button" class="m-mini" data-act="map-pick" data-id="${esc(row.loc)}"><span>${tag}${words}</span><i>›</i></button></div>`;
  }
'''

# 1. 幫手放在 conquestBlock 前面
sub("  const conquestBlock = (id) =>", HELPERS + "  const conquestBlock = (id) =>")
# 2. 卡：第 2 段底下接那一段；凍結那一行在原型裡不另寫
sub("      <div class=\"m-line\"${lineInk}>${esc(placeLine(st, id))}</div>\n      ${flipSection(id)}",
    "      <div class=\"m-line\"${lineInk}>${esc(placeLine(st, id))}</div>\n      ${mockCard(id)}${flipSection(id)}")
sub("const frozen = blk.frozen ? FROZEN_WORD", "const frozen = blk.frozen && !MOCK ? FROZEN_WORD")
# 3. 抽屜收著那一行（天下圖、區圖）
sub("if (S.mapDrawer === \"min\" && !deskMap()) return `<div class=\"m-wline\">",
    "if (S.mapDrawer === \"min\" && !deskMap()) return `${mockLine()}<div class=\"m-wline\">")
sub("    return `<div class=\"m-wline\"><button type=\"button\" class=\"m-mini\" data-act=\"map-open\" aria-label=\"攤開抽屜\"><span>${text}</span>${mine ? \"<i>▴</i>\" : \"\"}</button></div>`;",
    "    return `${mockLine()}<div class=\"m-wline\"><button type=\"button\" class=\"m-mini\" data-act=\"map-open\" aria-label=\"攤開抽屜\"><span>${text}</span>${mine ? \"<i>▴</i>\" : \"\"}</button></div>`;")
sub("return { min: 54, peek:", "return { min: mockLine() ? 90 : 54, peek:")
# 4.（上一版的 B 乙「地圖頂上一條」拿掉）
# 5. 天下圖：A乙 朱紅虛線框、B甲 激戰紅光、B乙 朱紅實線框
sub("    // 點一區：整區一塊透明的點擊區\n",
    "    for (const r of live ? mockRows() : []) {\n"
    "      const s = mockState(r), c = wd.cells.find((x) => x.id === r.loc);\n"
    "      if (!c) continue;\n"
    "      if (s === \"A\" && mockOn(\"A\", \"乙\")) out.push(`<path d=\"${c.d}\" fill=\"none\" stroke=\"${MK_RED}\" stroke-width=\"${f1(2.6 * k)}\" stroke-dasharray=\"${f1(6 * k)} ${f1(3.5 * k)}\" stroke-linejoin=\"round\" clip-path=\"url(#wc-${esc(c.region)})\" pointer-events=\"none\"/>`);\n"
    "      if (s === \"B\" && mockOn(\"B\", \"甲\")) out.push(`<path class=\"w-melee\" d=\"${c.d}\" fill=\"${FRONT_RED}\" fill-opacity=\".16\" stroke=\"${FRONT_RED}\" stroke-width=\"${f1(3.2 * k)}\" stroke-linejoin=\"round\" clip-path=\"url(#wc-${esc(c.region)})\" pointer-events=\"none\"/>`);\n"
    "      if (s === \"B\" && mockOn(\"B\", \"乙\")) out.push(`<path d=\"${c.d}\" fill=\"none\" stroke=\"${MK_RED}\" stroke-width=\"${f1(3.4 * k)}\" stroke-linejoin=\"round\" clip-path=\"url(#wc-${esc(c.region)})\" pointer-events=\"none\"/>`);\n"
    "    }\n"
    "    // 點一區：整區一塊透明的點擊區\n")
# 6. 區圖：A乙、B乙 名字框旁一枚「戰」字印（B乙一閃）、C乙「克」（拿下）／「守」（守住）；B甲 名字框一圈紅閃
sub("      const base0 = y + fh + (R_INS_GAP + L.insPx * 0.9) * k;",
    "      const mk = mockRows().find((r) => r.loc === L.id), ms = mk ? mockState(mk) : \"\";\n"
    "      if (mk && ms && mockOn(ms, \"乙\")) {\n"
    "        const word = ms === \"C\" ? (/拿下/.test(mk.status_text) ? \"克\" : \"守\") : \"戰\";\n"
    "        const sx = x + fw + ((L.rich ? R_SEAL_GAP + R_SEAL : 0) + R_SEAL_GAP) * k, sy = y + ((L.fh - R_SEAL) / 2) * k;\n"
    "        parts.push(`<g${ms === \"B\" ? ' class=\"w-melee\"' : \"\"}><rect x=\"${f1(sx)}\" y=\"${f1(sy)}\" width=\"${f1(R_SEAL * k)}\" height=\"${f1(R_SEAL * k)}\" rx=\"${f1(2 * k)}\" fill=\"#FFF8EC\" stroke=\"${MK_RED}\" stroke-width=\"${f1(1.5 * k)}\"/><text x=\"${f1(sx + (R_SEAL / 2) * k)}\" y=\"${f1(sy + 11.3 * k)}\" font-size=\"${f1(11 * k)}\" text-anchor=\"middle\" font-weight=\"700\" fill=\"${MK_RED}\">${word}</text></g>`);\n"
    "      }\n"
    "      if (mk && ms === \"B\" && mockOn(\"B\", \"甲\")) parts.push(`<rect class=\"w-melee\" x=\"${f1(x - 3 * k)}\" y=\"${f1(y - 3 * k)}\" width=\"${f1(fw + 6 * k)}\" height=\"${f1(fh + 6 * k)}\" rx=\"${f1(3 * k)}\" fill=\"${FRONT_RED}\" fill-opacity=\".12\" stroke=\"${FRONT_RED}\" stroke-width=\"${f1(2.4 * k)}\"/>`);\n"
    "      const base0 = y + fh + (R_INS_GAP + L.insPx * 0.9) * k;")

out = text.replace("\n", "\r\n") if crlf else text
app.write_bytes(out.encode("utf-8"))
print("ok", crlf)

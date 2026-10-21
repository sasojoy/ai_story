# 輿圖簡化的示意（暫時改法，不提交）：web/app.js 加一個網址參數 ?mapv=甲|乙|丙，三版都在同一份程式裡。
# 照 CRLF 規矩：讀進來先把 \r\n 換成 \n、每一處 assert、寫回去換回 \r\n。拍完 git checkout -- web/app.js 還原。
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(r"C:\Ray\專案\天下大勢\.claude\worktrees\serene-galileo-46e759")
path = ROOT / "web" / "app.js"
text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
assert "const MAPV" not in text, "已經改過了"

EDITS = [
    # 1. 變數：哪一版、金星的顏色
    (
        '  const sideName = (k) => (k ? MAP_SIDES[k].name : "無人控制");\n',
        '  const MAPV = (typeof location !== "undefined" && location.search && new URLSearchParams(location.search).get("mapv")) || ""; // 輿圖簡化示意（暫時）：甲／乙／丙\n'
        '  const PRIME_GOLD = "#C9962B"; // 示意：高級資源領地的金星\n'
        '  const sideName = (k) => (k ? MAP_SIDES[k].name : "無人控制");\n',
    ),
    # 2. 濾鏡那一排拿掉
    (
        "  function chipsHtml() {\n    const on = new Set(S.mapLayers);\n",
        '  function chipsHtml() {\n    if (MAPV) return "";\n    const on = new Set(S.mapLayers);\n',
    ),
    # 3. 地名底下的小牌子全部拿掉
    (
        "    const p = st.places[id], out = [];\n    if (!p || (id === st.here && !st.journey)) return out;\n",
        "    const p = st.places[id], out = [];\n    if (MAPV || !p || (id === st.here && !st.journey)) return out;\n",
    ),
    # 4. 意境濾鏡不算、勢力一定開
    (
        "    const k = o.k, far = o.far, hit = Math.round(2 * (hitRadius(1 / k) - 16)), ins = insightOn(base, o.layers), on = !!st.territory && o.layers.has(\"control\") && !ins;\n",
        "    const k = o.k, far = o.far, hit = Math.round(2 * (hitRadius(1 / k) - 16)), ins = !MAPV && insightOn(base, o.layers), on = !!st.territory && (!!MAPV || o.layers.has(\"control\")) && !ins;\n",
    ),
    # 5. 乙：暈色放大、連成一片
    (
        '    const out = [`<defs>${MAP_SIDE_ORDER.map((s) => `<radialGradient id="mk-halo-${s}"><stop offset="0" stop-color="${MAP_SIDES[s].soft}" stop-opacity=".7"/><stop offset=".55" stop-color="${MAP_SIDES[s].soft}" stop-opacity=".35"/><stop offset="1" stop-color="${MAP_SIDES[s].soft}" stop-opacity="0"/></radialGradient>`).join("")}</defs>`];\n'
        "    if (on) {\n"
        '      for (const p of base.places) if (ctrl[p.id]) out.push(`<circle cx="${p.x}" cy="${p.y}" r="80" fill="url(#mk-halo-${ctrl[p.id]})" pointer-events="none"/>`);\n'
        "      for (const [a, b] of base.edges) { // 前線",
        '    const wide = MAPV === "乙";\n'
        '    const out = [`<defs>${MAP_SIDE_ORDER.map((s) => wide\n'
        '      ? `<radialGradient id="mk-halo-${s}"><stop offset="0" stop-color="${MAP_SIDES[s].soft}" stop-opacity=".6"/><stop offset=".72" stop-color="${MAP_SIDES[s].soft}" stop-opacity=".5"/><stop offset="1" stop-color="${MAP_SIDES[s].soft}" stop-opacity="0"/></radialGradient>`\n'
        '      : `<radialGradient id="mk-halo-${s}"><stop offset="0" stop-color="${MAP_SIDES[s].soft}" stop-opacity=".7"/><stop offset=".55" stop-color="${MAP_SIDES[s].soft}" stop-opacity=".35"/><stop offset="1" stop-color="${MAP_SIDES[s].soft}" stop-opacity="0"/></radialGradient>`).join("")}</defs>`];\n'
        "    if (on) {\n"
        '      for (const p of base.places) if (ctrl[p.id]) out.push(`<circle cx="${p.x}" cy="${p.y}" r="${wide ? 150 : 80}" fill="url(#mk-halo-${ctrl[p.id]})" pointer-events="none"/>`);\n'
        "      if (!MAPV) for (const [a, b] of base.edges) { // 前線",
    ),
    # 6. 中立地：示意版不畫虛線，高級資源領地（開季中立的）另畫金星；沒人佔的灰圈
    (
        '      const nz = on && !c && !!st.places[p.id] && st.places[p.id].kind === "neutral";\n'
        '      const col = ink ? ink.c : c ? MAP_SIDES[c].color : nz ? NEUTRAL_INK.ring : "#7A6A55";\n',
        '      const prime = !!MAPV && on && !!st.places[p.id] && st.places[p.id].kind === "neutral"; // 示意：高級資源領地（開季中立），不論誰佔著\n'
        '      const nz = !MAPV && on && !c && !!st.places[p.id] && st.places[p.id].kind === "neutral";\n'
        '      const col = ink ? ink.c : c ? MAP_SIDES[c].color : nz || prime ? NEUTRAL_INK.ring : "#7A6A55";\n',
    ),
    # 7. 看大局：高級資源領地的小點金邊
    (
        '        out.push(`<circle cx="${p.x}" cy="${p.y}" r="${f1(r)}" fill="${ink ? ink.c : c ? MAP_SIDES[c].color : nz ? NEUTRAL_INK.far : "#A99C84"}" stroke="${nz ? NEUTRAL_INK.ring : MAP_HALO}" stroke-width="${f1(1.5 * k)}"${dash}/></g>`);\n',
        '        out.push(`<circle cx="${p.x}" cy="${p.y}" r="${f1(r)}" fill="${ink ? ink.c : c ? MAP_SIDES[c].color : nz || prime ? NEUTRAL_INK.far : "#A99C84"}" stroke="${nz ? NEUTRAL_INK.ring : prime ? PRIME_GOLD : MAP_HALO}" stroke-width="${f1((prime ? 2.2 : 1.5) * k)}"${dash}/></g>`);\n',
    ),
    # 8. 金星與 ⚔
    (
        "      // ⚔：你此刻能出陣攻的地方（疊層的 armed，跟舊輿圖同一個判斷 FB-251），圓盤左上一個紅色小圓章；散人、豪強一處都沒有（企劃者 10/15 從對比圖選乙）\n"
        "      if (st.places[p.id] && st.places[p.id].armed) {\n",
        '      if (prime) out.push(`<text x="${f1(p.x + r + 1 * k)}" y="${f1(p.y - r - 1 * k)}" font-size="${f1(14 * k)}" text-anchor="middle" fill="${PRIME_GOLD}" stroke="${MAP_HALO}" stroke-width="${f1(2.6 * k)}" paint-order="stroke" pointer-events="none">★</text>`); // 示意：高級資源領地\n'
        "      // ⚔：你此刻能出陣攻的地方（疊層的 armed，跟舊輿圖同一個判斷 FB-251），圓盤左上一個紅色小圓章；散人、豪強一處都沒有（企劃者 10/15 從對比圖選乙）\n"
        "      if (!MAPV && st.places[p.id] && st.places[p.id].armed) {\n",
    ),
    # 9. 丙：地名底下用意境的顏色寫這裡悟得到的
    (
        "      let bx = p.x + r + 5 * k;\n      for (const [t, color] of mapBadges(st, p.id, o.layers)) {\n",
        '      if (MAPV === "丙") { // 示意：每個地點名字底下，這裡悟得到的意境（照意境的顏色寫字，最濃的在前）\n'
        "        let ix = p.x + r + 6 * k;\n"
        "        const ids = [...(p.insights || [])].sort((a, b2) => (b2 === p.strong) - (a === p.strong)).slice(0, 3);\n"
        "        for (const id of ids) {\n"
        "          const ik = insightInk(base, id);\n"
        "          if (!ik) continue;\n"
        '          out.push(`<text x="${f1(ix)}" y="${f1(p.y + 19.5 * k)}" font-size="${f1(12 * k)}" font-weight="700" fill="${ik.c}" stroke="${MAP_HALO}" stroke-width="${f1(3 * k)}" paint-order="stroke" pointer-events="none" style="font-family:serif">${esc(ik.name)}</text>`);\n'
        "          ix += 14.5 * k;\n"
        "        }\n"
        "      }\n"
        "      let bx = p.x + r + 5 * k;\n      for (const [t, color] of mapBadges(st, p.id, o.layers)) {\n",
    ),
    # 10. 右上角的意境鈕拿掉
    (
        "    ${insightButton()}\n  </div>`;\n",
        '    ${MAPV ? "" : insightButton()}\n  </div>`;\n',
    ),
    # 11. 抽屜：總覽換成「你在這裡」那張卡
    (
        '    if (drawerNow() === "min" && !deskMap()) return miniHtml(base, st);\n    return overviewHtml(base, st);\n',
        '    if (drawerNow() === "min" && !deskMap()) return miniHtml(base, st);\n'
        "    if (MAPV && !st.journey && st.places[st.here]) return placeHtml(base, st, st.here); // 示意：一打開就是你站的那一處\n"
        "    return overviewHtml(base, st);\n",
    ),
    # 12. 地點那張卡：第一行是誰的領地、基礎還是高級；再來此地能悟、此地的對手；然後動作
    (
        "    const tone = (word) => TONE_COLOR[ODDS_TONE_WEB[word] || \"ok\"];\n    return `<div class=\"m-h1\">",
        "    const tone = (word) => TONE_COLOR[ODDS_TONE_WEB[word] || \"ok\"];\n"
        "    if (MAPV) { // 示意（字待 joy 潤）\n"
        '      const prime = p.kind === "neutral", holder = p.control ? MAP_SIDES[p.control] : null;\n'
        '      const what = p.kind === "base" ? `${holder ? holder.name : ""}大本營`\n'
        '        : prime ? (holder ? `${holder.name}佔下的高級資源領地` : "中立・高級資源領地，還沒有人佔")\n'
        '        : p.kind === "line" ? `${holder ? holder.name + "的" : ""}基礎資源領地`\n'
        '        : p.kind === "fixed" ? `${holder ? holder.name + "・" : ""}照大事易手` : holder ? `${holder.name}的地盤` : "不在戰線上";\n'
        '      const foes = p.squads.length ? p.squads.map((q) => `${esc(q.name)} <span style="color:${tone(q.odds)}">${esc(q.odds)}</span>`).join("、") : "沒有對手";\n'
        '      const dist = here ? "" : p.minutes === null ? "走不到" : `步行 ${Number(p.minutes)} 分`;\n'
        '      return `<div class="m-h1">${ctrlSeal(p.control)}<span class="nm">${esc(b.name)}${here ? "（你）" : ""}</span><span class="meta">${prime ? `<span style="color:${PRIME_GOLD};font-weight:700">★高級</span> ` : ""}${dist}</span><button type="button" class="m-x" data-act="map-back" aria-label="收起">✕</button></div>\n'
        '      <div class="m-sub" style="margin:-4px 0 8px;font-size:13.5px"><b style="color:${holder ? holder.color : "inherit"}">${esc(what)}</b></div>\n'
        "      ${insightRow(base, b)}\n"
        '      <div class="m-sec" style="margin-top:0"><h4>此地的對手</h4>${foes}${p.people.length ? `<div class="m-sub">人物：${p.people.map(esc).join("、")}</div>` : ""}</div>\n'
        '      <div class="m-acts">${acts}</div>\n'
        '      ${p.order || p.bounty ? `<div class="m-sec"><h4>軍令與懸賞</h4>${p.order ? `軍令「${esc(p.order)}」在這裡記功` : ""}${p.order && p.bounty ? "；" : ""}${p.bounty ? `懸賞「${esc(p.bounty)}」在這裡交差` : ""}</div>` : ""}\n'
        '      ${st.territory && (strip || flips) ? `<div class="m-sec"><h4>這一季誰佔過</h4>${strip}${flips ? `<div class="m-sub">易手：${flips}</div>` : ""}</div>` : ""}\n'
        "      ${terrainArtsRow(b)}\n"
        '      ${p.services.length ? `<div class="m-sec"><h4>此地</h4>${p.services.map(esc).join("・")}</div>` : ""}\n'
        '      ${p.goal || p.news ? `<div class="m-sec"><h4>劇情</h4>${p.goal ? "★ 這一幕主線的目標　" : ""}${p.news ? "✦ 最近有大事與傳聞" : ""}</div>` : ""}`;\n'
        "    }\n"
        "    return `<div class=\"m-h1\">",
    ),
]

for i, (old, new) in enumerate(EDITS, 1):
    assert text.count(old) == 1, f"第 {i} 處找不到或不只一處（{text.count(old)}）"
    text = text.replace(old, new)

path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
print(f"改好 {len(EDITS)} 處：{path}")

/* 天下大勢的網頁前端：煉製與自創（功能包 tianxia/features/craft/，開發規範手冊 3.7、G9）。
 *
 * 煉製頁（pageCraft）：太極火爐與開爐、挑東西的抽屜、自創五步與擺式（火柴人 figBody）、秘方與口訣書（bookHtml、secretPop）的畫法。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；/ 的 script 標籤由伺服器照 FEATURES 生成，這支排在 admin.js 之後、app.js 前面
 * （段裡有兩個頂層監聽跟著走：window 的 scroll、document 的 pointer；排 admin.js 之後，監聽的先後照舊）。
 * 全部拆包第 64 批從 app.js 逐行切出來（計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第64批.md）。點擊、change 用 registerClicks、registerChanges 登記在這支檔；renderPage 的 fixedKiln 照舊在 app.js（殼）。
 */
"use strict";

  // ── 太極火爐（煉製頁）──
  // 每次重畫都是新的 SVG，所以轉動用負的 animation-delay 接上時鐘，重畫不會讓圖案跳回原位
  const wpt = (r, deg) => { const a = (deg - 90) * Math.PI / 180; return [+(r * Math.cos(a)).toFixed(2), +(r * Math.sin(a)).toFixed(2)]; };
  const spinAt = (secs) => `animation-delay:-${((performance.now() / 1000) % secs).toFixed(2)}s`;
  // 煉製頁的太極火爐（企劃者 2026-10-04）。太極在爐裡慢慢轉，外圈是一圈火舌；左右兩格放進去的是一門武學與一個意境
  // （或兩門武學，或兩個意境），點有東西的那一格拿出來，點爐身開爐。開爐後等結果的這段時間整座爐子晃動（見 forge()）。
  // slots 兩格各是 {name, sub, rank}（名字、第二行小字、品階 1~3）或沒放（null）
  function furnaceHub(slots, ready) {
    const r = 54;
    const flames = Array.from({ length: 16 }, (_, k) => {
      const a = k * 22.5, [x0, y0] = wpt(r + 3, a - 7), [x1, y1] = wpt(r + 10, a), [x2, y2] = wpt(r + 3, a + 7);
      return `<path d="M${x0},${y0} Q${x1},${y1} ${x2},${y2}" style="animation-delay:-${((performance.now() / 1000 + (k % 4) * 0.23) % 1.8).toFixed(2)}s"/>`; // 照同一個鐘起跳（同 spinAt）：重畫時火舌不從頭竄一次
    }).join("");
    const slot = (m, i) => {
      const x = i ? 26 : -26;
      // 格子只有 46 寬：名字超過四個字（新取的武學名可到六個字）就把字距壓進格子裡，不然會溢出格外蓋到另一格
      const fit = m && [...m.name].length > 4 ? ' textLength="42" lengthAdjust="spacingAndGlyphs"' : "";
      const locked = m && isLocked(S.forgeSel[i]);
      // 格子外角一顆小鎖（pot-lock）：鎖著的那一樣開爐成了也留在爐裡
      const pin = m ? `<g class="w-pin${locked ? " on" : ""}" data-act="pot-lock" data-i="${i}" role="button" aria-label="${locked ? "解開" : "鎖住"}${esc(m.name)}" aria-pressed="${locked}"><circle cx="${i ? x + 22 : x - 22}" cy="-16" r="6.5"/><text x="${i ? x + 22 : x - 22}" y="-13.6" class="w-pin-t">鎖</text></g>` : "";
      return m
        ? `<g class="w-slot full r${m.rank}${S.potFlash === i ? " flash" : ""}${locked ? " locked" : ""}" data-act="unslot" data-i="${i}" role="button" aria-label="拿出${esc(m.name)}">
            <rect x="${x - 23}" y="-14" width="46" height="28" rx="7"/><text x="${x}" y="-3" class="w-slot-name"${fit}>${esc(m.name)}</text><text x="${x}" y="8" class="w-slot-sub">${esc(m.sub)}</text></g>${pin}`
        : `<g class="w-slot" data-act="pot-open"${potGlow()} role="button" aria-label="放一樣進爐"><rect x="${x - 23}" y="-14" width="46" height="28" rx="7"/><text x="${x}" y="0" class="w-slot-sub">放入</text></g>`;
    };
    return `<g class="w-hub w-furnace${ready ? " ready" : ""}" data-act="forge-hub" role="button" aria-label="太極火爐，開爐">
      <g class="w-shake">
        <g class="w-flames${ready ? " hot" : ""}">${flames}</g>
        <circle r="${r + 3}" class="w-hub-rim"/>
        <g class="w-spin w-taichi${ready ? " hot" : ""}" style="${spinAt(ready ? 3 : 28)}">
          <circle r="${r}" class="w-yang"/>
          <path d="M0,${-r} A${r},${r} 0 0 1 0,${r} A${r / 2},${r / 2} 0 0 1 0,0 A${r / 2},${r / 2} 0 0 0 0,${-r} Z" class="w-yin"/>
          <circle cy="${-r / 2}" r="${r / 7}" class="w-yang"/><circle cy="${r / 2}" r="${r / 7}" class="w-yin"/>
          <circle r="${r}" class="w-seam"/>
        </g>
        ${slot(slots[0], 0)}${slot(slots[1], 1)}
        <text y="${r - 12}" class="w-furnace-lab">${ready ? "點爐開火" : "太極火爐"}</text>
      </g></g>`;
  }
  // 煉製頁的太極火爐自己一張圖：外面不圍東西，挑武學與意境在下面的清單
  function furnaceSvg(slots, ready) {
    return `<div class="furnace-wrap"><svg class="wheel furnace" viewBox="-74 -74 148 148" role="group" aria-label="太極火爐">
      <defs><radialGradient id="wg-disk"><stop offset="0" style="stop-color:var(--disk-2)"/><stop offset="1" style="stop-color:var(--disk)"/></radialGradient></defs>
      <circle r="72" fill="url(#wg-disk)"/><circle r="70" class="w-rim"/>${furnaceHub(slots, ready)}</svg></div>`;
  }

  // 火柴人：九個角度（create.POSE_KEYS，度；0 朝下、正的往右），骨架跟 tianxia/create.py 同一組數字（伺服器照同一個幾何讀偏向）
  const RIG = { CX: 110, SY: 96, HIPY: 146, UA: 27, FA: 25, TH: 31, SH: 29 };
  const POSE_KEYS = ["t", "lS", "lE", "rS", "rE", "lH", "lK", "rH", "rK"];
  const WEAPON_LEN = { 劍: 40, 刀: 32, 槍: 70, 棍: 60 };
  function rigJoints(P) {
    const d2r = (d) => (d * Math.PI) / 180, g = (k) => Number(P && P[k]) || 0;
    const { CX, SY, HIPY, UA, FA, TH, SH } = RIG, t = d2r(g("t"));
    const chain = (x, y, a1, l1, a2, l2) => { const e = { x: x + Math.sin(a1) * l1, y: y + Math.cos(a1) * l1 }; return [e, { x: e.x + Math.sin(a1 + a2) * l2, y: e.y + Math.cos(a1 + a2) * l2 }]; };
    const J = { neck: { x: CX - Math.sin(t) * 10, y: SY - Math.cos(t) * 10 }, head: { x: CX - Math.sin(t) * 24, y: SY - Math.cos(t) * 24 },
      lSh: { x: CX - 9, y: SY }, rSh: { x: CX + 9, y: SY }, lHip: { x: CX - 7, y: HIPY }, rHip: { x: CX + 7, y: HIPY }, root: { x: CX, y: SY } };
    [J.lEl, J.lHa] = chain(J.lSh.x, J.lSh.y, d2r(g("lS")) + t, UA, d2r(g("lE")), FA);
    [J.rEl, J.rHa] = chain(J.rSh.x, J.rSh.y, d2r(g("rS")) + t, UA, d2r(g("rE")), FA);
    [J.lKn, J.lFt] = chain(J.lHip.x, J.lHip.y, d2r(g("lH")), TH, d2r(g("lK")), SH);
    [J.rKn, J.rFt] = chain(J.rHip.x, J.rHip.y, d2r(g("rH")), TH, d2r(g("rK")), SH);
    J.hand = d2r(g("rS")) + t + d2r(g("rE"));
    return J;
  }
  // 姿勢讀出的偏向（create.pose_scores 的同一套規則；伺服器在擺定那一下再讀一次，以伺服器為準）
  function poseRead(P) {
    const J = rigJoints(P), { CX, SY, HIPY, UA, FA, TH, SH } = RIG;
    const reach = Math.max(Math.abs(J.rHa.x - CX), Math.abs(J.lHa.x - CX)) / (UA + FA);
    const high = Math.max(SY - J.rHa.y, SY - J.lHa.y) / (UA + FA);
    const tucked = Math.hypot(J.rHa.x - CX, J.rHa.y - (SY + 20)) < 30 && Math.hypot(J.lHa.x - CX, J.lHa.y - (SY + 20)) < 30;
    const spread = Math.abs(J.lFt.x - J.rFt.x) / (TH + SH), lift = Math.min(J.lFt.y, J.rFt.y) < HIPY + TH * 1.3, lean = Number(P.t) || 0;
    const s = { 剛: 0, 柔: 0, 快: 0, 慢: 0, 虛: 0, 實: 0 };
    s.剛 += Math.max(0, reach - 0.95) * 8 + Math.max(0, high - 0.15) * 2;
    if (tucked) s.柔 += 1.6;
    s.實 += Math.max(0, spread - 0.9) * 3; s.慢 += Math.max(0, spread - 1.1) * 2;
    if (lift) { s.虛 += 2; s.快 += 1; }
    if (lean < -12) s.快 += (-lean - 12) / 15;
    if (lean > 10) s.慢 += (lean - 10) / 15;
    const order = ["陰", "陽", "剛", "柔", "快", "慢", "虛", "實"];
    const top = Object.entries(s).sort((p, q) => q[1] - p[1] || order.indexOf(p[0]) - order.indexOf(q[0]));
    const attrs = top[0][1] < 0.35 ? [] : [top[0][0], ...(top[1][1] > 0.35 && top[1][1] > top[0][1] * 0.6 ? [top[1][0]] : [])];
    const why = [];
    if (reach > 0.95) why.push("手伸得遠"); if (high > 0.15) why.push("手抬得高"); if (tucked) why.push("雙手收在胸前");
    if (spread > 0.9) why.push("馬步寬"); if (lift) why.push("單腳提起"); if (lean < -12) why.push("身子前傾"); if (lean > 10) why.push("身子後仰");
    // 勢（create.stance_of 的同一套：提腿先看，再看收手或寬馬步，再看手伸遠或前傾）
    const stance = lift ? "變勢" : tucked || (spread > 1.1 && reach < 0.95) ? "守勢" : reach >= 1.0 || lean <= -10 ? "攻勢" : "起勢";
    return { attrs, why, stance };
  }
  const poseReadText = (attrs) => (attrs.length ? `此式偏${attrs[0]}${attrs[1] ? `、兼${attrs[1]}` : ""}` : "此式平正，不偏一路"); // 待 joy 潤
  // 骨頭與兵器（拖曳的大圖與功法卡的小圖共用）；joints 為真時多畫可拖的關節點
  function figBody(P, weapon, joints) {
    const J = rigJoints(P || {}), f = (v) => v.toFixed(1);
    const L = (p, q, cls) => `<line class="${cls || "bone"}" x1="${f(p.x)}" y1="${f(p.y)}" x2="${f(q.x)}" y2="${f(q.y)}"/>`;
    let arm = "";
    const len = WEAPON_LEN[weapon];
    if (len) {
      const tip = { x: J.rHa.x + Math.sin(J.hand) * len, y: J.rHa.y + Math.cos(J.hand) * len };
      const back = weapon === "棍" || weapon === "槍" ? { x: J.rHa.x - Math.sin(J.hand) * 14, y: J.rHa.y - Math.cos(J.hand) * 14 } : J.rHa;
      arm = L(back, tip, `blade${weapon === "刀" || weapon === "棍" ? " thick" : ""}`);
    } else if (weapon === "弓弩") {
      const n = { x: Math.cos(J.hand), y: -Math.sin(J.hand) }, h = J.rHa;
      arm = `<path class="blade bow" d="M${f(h.x + n.x * 18)} ${f(h.y + n.y * 18)} Q${f(h.x + Math.sin(J.hand) * 14)} ${f(h.y + Math.cos(J.hand) * 14)} ${f(h.x - n.x * 18)} ${f(h.y - n.y * 18)}"/>`;
    }
    const bones = L(J.neck, { x: RIG.CX, y: RIG.HIPY }) + L(J.lSh, J.lEl) + L(J.lEl, J.lHa) + L(J.rSh, J.rEl) + L(J.rEl, J.rHa)
      + L(J.lHip, J.lKn) + L(J.lKn, J.lFt) + L(J.rHip, J.rKn) + L(J.rKn, J.rFt) + L(J.lSh, J.rSh);
    const head = `<circle class="bone" cx="${f(J.head.x)}" cy="${f(J.head.y)}" r="13"/>`;
    const dots = joints ? ["head", "lEl", "lHa", "rEl", "rHa", "lKn", "lFt", "rKn", "rFt"].map((k) =>
      `<circle class="jt" data-j="${k}" cx="${f(J[k].x)}" cy="${f(J[k].y)}" r="${k === "head" ? 7 : 8}"/><circle class="jhit" data-j="${k}" cx="${f(J[k].x)}" cy="${f(J[k].y)}" r="18"/>`).join("") : "";
    return arm + bones + head + dots;
  }

  // 爐裡放的東西 → 送給伺服器的 body：只有意境（武學不再拿來合，Joy 2026-10-21）
  function forgeBody() {
    return { insights: S.forgeSel.filter((p) => p.type === "ins").map((p) => p.id) };
  }
  // 兩個意境才放得滿（不同的合併、同一種的兩份揣摩）
  function forgeReady() {
    return forgeBody().insights.length === 2;
  }
  // 鎖在爐裡（Joy 2026-10-19「弄一個鎖定的功能，尤其獲得新意境時會想要試他的所有組合」）：一次鎖一樣，開爐成了它留在爐裡、
  // 只清另一格，接著再放一樣就能試下一個組合；拿出來、熔掉、合掉就解開
  const isLocked = (p) => !!(p && S.forgeLock && S.forgeLock.type === p.type && S.forgeLock.id === p.id);
  function toggleLock(i) {
    const p = S.forgeSel[i];
    if (!p) return;
    S.forgeLock = isLocked(p) ? null : { type: p.type, id: p.id };
    renderPage();
  }
  let potFlashTimer = 0;
  function pick(type, id) {
    if (S.busy) return; // 開爐等結果的時候（首次取名要等模型）爐子不動
    if (S.forgeSel.length >= 2) { toast("爐裡已經放滿了，點上面的拿出來再換。"); return; }
    if (type !== "ins") return; // 爐裡只合意境
    const no = pickMark(type, id);
    if (no) { toast(no.why); return; } // 跟爐裡那一樣合不了（伺服器照開爐時的判斷算好的）：說為什麼，不放進去
    S.forgeSel.push({ type, id });
    if (forgeReady()) S.craftPick = false; // 兩格放滿：抽屜收起，看預覽
    S.potFlash = S.forgeSel.findIndex((p) => p.type === type && p.id === id); // 剛放進去的那一格閃一下（固定列上看得到，不必捲回爐子）
    renderPage();
    clearTimeout(potFlashTimer); // 說明那一行回來時會再畫一次：閃的那一格撐到動畫跑完才收
    potFlashTimer = setTimeout(() => { S.potFlash = null; }, 900);
    updateForgeLine();
  }

  // 爐裡只放了一樣時，這一樣能不能放進另一格：伺服器照開爐時同一套判斷算好的（/api/forge_line 的 picks，skillview.forge_picks）。
  // 合不了回 { short, why }，合得了或還沒算好回 null
  function pickMark(type, id) {
    const p = S.forgePicks;
    if (!p || S.forgeSel.length !== 1) return null;
    return (type === "ins" && p.insights[id]) || null;
  }
  // 煉製頁的清單篩選（企劃者 2026-10-10「武學數量很多的時候，很難選」）：種類（ART_FILTERS 那四顆）之外再加屬性、品質、排序，
  // 爐裡放了一樣時可以「只看合得了的」。都只記在這一頁（S.craftView），不存瀏覽器
  const CRAFT_SORTS = [["", "依品質"], ["attr", "依屬性"], ["name", "依名字"]];
  // 一次先列幾門，其餘按「再列」
  const CRAFT_PAGE = 12;
  function craftView() {
    S.craftView = S.craftView || { attr: "", quality: "", sort: "", okOnly: false, all: false };
    return S.craftView;
  }
  function craftFilterRow(x) {
    if (pro()) return "";
    const v = craftView();
    const attrs = [...new Set(x.insights.map((i) => i.attribute))].sort();
    const quals = [...new Set(x.insights.map((i) => i.look).filter(Boolean))].sort((a, b) => "凡佳珍神".indexOf(a) - "凡佳珍神".indexOf(b));  // 意境的品相（凡佳珍神，新手引導重做：不再寫底子的中品）
    const sel = (key, label, opts) => `<select class="input" data-act="craft-view" data-key="${key}" aria-label="${label}">${opts.map(([val, text]) =>
      `<option value="${esc(val)}"${v[key] === val ? " selected" : ""}>${esc(text)}</option>`).join("")}</select>`;
    const pot = S.forgeSel.length === 1 && S.forgePicks;
    return `<div class="craft-filter">
      ${sel("attr", "屬性", [["", "屬性"], ...attrs.map((a) => [a, `屬${a}`])])}
      ${sel("quality", "品相", [["", "品相"], ...quals.map((q) => [q, `${q}品`])])}
      ${sel("sort", "排序", CRAFT_SORTS)}
      ${pot ? `<button type="button" class="fchip${v.okOnly ? " on" : ""}" data-act="craft-ok" aria-pressed="${v.okOnly}">只看合得了的</button>` : ""}
    </div>`;
  }
  // 一顆功法：合不了的灰掉、底下寫兩三個字的原因（點了說整句）
  function craftChip(type, thing, sub, rank, extra = "", used = false) {
    const no = !used && pickMark(type, thing.id);
    return `<button class="chip r${rank}${no ? " no" : ""}${used ? " used" : ""}" data-act="pick" data-type="${type}"${used ? "" : extra} data-id="${esc(thing.id)}"${used ? " disabled" : ""}>
          <b>${esc(thing.name)}</b><small>${no ? `<i class="why">${esc(no.short)}</i>` : esc(sub)}</small></button>`;
  }
  // 太極爐一直看得到（Joy 2026-10-17「合成的時候也會因為要把畫面拉到下面看不到爐子的內容」，之後「那個太極爐變得很多餘」）：
  // 爐子本身就是開爐的地方，沒有另一條列。往下捲去挑東西、大爐子捲出畫面時，同一座爐縮成一條黏在狀態列底下（.kiln.compact，fixedKiln）：
  // 左右兩格（點了拿出來）、中間小太極就是開爐鈕，開不了爐的原因寫在底下一行。大爐子那一格的高度由 .kiln-wrap 撐著，縮起來頁面不跳。
  // 剛放進去的那一格大小兩座都閃一下（S.potFlash：第幾格）
  // 開不了爐的原因（說明那一行 ⚠ 後面那一句）：縮起來的爐子底下一行；說明回來時只換這一格（updateForgeLine）
  function kilnWarn() {
    if (S.forgePreview) return kilnPeek(S.forgePreview); // 兩格放好：縮起來的爐子底下帶著預覽，不用滑回上面看
    const warn = String(S.forgeLine || (S.menxia && S.menxia.forge_line) || "").replace(/<[^>]+>/g, " ").split("⚠")[1];
    return warn && warn.trim() ? `<p class="kiln-warn">⚠ ${esc(warn.replace(/\s+/g, " ").trim())}</p>` : "";
  }
  // 縮起來的爐子底下的預覽（Joy 2026-10-19「玩家要先往下滑滑滑選選選，然後還要重新滑到最上面看可能出現什麼」）：
  // 預覽卡濃縮成兩行——品級印、會合出什麼、屬性、境界、第幾成；功效與亮幾格、離下一品的提示；開不了爐的原因照舊一行。
  // 點了捲回上面看整張卡。資料同 previewCardHtml（S.forgePreview）
  // 爐火（招式與絕學稿案第五輪，Joy 2026-10-21「火候用文字加爐火圖」）：四段，火苗一到四簇、越旺越亮；不寫品級、不寫機率
  const FLAME = "M6 0C7 4 11 6 11 11a5 5 0 0 1-10 0C1 8 3 7 3 4c1 2 2 3 3 3C6 5 5 3 6 0Z";
  // after：緊接在火候字後面的一段（預覽卡的「真意 N%」，鐵匠鋪與合成流程 3.5），已經是畫好的標記
  function fireHtml(f, small, after = "") {
    if (!f) return "";
    const lv = Math.max(0, Math.min(3, f.level | 0));
    const flames = Array.from({ length: lv + 1 }, (_, k) => `<path d="${FLAME}" transform="translate(${k * 9},${k % 2 ? 2 : 0})"/>`).join("");
    return `<span class="fire f${lv}${small ? " small" : ""}"><svg viewBox="0 -1 ${12 + lv * 9} 18" aria-hidden="true">${flames}</svg><b>${esc(f.word)}</b>${after}${small ? "" : `<span>${esc(f.line)}</span>`}</span>`;
  }
  function kilnPeek(v) {
    const merge = v.kind === "合併";
    const badge = merge ? '<span class="qseal qi">意</span>' : v.quality ? seal(v.quality) : '<span class="qseal q1">？</span>';
    const head = [v.made, v.attribute ? `屬${v.attribute}` : "", merge ? v.depth : v.gen, v.level > 1 ? `第${v.level}成` : ""].filter(Boolean).map(esc).join("・");
    const tags = (v.traits || []).map((t) => `${esc(t.name)}${t.layers > 1 ? ` ×${t.layers}` : ""}`);
    const line2 = [tags.length ? `功效 ${tags.join("、")}` : "", v.slots, v.near].filter(Boolean).map(esc).join("・");
    return `<button type="button" class="kiln-peek" data-act="peek" aria-label="看整張預覽卡">${badge}<span><b>${head}</b>${line2 ? `<small>${line2}</small>` : ""}</span>${fireHtml(v.fire, true)}</button>
      ${v.problem ? `<p class="kiln-warn">⚠ ${esc(v.problem)}</p>` : ""}`;
  }
  function kilnHtml(slots, ready) {
    // 放了東西的格子右下角一顆小鎖（同大爐子的 pot-lock），鎖著的那一格金邊；兩顆鈕不能套在一起，所以包一層 .kiln-cell
    const cell = (m, i) => m
      ? `<div class="kiln-cell"><button class="kiln-slot full r${m.rank}${S.potFlash === i ? " flash" : ""}${isLocked(S.forgeSel[i]) ? " locked" : ""}" data-act="unslot" data-i="${i}" aria-label="拿出${esc(m.name)}"><b>${esc(m.name)}</b><small>${esc(m.sub)}</small><i aria-hidden="true">×</i></button>
          <button type="button" class="kiln-pin${isLocked(S.forgeSel[i]) ? " on" : ""}" data-act="pot-lock" data-i="${i}" aria-pressed="${isLocked(S.forgeSel[i])}" aria-label="${isLocked(S.forgeSel[i]) ? "解開" : "鎖住"}${esc(m.name)}">鎖</button></div>`
      : `<button type="button" class="kiln-slot empty" data-act="pot-open"${potGlow()}><small>${i ? "再放一樣" : "放一樣"}</small></button>`;
    const r = 20;
    const taichi = `<svg class="kiln-taichi" viewBox="-24 -24 48 48" aria-hidden="true"><circle r="26.5" class="kiln-ember"/><circle r="24.2" class="kiln-ring"/><circle r="23" class="w-hub-rim"/><g class="w-spin" style="${spinAt(ready ? 3 : 28)}">
      <circle r="${r}" class="w-yang"/><path d="M0,${-r} A${r},${r} 0 0 1 0,${r} A${r / 2},${r / 2} 0 0 1 0,0 A${r / 2},${r / 2} 0 0 0 0,${-r} Z" class="w-yin"/>
      <circle cy="${-r / 2}" r="${r / 7}" class="w-yang"/><circle cy="${r / 2}" r="${r / 7}" class="w-yin"/><circle r="${r}" class="w-seam"/></g></svg>`;
    return `<div class="kiln-wrap" id="kiln-wrap"><div class="kiln" id="kiln">
      <div class="kiln-big">${furnaceSvg(slots, ready)}</div>
      <div class="kiln-mini">
        <div class="kiln-row">${cell(slots[0], 0)}
          <button class="kiln-hub${ready ? " ready" : ""}" id="forge" data-act="forge" data-glow="forge" ${ready ? "" : "disabled"}>${taichi}<span class="kiln-lab">開爐</span></button>
          ${cell(slots[1], 1)}</div>
        <div id="kiln-warn">${kilnWarn()}</div>
      </div></div></div>`;
  }
  // 大爐子捲出狀態列底下時縮成一條、捲回來時放大：捲動時與每次畫完煉製頁都量一次（renderPage 的 afterPage 之後）
  function fixedKiln(quiet) {
    const wrap = document.getElementById("kiln-wrap"), kiln = document.getElementById("kiln");
    if (!wrap || !kiln || typeof wrap.getBoundingClientRect !== "function" || !kiln.classList) return;
    const head = document.getElementById("top");
    const topH = head && !head.hidden ? head.offsetHeight : 0;
    const compact = wrap.getBoundingClientRect().bottom < topH + 90;
    if (compact === kiln.classList.contains("compact")) return;
    if (compact) wrap.style.minHeight = `${wrap.offsetHeight}px`; // 縮起來前先撐住原本的高度，頁面才不往上跳
    kiln.classList.toggle("compact", compact);
    kiln.classList.toggle("still", compact && !!quiet);
  }
  // 捲動時一幀量一次（只在煉製頁）
  let kilnFrame = 0;
  window.addEventListener("scroll", () => {
    if (kilnFrame || S.stage !== "game" || S.tab !== "craft") return;
    kilnFrame = requestAnimationFrame(() => { kilnFrame = 0; fixedKiln(); });
  }, { passive: true });

  // 開爐成了：結果底下直接畫合出來的那一樣（Joy 2026-10-17「玩家根本無法在一合成出武學時查看武學內容評估武學強弱，還需要切換到另一個分頁」）。
  // 武學寫品質、種類、屬性、境界、第幾成、威力、跟身上同一種比強弱、功效（帶檔次的寫檔次）、特別功效、絕招，底下摺著整張功法卡與「改練上身」；
  // 意境寫重數、圓融駁雜、正邪與說明。資料是 owned_arts 的 judge（skillview.melt_judge，同批量熔煉）與 insights
  // 技能的檔次（武學技能分檔：低階＝一般功效、中階＝特別功效、高階＝content/traits.json 的 high）；沒亮的寫「未開」，修練升品才亮
  const TRAIT_TIERS = { 1: "低", 2: "中", 3: "高", 4: "高" };
  function madeCardHtml(x, item) {
    if (!item) return "";
    if (item.type === "ins") { // 出爐卡（第五輪）：跟修練頁抽屜同一張意境卡；剛出爐那一下有排場（S.forgeReveal：爐火一閃、卡翻面、品相印最後蓋上）
      const i = (x.insights || []).find((r) => r.id === item.id);
      return i ? `<div class="made-card ins-made">${insightCardHtml(i, { fits: true, reveal: !!S.forgeReveal })}</div>` : "";
    }
    const a = (x.owned_arts || []).find((r) => r.id === item.id);
    if (!a) return "";
    const j = a.judge || {};
    const sub = [a.kind, a.attribute ? `屬${a.attribute}` : "", a.affinity ? `收${a.affinity}` : "", `第${a.level}成`].filter(Boolean);
    const diff = typeof j.worn_diff === "number" ? j.worn_diff : null;
    const verdict = diff === null ? ""
      : diff > 0 ? `<b class="up">比身上那門強 ${meltNum(diff)}</b>` : diff < 0 ? `<b class="down">比身上那門弱 ${meltNum(diff)}</b>` : "跟身上那門一樣";
    const tags = [];
    (j.traits || []).forEach((t) => tags.push(`<i class="tr${t.tier ? ` t${t.tier}` : ""}">${t.tier && TRAIT_TIERS[t.tier] ? `<em>${TRAIT_TIERS[t.tier]}</em>` : ""}${esc(t.name)}${t.layers > 1 ? `<small>${t.layers} 層</small>` : ""}</i>`));
    if (j.special) tags.push(`<i class="tr t2"><em>中</em>${esc(j.special)}</i>`); // 來路帶的特別功效：中階
    (j.dormant || []).forEach((n) => tags.push(`<i class="tr off"><em>未開</em>${esc(n)}</i>`));
    if (j.ultimate) tags.push(`<i class="hi">${tsealHtml("絕")}〔${esc(j.ultimate)}〕</i>`);
    if (j.tactic) tags.push(`<i class="hi">${tsealHtml(j.tactic_title || "本命")}〔${esc(j.tactic)}〕</i>`);
    (a.slots || []).forEach((t) => tags.push(t ? `<i class="tr t2"><em>槽</em>「${esc(t.name)}」〔${esc(t.skill)}〕${esc(t.mark)}</i>` : `<i class="tr off">空槽</i>`));
    return `<div class="made-card">
      <div class="mc-head">${seal(a.quality, true)}<div><b>【${esc(a.name)}】</b><small>${sub.map(esc).join("・")}</small></div>
        ${typeof j.power === "number" ? `<span class="mc-power">威力<b>${j.power}</b></span>` : ""}</div>
      <p class="mc-verdict">${verdict}<span class="muted">${verdict ? "・" : ""}${a.worn ? "已配上身" : "放在功法庫"}</span></p>
      ${tags.length ? `<div class="mc-tags">${tags.join("")}</div>` : ""}
      <details class="fold"><summary>整張功法卡</summary><div class="fold-body">${tenCells(a.card)}</div></details>
      ${a.worn ? "" : `<button class="btn small" data-act="switch" data-id="${esc(a.id)}">改練上身<small>熟練度各自保留</small></button>`}
    </div>`;
  }
  // 預覽卡（合成即設計定案第三節；Joy 2026-10-19「這個UI不用跟著調整嗎」）：兩格都放好時爐子底下不再是一團字，
  // 而是跟出爐卡同一個形狀的一張卡——品級印、屬性、境界、一上手第幾成、功效籤、亮幾格、舊功效怎麼傳、為什麼是這個屬性、
  // 有沒有人合過、花多少；開不了爐的原因在最底下。資料全是伺服器算的（skillview.forge_preview），網頁一個字不算。
  // 擲骰的爐（fixed 關著）品級印是「？」、寫機率那一句；合併意境寫幾重、圓融駁雜。
  function previewCardHtml(v) {
    if (!v) return "";
    const merge = v.kind === "合併";
    const sub = [v.attribute ? `屬${v.attribute}` : "", merge ? "" : v.gen, v.level > 1 ? `第${v.level}成` : ""].filter(Boolean);
    const badge = merge ? '<span class="qseal qi big">意</span>' : v.quality ? seal(v.quality, true) : '<span class="qseal q1 big">？</span>';
    const pair = merge || v.kind === "揣摩"; // 意境＋意境：品質照兩份裡好的，另寫真意機會
    // 真意幾成（鐵匠鋪與合成流程 3.5，企劃者 2026-10-29「寫百分比沒關係」）：合併而且那一路有真意時伺服器給 grand_pct，寫在火候字後面；
    // 揣摩、那一路沒有真意是 null，不寫（不寫「真意 0%」）。字待 joy 潤
    const grand = merge && v.grand_pct != null ? `<span class="mc-grand">真意 ${v.grand_pct | 0}%</span>` : "";
    const verdict = pair ? `${fireHtml(v.fire, false, grand)}${merge && v.depth ? `<span class="muted">${esc(v.depth)}</span>` : ""}`
      : v.quality ? `<b>${esc(v.quality)}</b>${v.why && v.why.length ? `<span class="muted">・${v.why.map(esc).join("；")}</span>` : ""}${v.near ? `<span class="near">・${esc(v.near)}</span>` : ""}`
      : `品質看造化：${esc(v.odds || "")}`;
    const tags = (v.traits || []).map((t) => t.grand ? `<i class="tr grand${t.maybe ? " maybe" : ""}">${esc(t.name)}<small>真意</small></i>`
      : t.special ? `<i class="tr sp">${esc(t.name)}</i>`
      : `<i class="tr${t.maybe ? " maybe" : ""}">${esc(t.name)}${t.maybe ? "" : lvHtml(t.layers)}</i>`); // 待 joy 潤
    if (v.slots) tags.push(`<i class="tr off">${esc(v.slots)}</i>`);
    const notes = [merge ? "" : v.depth, v.keep, v.attribute_why, v.known].filter(Boolean);
    return `<div class="made-card preview">
      <div class="mc-head">${badge}<div><b>${esc(v.made)}</b><small>${sub.map(esc).join("・")}</small></div>
        ${v.level > 1 ? `<span class="mc-power">一上手<b>${v.level}<small>成</small></b></span>` : ""}</div>
      <p class="mc-verdict">${verdict}</p>
      ${tags.length ? `<div class="mc-tags">${tags.join("")}</div>` : ""}
      ${notes.length ? `<p class="mc-note">${notes.map((n) => esc(n.replace(/。$/, ""))).join("。")}。</p>` : ""}
      <p class="mc-cost">${esc(v.cost)}</p>
      ${v.problem ? `<p class="kiln-warn">⚠ ${esc(v.problem)}</p>` : ""}
    </div>`;
  }
  // 爐子底下那一格：有預覽卡畫卡，否則畫說明那一行（空爐、只放一樣、不是你的東西）
  function forgeLineHtml(x) {
    return S.forgePreview ? previewCardHtml(S.forgePreview) : `<div class="card">${S.forgeLine || x.forge_line}</div>`;
  }
  // 序章裡點名的那一格（pick:insight）：抽屜關著時亮在爐子的空格上（點了開抽屜，裡面那一顆再亮）
  function potGlow() {
    return S.craftPick ? "" : ' data-glow="pick:insight"';
  }
  // 挑東西放進爐的抽屜（Joy 2026-10-19 決策卡選「點格子開抽屜」：爐子、預覽卡、開爐永遠在第一屏，清單再長也不用捲頁）：
  // 點爐子的空格從底下升起，篩選、武學、意境都在裡面；點一樣就放進去，兩格放滿自動收起、預覽當場更新；放了一樣還缺一樣就留著接著挑。
  // 清單本身（craftChip、篩選、再列、合不了的灰掉）跟以前在頁面上的一模一樣
  function craftSheetHtml(x) {
    // 抽屜本來就開著（放了一樣、篩選、再列時重畫）：不再從底下升上來一次（Joy 2026-10-22「合成前點第一個素材時畫面也會閃一下」）
    const still = document.querySelector(".craft-sheet") ? " still" : "";
    return `<div class="sheet-bg${still}" data-act="pot-close"></div>
      <div class="sheet craft-sheet${still}" role="dialog" aria-label="挑東西放進爐">${craftSheetInner(x)}</div>`;
  }
  function craftSheetInner(x) {
    const v = craftView();
    const keep = (type, thing) => (!v.attr || thing.attribute === v.attr) && (!v.quality || thing.look === v.quality) && (!v.okOnly || !pickMark(type, thing.id));
    const order = (list) => v.sort === "name" ? [...list].sort((a, b) => a.name.localeCompare(b.name, "zh-Hant"))
      : v.sort === "attr" ? [...list].sort((a, b) => a.attribute.localeCompare(b.attribute, "zh-Hant")) : list; // 照品質＝伺服器的順序
    const ins = order(x.insights.filter((i) => keep("ins", i)));
    const first = S.forgeSel[0];
    const held = first ? x.insights.find((r) => r.id === first.id) : null;
    const title = !first ? "放一個意境進爐" : held ? `爐裡${isLocked(first) ? "鎖著" : "有"}「${esc(held.name)}」，再放一個` : "再放一個";
    return `
        <div class="grip"></div>
        <div class="top-row"><h3 style="flex:1">${title}</h3><button type="button" class="btn small ghost" data-act="pot-close">關閉</button></div>
        ${craftFilterRow(x)}
        <div class="label">意境 <small class="muted">不同的合出新的意境，同一種的兩份是揣摩</small></div>
        ${x.insights.length ? (ins.length ? `<div class="chips">${ins.map((i) => craftChip("ins", i, `${i.look ? `${i.look}品` : ""}・屬${i.attribute}${i.lean !== "無" ? `・${i.lean}` : ""}・${fxText(i.fx) || i.depth || ""}`, i.grand ? 3 : 2,
          (i.glow || []).includes("pick:insight") && !S.forgeSel.some((p) => p.type === "ins" && p.id === i.id) ? ' data-glow="pick:insight"' : "")).join("")}</div>`
          : '<p class="muted">沒有合這些條件的意境。</p>')
          : '<p class="muted">還沒悟到任何意境。去探索，荒郊野外最容易有所領悟。</p>'}`;
  }
  function pageCraft() {
    const x = S.menxia;
    if (!x) return '<p class="muted">載入中…</p>';
    // 爐子兩格要畫的：意境寫「意境」與屬性（找不到就當空格）
    const slotOf = (p) => {
      if (!p) return null;
      const i = x.insights.find((r) => r.id === p.id);
      return i && { name: i.name, sub: `意境・${i.attribute}`, rank: 2 };
    };
    const ready = forgeReady();
    // 合出來的那一樣的卡排在結果那段話前面：一開爐第一眼就看到它強不強（Joy 2026-10-17）
    const result = S.forgeResult ? `${madeCardHtml(x, S.forgeMade)}<div class="msg forge-result">${S.forgeResult.html}</div>` : "";
    // 爐子、預覽卡（或說明那一行）、結果都在第一屏；挑東西在抽屜裡（craftSheetHtml），頁面本身不長。
    // 爐裡還沒放滿時預覽那一行底下一顆「挑東西放進爐」（點爐子的空格也行）
    // 煉製頁是從「俠客」頁進來的（減法季批 1：分頁列上沒有它自己一格）：最上面一行「‹ 俠客」回去
    return `
      <div class="self-sub"><button class="linkish back" data-act="tab" data-tab="practice">‹ 俠客</button><h3>煉製</h3></div>
      ${proGuide()}
      <div class="msg" id="mx-msg">${S.message}</div>
      ${kilnHtml([slotOf(S.forgeSel[0]), slotOf(S.forgeSel[1])], ready)}
      <div id="forge-line">${forgeLineHtml(x)}</div>
      ${ready ? "" : `<button type="button" class="btn pot-open" data-act="pot-open">${S.forgeSel.length ? "再放一樣進爐" : "挑東西放進爐"}<small>意境的清單</small></button>`}
      ${result}
      ${attrNoteHtml(x)}
      ${x.clue_items?.length ? `<div class="label">伏筆物品</div>
      <div class="chips clues">${x.clue_items.map((i) => `<div class="clue"><b>${esc(i.name)}</b><span>×${i.count}</span></div>`).join("")}</div>` : ""}
      ${manualEntry("arts")}${manualEntry("forge")}
      <details class="fold"><summary>背包</summary><div class="fold-body">${x.bag}</div></details>
      ${S.craftPick ? craftSheetHtml(x) : ""}`;
  }

  // 自創武學（Joy 2026-10-20：先選兵器、擺姿勢當圖示、寫一句意，槽分顏色）：煉製頁爐子底下一塊，五步——
  // 執器（內功／武學、兵器或行功之法，menxia create_begin）→ 擺式（拖火柴人，menxia create_pose）→ 立意（一句 2～20 字的意，
  // /api/do/create_intent 請模型讀）→ 成形（伺服器擲好四格顏色，這裡畫成玉環）→ 立名（menxia create_name；重來 create_back、作罷 create_cancel）。
  // 資料全是伺服器給的 status.create（create.view）；擺式時讀出的偏向網頁先照同一套規則算給人看，擺定那一下以伺服器為準。字待 joy 潤
  const CREATE_STEPS = [["form", "執器"], ["pose", "擺式"], ["intent", "立意"], ["name", "成形・立名"]];
  // 擺式時即時算主屬性（create.top_of 的同一套）：伺服器給不含姿勢的權重，這裡加上姿勢讀出的兩路，取最高（同分照屬性的先後）
  function createMain(c, draft, attrs) {
    const w = { ...(draft.base_weights || {}) };
    attrs.forEach((a, i) => { w[a] = (w[a] || 0) + (Number((c.pose_weights || [])[i]) || 0); });
    const order = c.attributes || [];
    return order.reduce((best, a) => (best === null || (w[a] || 0) > (w[best] || 0) ? a : best), null);
  }
  // 勢與稀有路數（Joy 2026-10-22「要加」）：四個勢怎麼擺、對應哪個時機，現在擺的那一個亮；底下一行「每一格都有機會撞到稀有路數」
  // （表上每一格都有稀有的才寫，伺服器給 rare_line）。擺式時拖一下就重畫（rigRedraw），立意那一步照伺服器讀的。字待 joy 潤
  function stanceBoxHtml(c, kind, stance, main) {
    const rows = ((c.stances || {})[kind] || []);
    const now = rows.find((r) => r.stance === stance) || {};
    const list = rows.map((r) => `<li class="${r.stance === stance ? "on" : ""}"><span><b>${esc(r.stance)}</b>・${esc(r.timing)}</span><small>${esc(r.how)}</small></li>`).join("");
    return `<p class="cr-now">此式是<b>${esc(stance || "")}</b>・${esc(now.timing || "")}${main ? `<span class="muted small">（連兵器、意一起算，主屬性現在偏${esc(main)}）</span>` : ""}</p>
      <ul class="cr-stances">${list}</ul>
      ${c.rare_line ? `<p class="muted small">${esc(c.rare_line)}</p>` : ""}`;
  }
  const biasHtml = (bias) => Object.entries(bias || {}).sort((p, q) => q[1] - p[1]).map(([k]) => ringHtml([k], esc(k), "jchip")).join("");
  // 作罷（鐵匠鋪與合成流程 3.1，FB-903：誤觸白丟心得）：立意時付過心得（draft.paid 是實際收的那一筆）先問一次，確認鈕「作罷」、另一顆「再想想」；
  // 還沒付（執器、擺式）沒有損失，直接作罷。規則不動：作罷照舊不退。字待 joy 潤
  const CREATE_CANCEL_ASK = "作罷？立意時收的 {n} 心得不退。"; // 待 joy 潤
  const CREATE_CANCEL_NO = "再想想"; // 待 joy 潤
  function createCancel() {
    const c = S.main && S.main.status && S.main.status.create;
    const paid = c && c.draft ? c.draft.paid | 0 : 0;
    if (paid > 0) ask(CREATE_CANCEL_ASK.replace("{n}", paid), "作罷", () => mx("create_cancel"), { no: CREATE_CANCEL_NO });
    else return mx("create_cancel");
  }
  function createHtml() {
    const c = S.main && S.main.status && S.main.status.create;
    if (!c || !c.on) return "";
    const step = c.step, at = CREATE_STEPS.findIndex((p) => p[0] === step);
    const head = c.left == null ? "" : `<p class="muted small cr-left">本季還可自創 ${c.left | 0} 門</p>`;
    const steps = `<ol class="cr-steps">${CREATE_STEPS.map(([k, w], i) => `<li class="${i === at ? "on" : i < at ? "done" : ""}">${w}</li>`).join("")}</ol>`;
    const draft = c.draft;
    if (step !== "pose") S.createPose = null;
    if (step !== "name") S.createReread = null; // 重讀這句意那一格打到一半的字只留在這一門的成形那一步
    if (!draft) {
      if (c.problem) return `${head}<div class="card create"><p class="muted">${esc(c.problem)}</p></div>`;
      const f = S.createPick || (S.createPick = { kind: c.kinds.includes("武學") ? "武學" : c.kinds[0], form: "" });
      const short = createShort(c);
      const forms = (c.forms && c.forms[f.kind]) || [];
      const kinds = c.kinds.map((k) => `<button type="button" class="fchip${f.kind === k ? " on" : ""}" data-act="create-kind" data-val="${esc(k)}">${esc(k)}</button>`).join("");
      const tiles = forms.map((o) => `<button type="button" class="cr-form${f.form === o.key ? " on" : ""}" data-act="create-pick" data-val="${esc(o.key)}">
          ${f.kind === "武學" ? figSvg((c.presets.find((p) => p.name === ({ 拳腳: "起手", 棍: "守禦", 弓弩: "奇變" }[o.key] || "進擊")) || {}).angles, o.key, "tile-fig") : ""}
          <b>${esc(o.key)}</b><span class="cr-bias">${biasHtml(o.bias)}</span><small>${esc(o.blurb)}</small></button>`).join("");
      return `${head}<div class="card create">${steps}
        <p class="muted">花心得立一門自己的功夫。手裡拿什麼、擺什麼架式、心裡存什麼意，都會讓它偏向不同的路數。</p>
        <div class="crow"><span>要立</span><div class="fchips">${kinds}</div></div>
        <p class="mc-cost${short ? " short" : ""}">${short
          ? `開始自創要先有 ${c.price | 0} 心得，你有 ${c.xinde | 0}，${createShortWord(c)}（立意那一刻才收）`
          : `開始自創要有心得 ${c.price | 0}（你有 ${c.xinde | 0} 點）・立意那一刻才收，之後擱下不退`}</p>
        <div class="cr-forms">${tiles}</div>
        <button class="btn primary" data-act="create-begin" ${f.form && !short ? "" : "disabled"}>${short ? createShortWord(c) : f.form ? `握起${esc(f.form)}` : "先挑一樣"}<small>${short ? "攢夠了再來" : "下一步：擺個架式"}</small></button>
      </div>`;
    }
    const weapon = draft.kind === "武學" ? draft.form : null;
    const sum = `<p class="create-sum"><b>${esc(draft.kind)}</b>・${esc(draft.form)}${draft.intent ? `・意「${esc(draft.intent)}」` : ""}</p>`;
    // 付過心得（立意那一刻收，Joy 2026-10-21）之後作罷不退：鈕上寫明。字待 joy 潤
    const quit = `<button class="btn ghost" data-act="create-cancel">${draft.paid ? "作罷<small>心得不退</small>" : "作罷"}</button>`;
    if (step === "pose") {
      const P = S.createPose || (S.createPose = { ...draft.pose });
      const read = poseRead(P);
      const presets = c.presets.map((p) => `<button type="button" class="fchip" data-act="create-preset" data-val="${esc(p.name)}">${esc(p.name)}</button>`).join("");
      return `${head}<div class="card create">${steps}${sum}
        <div class="cr-rig"><svg id="create-rig" class="fig" viewBox="0 0 220 240" data-weapon="${esc(weapon || "")}"><line class="ground" x1="20" y1="226" x2="200" y2="226"/>${figBody(P, weapon, true)}</svg>
          <div class="cr-side"><p class="muted">拖金色的關節擺出這一門的架式，它會成為這門功夫的圖示。也可以從這幾個起手：</p>
            <div class="fchips wrap">${presets}</div>
            <p class="cr-read" id="create-read">${esc(poseReadText(read.attrs))}</p>
            <p class="muted small" id="create-why">${esc(read.why.length ? `看的是：${read.why.join("、")}。` : "手伸出去、馬步放寬、提腿或前傾，都會讓它偏向一路。")}</p></div></div>
        <div class="cr-stance-box" id="create-stance">${stanceBoxHtml(c, draft.kind, read.stance, createMain(c, draft, read.attrs))}</div>
        <div class="acts"><button class="btn primary" data-act="create-pose">擺定<small>下一步：立意</small></button>${quit}</div>
      </div>`;
    }
    if (step === "intent") {
      return `${head}<div class="card create">${steps}${sum}
        <div class="cr-mini">${figSvg(draft.pose, weapon, "cr-fig")}<p>${esc(draft.pose_read)}</p></div>
        <div class="cr-stance-box">${stanceBoxHtml(c, draft.kind, draft.stance, draft.main)}</div>
        <div class="crow"><span>意</span><input class="input" id="create-text" maxlength="${c.intent_max | 0}" placeholder="一句話說這門功夫的神，2～${c.intent_max | 0} 字" value="${esc(S.createText || "")}"></div>
        <p class="muted small">寫得有神有象，底子越厚；意裡帶出的神韻也會讓它偏向那一路。${draft.paid ? "" : `立意那一刻就成形、收心得 ${c.price | 0}，之後擱下不退。`}</p>
        <div class="acts"><button class="btn primary" data-act="create-intent">立意<small>${draft.paid ? "已付過心得" : `心得 ${c.price | 0}`}・下一步：成形</small></button><button class="btn ghost" data-act="create-back" data-to="pose">重擺架式</button>${quit}</div>
      </div>`;
    }
    const rings = (draft.colors || []).map((cc, i) => `<div class="cr-ring">${ringHtml(cc, `<b>${i + 1}</b>`)}<small>${esc(ringWord(cc))}</small></div>`).join("");
    const grade = c.grade || "上品";
    const stance = draft.stance ? `<p class="cr-stance"><b>${esc(draft.stance)}</b>・${esc(draft.timing || "")}${draft.fire ? `・火候 <b class="fire-${esc(draft.fire)}">${esc(draft.fire)}</b>` : ""}</p>` : "";
    const look = draft.tier ? `${lookLadder(draft.tier, ART_LOOK_STEPS)}${(draft.marks || []).length ? `<p class="cr-look tier-${esc(draft.tier)}">${esc(draft.look)}</p>` : ""}` : "";
    const redo = draft.redo > 0 ? `<button class="btn ghost" data-act="create-back" data-to="pose">重擺</button><button class="btn ghost" data-act="create-back" data-to="intent">重立意</button>` : "";
    return `${head}<div class="card create">${steps}
      <div class="cr-made">${figSvg(draft.pose, weapon, "cr-fig big")}<div><p class="create-sum"><b>${esc(draft.kind)}</b>・${esc(draft.form)}</p><p>意「${esc(draft.intent)}」</p><p class="muted small">${esc(draft.pose_read)}・${esc(draft.read_text)}</p></div></div>
      <div class="cr-rings">${rings}</div>
      <p class="muted small">${c.slots[grade] | 0} 格全開。每一格只收自己顏色的意境，八色一圈的什麼都收。</p>
      ${look}
      ${draft.power ? `<p class="muted small">${esc(draft.power)}</p>` : ""}
      ${stance}
      ${draft.rare_hit ? `<p class="cr-rare">${esc(draft.rare_hit)}</p>` : ""}
      ${draft.tactic ? `<p class="art-tactic cr-move">${tacticHtml(draft.tactic)}</p>` : ""}
      ${draft.say ? `<p class="muted small">出手時：「${esc(draft.say)}」</p>` : ""}
      <p class="muted small">招剛創時還生，練到第四成才使得順。</p>
      ${draft.redo > 0 ? `<p class="muted small">不滿意這個形，可以免費重來一次（重擺或重立意）。</p>` : ""}
      <div class="cr-reroll">${(draft.reroll_left | 0) <= 0 ? `<button class="btn" disabled>重骰<small>這一門已骰滿 ${c.reroll_cap | 0} 次</small></button><span class="muted small">一門最多重骰 ${c.reroll_cap | 0} 次：留下這個形，或回頭重來。</span>`
        : c.rerolls > 0 ? `<button class="btn" data-act="create-reroll">重骰<small>重悟帖 剩 ${c.rerolls | 0} 張</small></button><span class="muted small">同一個架式與意，三格顏色與變招再擲一次。這一門還能重骰 ${draft.reroll_left | 0} 次。</span>`
        // 手上沒帖：引去萬寶閣，停在重悟帖那一件（Joy 2026-10-22「沒有重悟丹不會自動提示玩家去商城購買」；同修練頁沒丹時的破境丹）
        : c.shop ? `<button class="btn" data-act="mall-goto" data-id="${esc(c.shop)}">去萬寶閣<small>買重悟帖</small></button><span class="muted small">重悟帖可以直接重骰這個形，不必重來（一門最多 ${draft.reroll_left | 0} 次）。</span>`
        : `<span class="muted small">萬寶閣的重悟帖可以直接重骰這個形，不必重來（一門最多 ${draft.reroll_left | 0} 次）。</span>`}</div>
      ${(draft.reroll_left | 0) > 0 && c.rerolls > 0 ? `<div class="cr-reread">
        <div class="crow"><span>意</span><input class="input" id="create-reread" maxlength="${c.intent_max | 0}" value="${esc(S.createReread != null ? S.createReread : draft.intent || "")}"></div>
        <div class="cr-reroll"><button class="btn" data-act="create-reread">重讀這句意<small>重悟帖 剩 ${c.rerolls | 0} 張</small></button><span class="muted small">同一句意（也可以改寫）再讀一次：意分、火候、屬性重來，形也跟著重擲。跟重骰共用這一門的次數；沒讀成不扣帖。</span></div>
      </div>` : ""}
      <div class="crow"><span>名字</span><input class="input" id="create-name" maxlength="6" placeholder="2～6 個字，全服不能重名"></div>
      <div class="crow"><span>招名</span><input class="input" id="create-move" maxlength="4" value="${esc(draft.move || "")}" placeholder="2～4 個字"></div>
      <div class="acts"><button class="btn primary" data-act="create-name">立名<small>${draft.paid ? "心得已在立意時付了" : `心得 ${c.price | 0}`}</small></button>${redo}${quit}</div>
    </div>`;
  }
  // 自創單獨一頁（Joy 2026-10-21「創造武學不要卡在煉成的中間」）：入口在「俠客」頁底下那三顆的中間（減法季批 1；以前在修練頁功法庫的頂上），
  // 點了整頁換成自創（S.createOpen），左上「返回自己」。立好或作罷就回修練頁、結果寫在上面。字待 joy 潤
  const CREATE_STEP_WORD = Object.fromEntries(CREATE_STEPS);
  // 「俠客」頁底下「自創武學」那一顆的小字：起了意的寫停在哪一步，沒起意寫價錢（或這一季還能創幾門、做不了的原因）
  function createSub(c) {
    const d = c.draft;
    return d ? `${esc(d.kind)}・${esc(d.form)}，停在「${esc(CREATE_STEP_WORD[c.step] || "")}」`
      : c.problem ? esc(c.problem) : createShort(c) ? createShortWord(c)
      : (c.left == null ? `心得 ${c.price | 0}` : `本季還可自創 ${c.left | 0} 門・心得 ${c.price | 0}`);
  }

  const createShortWord = (c) => `還差 ${createShort(c)} 心得`;
  function createPageHtml() {
    return `<div class="cr-page">
      <header class="cr-bar"><button class="book-back" data-act="create-close" aria-label="返回自己">‹ 返回自己</button><span class="cr-bar-title">自創武學</span></header>
      <div class="msg" id="mx-msg">${S.message || ""}</div>
      ${createHtml()}
    </div>`;
  }
  async function createIntent() {
    const box = document.getElementById("create-text");
    if (box) S.createText = box.value;
    await busy(async () => {
      const r = await api("/api/do/create_intent", { text: S.createText || "" });
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
      if (r.main && r.main.status && r.main.status.create && r.main.status.create.step === "name") S.createText = "";
    }, WAIT_LINES.forge || SENT_WAITING);
  }
  // 重悟帖：重讀這句意（Joy 2026-10-22「立意那邊好像也要可以重骰」）：同 createIntent 走三段式，模型在鎖外重讀；讀成了留在成形那一步
  async function createReread() {
    const box = document.getElementById("create-reread");
    if (box) S.createReread = box.value;
    await busy(async () => {
      const r = await api("/api/do/create_reread", { text: S.createReread != null ? S.createReread : "" });
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
      const c = r.main && r.main.status && r.main.status.create;
      if (!c || !c.draft || c.step !== "name") S.createReread = null;
    }, WAIT_LINES.forge || SENT_WAITING);
  }
  // 擺式的拖曳：按在關節上開始，指頭移到哪、那一節就轉向哪裡。只重畫那張圖與讀出來的那兩句，不重畫整頁
  const RIG_DRAG = { head: null, lEl: ["lSh", "lS", []], lHa: ["lEl", "lE", ["lS"]], rEl: ["rSh", "rS", []], rHa: ["rEl", "rE", ["rS"]],
    lKn: ["lHip", "lH", null], lFt: ["lKn", "lK", ["lH"]], rKn: ["rHip", "rH", null], rFt: ["rKn", "rK", ["rH"]] };
  let rigDrag = null;
  const rigNorm = (d) => { while (d > 180) d -= 360; while (d < -180) d += 360; return Math.round(d * 10) / 10; };
  function rigRedraw(svg) {
    const P = S.createPose;
    svg.innerHTML = `<line class="ground" x1="20" y1="226" x2="200" y2="226"/>${figBody(P, svg.dataset.weapon || null, true)}`;
    const read = poseRead(P), out = document.getElementById("create-read"), why = document.getElementById("create-why");
    if (out) out.textContent = poseReadText(read.attrs);
    if (why) why.textContent = read.why.length ? `看的是：${read.why.join("、")}。` : "手伸出去、馬步放寬、提腿或前傾，都會讓它偏向一路。";
    const box = document.getElementById("create-stance"), c = S.main && S.main.status && S.main.status.create;
    if (box && c && c.draft) box.innerHTML = stanceBoxHtml(c, c.draft.kind, read.stance, createMain(c, c.draft, read.attrs));
  }
  function rigMove(ev) {
    if (!rigDrag || !S.createPose) return;
    const { svg, j } = rigDrag, P = S.createPose;
    const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
    const m = pt.matrixTransform(svg.getScreenCTM().inverse()), J = rigJoints(P), r2d = (r) => (r * 180) / Math.PI;
    const spec = RIG_DRAG[j];
    if (!spec) P.t = Math.max(-35, Math.min(35, Math.round(r2d(Math.atan2(-(m.x - RIG.CX), -(m.y - RIG.SY))))));
    else {
      const from = J[spec[0]], a = r2d(Math.atan2(m.x - from.x, m.y - from.y));
      const minus = (spec[2] === null ? 0 : P.t || 0) + (spec[2] || []).reduce((acc, k) => acc + (P[k] || 0), 0);
      P[spec[1]] = rigNorm(a - minus);
    }
    rigRedraw(svg);
  }
  document.addEventListener("pointerdown", (ev) => {
    const t = ev && ev.target, svg = t && t.closest ? t.closest("#create-rig") : null;
    if (!svg || !t.dataset || !t.dataset.j || !S.createPose) return;
    rigDrag = { svg, j: t.dataset.j };
    try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* 舊瀏覽器 */ }
    ev.preventDefault();
  });
  document.addEventListener("pointermove", (ev) => { if (rigDrag) { ev.preventDefault(); rigMove(ev); } }, { passive: false });
  const rigEnd = () => { rigDrag = null; };
  document.addEventListener("pointerup", rigEnd);
  document.addEventListener("pointercancel", rigEnd);

  // 武學譜（status.manual，secret_recipes.view；企劃者 2026-10-10「武學譜能不能獨立一頁，做得更豪華一些」）：
  // 煉製頁上只放入口（manualEntry），點了開全螢幕的一本書（bookHtml，S.book，疊在整個畫面上、左上返回）。
  // 鑄譜（status.forge_manual，打造隱藏配方設計 6.3）用同一本書，入口擺在武學譜旁邊（S.book 記開哪一本：false／"arts"／"forge"，true 當武學譜），打中過的另外寫配方（`recipe`）。
  // 一條秘方一頁，聽過的口訣直書大字，合中了蓋一方朱印寫它的名號。只列聽過的那幾句：不寫種類、配方、還差幾句（還沒拿到的線索一律不露）
  // 兩本書：武學譜（口訣與秘方）、鑄譜（打造的隱藏配方）。字待 joy 潤。一行寫完：tests/web/test_arts_pages.py、test_arts_pages_two.py 的假瀏覽器照名字把這一行切出去（webharness.konst 只認一行的 const）
  const BOOKS = { arts: { title: "武學譜", verb: "合出", unit: "口訣", empty: "江湖上流傳的老話，有時藏著合成的門道。" }, forge: { title: "鑄譜", verb: "打出", unit: "鑄訣", empty: "鐵匠的閒話、說書人的掌故，有時藏著失傳的鑄法。" } };
  // 武學譜兩段的段名與一句說明（字待 joy 潤）；秘方的種類：fuse 裝滿武學的意境槽、merge 兩個意境合成（secret_recipes.view 的 kind）
  const MANUAL_PARTS = [["fuse", "武學篇", "武學的意境槽裝滿了，暗合口訣"], ["merge", "意境篇", "兩個意境放進爐裡合成"]];
  const MANUAL_VERB = { fuse: "使出", merge: "合出" };
  function manualRows(which = "arts") {
    const st = S.main && S.main.status;
    return (st && (which === "forge" ? st.forge_manual : st.manual)) || [];
  }

  // 一卷線裝書（入口與封面共用）：書衣、題簽、四道線
  function bookIcon() {
    return `<svg class="book-icon" viewBox="0 0 48 56" aria-hidden="true"><rect x="4" y="3" width="40" height="50" rx="2" class="bk-cover"/>
    <rect x="22" y="9" width="12" height="32" class="bk-slip"/><path d="M28 13v24" class="bk-slip-ink"/>
    <path d="M10 3v50M4 12h6M4 24h6M4 36h6M4 48h6" class="bk-thread"/></svg>`;
  }
  function manualEntry(which) {
    const rows = manualRows(which), b = BOOKS[which];
    const solved = rows.filter((r) => r.solved).length;
    // 武學譜的分母是這一季全服共有幾條（status.manual_total；玩家回報 2026-10-25：以前寫「你聽過的」，參透完了也看不出還剩幾條）
    const total = which === "arts" ? (S.main?.status?.manual_total | 0) : 0;
    const sub = total ? `本季已參透 ${solved}／${total}${rows.length > solved ? `・線索 ${rows.length - solved} 條` : ""}`
      : rows.length ? `收錄${b.unit} ${rows.length} 則${solved ? `・已參透 ${solved}` : ""}` : "卷中尚無一字";
    return `<button class="manual-entry" data-act="book-open" data-book="${which}">${bookIcon()}<span><b>${b.title}</b><small>${sub}</small></span><i class="go">翻閱 ›</i></button>`;
  }
  // 參透一條秘方的那一下跳的視窗（企劃者 2026-10-25「應該是跳顯出個視窗比較明顯」；伺服器的 secret，secret_recipes.solved_card）：
  // 朱印蓋下來（同破境衝關的印）、參透的是哪一條、聽過的口訣、這一季的進度，「翻開武學譜」直接進那一頁。點外面或「收起」關掉。字待 joy 潤
  function secretPop(c) {
    if (!c) return;
    document.getElementById("sp-pop")?.remove();
    const box = document.createElement("div");
    box.id = "sp-pop";
    box.className = "sp-wrap";
    const pct = c.total ? Math.round((c.solved / c.total) * 100) : 0;
    const clues = (c.clues || []).map((t) => `<p class="sp-clue">「${esc(t)}」</p>`).join("");
    box.innerHTML = `<div class="sp-card" role="dialog" aria-label="${esc(c.title)}">
      <div class="sp-seal">${sealSvg(c.name)}</div>
      <p class="sp-title">${esc(c.title)}</p>
      <p class="sp-name">【${esc(c.name)}】</p>${clues}
      <div class="sp-bar" aria-hidden="true"><i style="width:${pct}%"></i></div>
      <p class="sp-note">${esc(c.note || `這一季的秘方，你已參透 ${c.solved}／${c.total}。`)}</p>
      <div class="sp-btns"><button class="btn primary" data-act="secret-book">翻開武學譜</button><button class="btn ghost" data-act="secret-close">收起</button></div>
    </div>`;
    box.addEventListener("click", (ev) => { if (ev.target === box) box.remove(); });
    document.body.appendChild(box);
  }
  // 直書一句一欄：口訣照標點斷開（「日出東嶺，」「一寸一寸爬上峰頂。」），每一段自己起一欄，不在句中折行
  const clauses = (text) => text.split(/(?<=[，。；！？、：])/).filter((t) => t.trim());
  // 朱印：名號照字數排成方印（四字兩行兩列、其餘一直行），字是白的（陰刻）。只有合中了才有
  function sealSvg(name) {
    const chars = [...name].slice(0, 6);
    const n = chars.length;
    const cols = n === 4 ? 2 : n > 4 ? 2 : 1;
    const rows = Math.ceil(n / cols);
    const cell = 40 / Math.max(rows, cols);
    // 直書的方印：右行先讀，由上而下
    const glyphs = chars.map((ch, k) => {
      const col = Math.floor(k / rows), row = k % rows;
      const cx = 46 - (col + 0.5) * (40 / cols);
      const cy = 6 + (row + 0.5) * (40 / rows);
      return `<text x="${cx.toFixed(1)}" y="${cy.toFixed(1)}" font-size="${(cell * 0.86).toFixed(1)}">${esc(ch)}</text>`;
    }).join("");
    return `<svg class="seal" viewBox="0 0 52 52" role="img" aria-label="${esc(name)}"><rect x="2" y="2" width="48" height="48" rx="3" class="seal-bg"/>
      <rect x="5" y="5" width="42" height="42" rx="1.5" class="seal-rim"/><g class="seal-ink">${glyphs}</g></svg>`;
  }

  function bookHtml(which = S.book === "forge" ? "forge" : "arts") {
    // 參透了卻一句口訣都沒聽過的那一頁寫一句（Joy 2026-10-26 卡上選「補一句」；以前直書區是空的）。寫在行內：有測試只抽這一支。待 joy 潤
    const rows = manualRows(which), b = BOOKS[which];
    const now = rows.filter((r) => !r.past); // 卷首只算這一季真的聽到、打中的：跨季記得的那幾行（past）照樣列在卷裡（FB-404）
    const solved = now.filter((r) => r.solved).length;
    const leaf = (r, k) => `<article class="leaf${r.solved ? " solved" : ""}">
        <header class="leaf-head"><span>第${cnNum(k + 1)}則</span><span class="leaf-state">${r.solved ? "已參透" : "未參透"}</span></header>
        <div class="leaf-text">${r.clues.length ? r.clues.map((c) => `<p>${clauses(c).map((t) => `<span>${esc(t)}</span>`).join("")}</p>`).join("") : r.solved ? `<p class="leaf-blank"><span>未聞口訣，誤打誤撞${which === "forge" ? "打" : "合"}了出來。</span></p>` : ""}</div>
        <footer class="leaf-foot">${r.solved ? `${sealSvg(r.solved)}<span class="leaf-sign">${MANUAL_VERB[r.kind] || b.verb}<b>【${esc(r.solved)}】</b></span>` : '<span class="leaf-sign muted">尚待參悟</span>'}${r.recipe ? `<p class="leaf-recipe">${esc(r.recipe)}</p>` : ""}</footer>
      </article>`;
    // 武學譜分兩段（Joy 2026-10-25「武學跟意境合成兩個應該分開放」）：裝滿武學意境槽的（fuse）、兩個意境合成的（merge），各自從第一則數起
    const parts = which === "arts" ? MANUAL_PARTS.map(([kind, head, hint]) => [head, hint, rows.filter((r) => r.kind === kind)]).filter(([, , rs]) => rs.length) : [];
    const leaves = !rows.length ? null : parts.length
      ? parts.map(([head, hint, rs]) => `<h3 class="leaf-part"><b>${head}</b><small>${hint}</small></h3>${rs.map(leaf).join("")}`).join("")
      : rows.map(leaf).join("");
    const body = leaves || `<article class="leaf empty"><div class="leaf-text"><p>卷中尚無一字</p></div>
        <p class="leaf-hint">${b.empty}</p></article>`;
    return `<div class="book-layer" role="dialog" aria-label="${b.title}">
      <header class="book-bar"><button class="book-back" data-act="book-close" aria-label="返回">‹ 返回</button><span class="book-bar-title">${b.title}</span></header>
      <div class="book-cover">
        <svg class="book-hills" viewBox="0 0 375 120" preserveAspectRatio="none" aria-hidden="true">
          <path class="hill far" d="M0 86 C40 58 70 64 104 46 C134 30 160 52 190 40 C226 26 258 48 292 36 C326 24 352 40 375 34 V120 H0Z"/>
          <path class="hill near" d="M0 104 C36 86 72 96 110 80 C150 64 178 88 222 76 C262 66 300 86 340 74 C356 70 366 72 375 70 V120 H0Z"/>
        </svg>
        <i class="book-moon" aria-hidden="true"></i>
        <div class="book-title"><span>${b.title}</span></div>
        <p class="book-sub">${which === "arts" && S.main?.status?.manual_total ? `本季秘方 ${S.main.status.manual_total} 條・已參透 ${solved}・所聞${b.unit} ${now.length} 則` : `本季所聞${b.unit} ${now.length} 則${solved ? `・已參透 ${solved} 則` : ""}`}</p>
      </div>
      <div class="leaves">${body}</div>
    </div>`;
  }

  // 放東西、輪詢都會問說明，回應可能晚到：只用最後一次請求的回應，而且爐子要還是問的那一爐
  let forgeLineSeq = 0;
  async function updateForgeLine() {
    const seq = ++forgeLineSeq;
    const pot = JSON.stringify(S.forgeSel);
    try {
      const r = await api("/api/forge_line", forgeBody());
      if (seq !== forgeLineSeq || pot !== JSON.stringify(S.forgeSel)) return;
      S.forgeLine = r.line;
      S.forgePreview = r.preview || null;
      const drawn = JSON.stringify(S.forgePicks);
      S.forgePicks = r.picks || null;
      // 清單上「合不了」的標記變了：只換抽屜裡那一張清單（捲到哪留在哪），爐子與頁面不重畫——整頁重畫的話火舌、剛放進去那一格的閃光都從頭來一次
      const sheet = S.tab === "craft" && JSON.stringify(S.forgePicks) !== drawn && document.querySelector(".craft-sheet");
      if (sheet) { const top = sheet.scrollTop; sheet.innerHTML = craftSheetInner(S.menxia || {}); sheet.scrollTop = top; applyGlow(); }
      const el = document.getElementById("forge-line");
      if (el) el.innerHTML = forgeLineHtml(S.menxia || {});
      const warn = document.getElementById("kiln-warn");
      if (warn) warn.innerHTML = kilnWarn();
    } catch (e) { /* 提示過 */ }
  }

  // 開爐等結果的時候頁面上方寫的那一句（W10，待 joy 潤）：取名實際約 3～5 秒，不把等待說成好幾十秒，免得人以為壞了
  const FORGE_WAIT = "爐火正旺。若這是江湖上第一次合出來，要等它取名，請稍候。";

  // 重畫時畫面不跳：記下 anchor（預設是第一個看得到的「開爐」或點子清單）在螢幕上的位置，畫完捲回同一個位置
  function keepPlace(draw, anchor) {
    const sel = anchor || "#forge-line";
    const before = document.querySelector(sel)?.getBoundingClientRect().top;
    draw();
    const after = document.querySelector(sel)?.getBoundingClientRect().top;
    if (before !== undefined && after !== undefined && after !== before) window.scrollBy({ top: after - before, left: 0, behavior: "instant" });
  }

  // 開爐：結果寫在「開爐」底下，頁面不捲（企劃者 2026-10-10）；合成了爐子清空，被拒絕的東西留著（Joy 2026-10-12）
  async function forge() {
    const btn = document.getElementById("forge");
    const step = guideKey(S.main && S.main.guide);
    let guideMoved = false, made = false, secret = null;
    await busy(async () => {
      const lab = (btn.querySelector && btn.querySelector(".kiln-lab")) || btn; // 小太極上那兩個字（大爐子縮起來時的開爐鈕）
      btn.disabled = true;
      lab.textContent = "爐火正旺…";
      btn.classList.add("forging");
      // 等結果的這段時間（首次發現的配方要等模型取名）整座爐子晃動、火舌竄高、太極快轉
      document.querySelector(".furnace .w-furnace")?.classList.add("forging");
      document.querySelector(".furnace .w-taichi")?.classList.add("hot");
      S.forgeResult = { html: esc(FORGE_WAIT) };
      const stop = watchQueue(lab, "爐火正旺…");
      try {
        const r = await api("/api/menxia/forge", forgeBody());
        S.menxia = r.menxia;
        S.message = "";
        S.forgeResult = { html: r.message };
        S.forgeMade = r.made ? r.made_item || null : null; // 合出來的那一樣：結果底下畫它的卡
        made = !!r.made;
        secret = r.secret || null; // 這一季第一次參透一條秘方：出爐之後跳視窗（secretPop）
        // 出爐的排場只演一次（一秒半，不擋操作）：畫完這一次就收，之後輪詢重畫不再翻一次
        S.forgeReveal = made;
        // 合成了：兩格清空，下一爐從頭放（Joy 2026-10-12「爐子合完應該要把上次放上去的東西自動卸下」）；
        // 被拒絕（沒合成、只回一句話）：東西留在爐裡，換一格就能再試——只拿掉已經不在手上的
        // 鎖著的那一樣留在爐裡（Joy 2026-10-19），下一爐只要再放一樣；它自己被合掉了（武學＋武學不會，意境不會用掉）就解開
        if (r.made) S.forgeSel = S.forgeLock ? S.forgeSel.filter(isLocked) : [];
        trimForgeSel();
        S.forgeLine = "";
        S.forgePreview = null;
        S.forgePicks = null;
        setMain(r.main);
        renderTop();
        guideMoved = guideKey(r.main && r.main.guide) !== step;
      } catch (e) {
        // 被擋下來（另一個分頁的上一爐還沒出爐：400）或連不上：等的時候寫的「爐火正旺……請稍候」不能留著，換成這一句，
        // 爐裡放的東西不動；api() 已經用提示泡泡講過一次，結果那一格再留一份
        S.forgeResult = { html: esc(failText(e)) };
      } finally { stop(); }
    }, WAIT_LINES.forge);
    // 引導的下一句在頁面最上面（序章師父說的話）：這時才捲上去，不然留在原位、可以馬上接著合下一爐
    if (guideMoved) { renderPage(); S.forgeReveal = false; window.scrollTo({ top: 0, behavior: "smooth" }); } else {
      keepPlace(() => renderPage());
      S.forgeReveal = false;
      if (made) kilnBurst();
      showMadeCard();
    }
    secretPop(secret);
    updateForgeLine(); // 心得、體力、「已經有了」都變了：重問一次說明
  }

  // 開爐成了：爐裡的太極猛轉兩圈（大小兩座都是），新武學的卡從爐裡冒出來；轉完回到平常的慢轉
  function kilnBurst() {
    document.querySelectorAll(".furnace .w-taichi, .kiln-taichi .w-spin").forEach((g) => {
      g.classList.add("burst");
      g.addEventListener("animationend", () => { // 轉完接回平常的慢轉：照同一個鐘起跳（spinAt），不從頭轉、不頓一下
        g.classList.remove("burst");
        const secs = parseFloat(getComputedStyle(g).animationDuration) || 28;
        g.style.animationDelay = `-${((performance.now() / 1000) % secs).toFixed(2)}s`;
      }, { once: true });
    });
    const card = document.querySelector(".made-card");
    if (card) card.classList.add("emerge");
  }

  // 新武學的卡被黏在上面的固定列蓋住了（往下捲著開爐時）：捲到卡頭剛好露在固定列底下；本來就看得到就不動
  function showMadeCard() {
    const card = document.querySelector(".made-card"), bar = document.querySelector(".kiln.compact");
    if (!card || !bar || typeof card.getBoundingClientRect !== "function") return;
    const under = bar.getBoundingClientRect().bottom + 8, top = card.getBoundingClientRect().top;
    if (top < under) window.scrollBy({ top: top - under, left: 0, behavior: "smooth" });
  }

  // S.menxia 換成新的一份之後：爐裡放的若已經不在了（例如在修練頁熔掉），拿掉、說明那一行作廢；爐裡還有東西就重問一次說明。
  // 不修剪的話，爐子看起來是空的（畫的時候找不到它），forgeReady() 卻照 id 數、開爐亮著，說明也是舊的
  function trimPot() {
    if (!trimForgeSel()) return;
    S.forgeLine = "";
    S.forgePreview = null;
    if (S.forgeSel.length) updateForgeLine();
  }

  // 重抓之後，爐裡放的若已經不在了（熔掉、別處用掉）就拿掉；有拿掉回 true
  function trimForgeSel() {
    const arts = new Set((S.menxia?.owned_arts || []).map((a) => a.id));
    const held = new Set((S.menxia?.insights || []).map((i) => i.id));
    const keep = S.forgeSel.filter((p) => (p.type === "art" ? arts : held).has(p.id));
    const trimmed = keep.length !== S.forgeSel.length;
    S.forgeSel = keep;
    if (S.forgeLock && !keep.some(isLocked)) S.forgeLock = null; // 鎖著的那一樣不在爐裡了：鎖也解開
    return trimmed;
  }

  registerPage("craft", { render: pageCraft });

  // 功法清單的篩選（FB-085）：煉製頁一排四顆（全部／內功／武學／意境）；修練頁用卷軸卡自己的庫篩選（libFilter，也記在 localStorage）。
  // 選擇記在這個瀏覽器的 localStorage（存不了就只在這一頁有效，讀不到就當沒選過）。
  // 排序是伺服器排好的（skillview.art_rows：身上的先，再品質、成、名字），兩頁畫的是同一份，這裡只決定哪些要畫
  const ART_FILTERS = ["全部", "內功", "武學", "意境"];
  const filterKey = (page) => `tx-arts-filter-${page}`;
  function artFilter(page) {
    // 序章的煉製頁（第 4 步要放進爐子的基礎拳腳與剛悟到的意境）一律全列：瀏覽器記著的是上一個角色的篩選，不能把師父點名的藏起來
    if (page === "craft" && pro()) return "全部";
    S.artFilter = S.artFilter || {};
    if (!(page in S.artFilter)) {
      let saved = null;
      try { saved = localStorage.getItem(filterKey(page)); } catch (e) { /* 讀不到就當沒選過 */ }
      S.artFilter[page] = ART_FILTERS.includes(saved) ? saved : "全部";
    }
    return S.artFilter[page];
  }
  function setArtFilter(page, value) {
    if (!ART_FILTERS.includes(value)) return;
    S.artFilter = S.artFilter || {};
    S.artFilter[page] = value;
    try { localStorage.setItem(filterKey(page), value); } catch (e) { /* 存不了就只在這一頁有效 */ }
  }
  // 這一頁現在的篩選下，這一門武學要不要畫（選「意境」時武學一門都不畫）。煉製頁的意境一律畫：它是拿一門武學配一個意境的地方，
  // 「內功」「武學」篩選不把意境整排藏起來（沒有提示會讓人以為意境不見了）；修練頁的庫另有卷軸卡的篩選（libFilter）
  function showArts(page, art) {
    const f = artFilter(page);
    return f === "全部" || f === art.kind;
  }
  // 四顆小鈕排一行，併在煉製頁「功法」那一行標籤裡（第一屏不多一行）
  function filterChips(page) {
    if (page === "craft" && pro()) return ""; // 序章裡沒有篩選可選（artFilter 一律全列），不畫鈕
    const now = artFilter(page);
    return `<span class="fchips" role="group" aria-label="篩選">${ART_FILTERS.map((f) => `<button type="button" class="fchip${f === now ? " on" : ""}" data-act="art-filter" data-page="${page}" data-filter="${f}" aria-pressed="${f === now}">${f}</button>`).join("")}</span>`;
  }
  async function craftClick(act, el, ev) {
    switch (act) {
        case "secret-close": document.getElementById("sp-pop")?.remove(); break;
        case "secret-book": document.getElementById("sp-pop")?.remove(); S.bookFrom = window.scrollY; S.book = "arts"; render(); document.querySelector(".book-layer")?.scrollTo(0, 0); break;
        case "book-open": S.bookFrom = window.scrollY; S.book = el.dataset.book === "forge" ? "forge" : "arts"; render(); document.querySelector(".book-layer")?.scrollTo(0, 0); break;
        case "book-close": S.book = false; render(); window.scrollTo(0, S.bookFrom || 0); break;
        case "create-kind": { const c = S.main.status.create; S.createPick = { kind: el.dataset.val, form: "" }; if (c) renderPage(); break; }
        case "create-pick": { if (S.createPick) S.createPick.form = el.dataset.val; renderPage(); break; }
        case "create-begin": if (S.createPick && S.createPick.form) await mx("create_begin", { kind: S.createPick.kind, form: S.createPick.form }); break;
        case "create-preset": { // 起手的幾個架式：套上再拖
          const p = ((S.main.status.create || {}).presets || []).find((q) => q.name === el.dataset.val);
          if (p) { S.createPose = { ...p.angles }; const svg = document.getElementById("create-rig"); if (svg) rigRedraw(svg); }
          break;
        }
        case "create-pose": if (S.createPose) await mx("create_pose", { pose: S.createPose }); break;
        case "create-intent": await createIntent(); break;
        case "create-back": await mx("create_back", { to: el.dataset.to }); break;
        case "create-name": {
          const n = document.getElementById("create-name"), m = document.getElementById("create-move");
          document.activeElement?.blur?.(); // 手機的鍵盤先在這一下收起，不要等換頁那一刻才收、整頁再跳一次
          await mx("create_name", { name: n ? n.value.trim() : "", move: m ? m.value.trim() : "" }); break; // 立好了 mx 直接回修練頁
        }
        case "create-cancel": await createCancel(); break; // 付過心得的先問一次（3.1）
        case "create-reroll": await mx("create_reroll"); break; // 重悟帖：留在成形那一步，三格換了
        case "create-reread": await createReread(); break; // 重悟帖的第二個用法：重讀這句意（Joy 2026-10-22）
        case "create-open": S.createOpen = true; S.message = ""; renderPage(); window.scrollTo(0, 0); break;
        case "create-close": S.createOpen = false; S.message = ""; renderPage(); window.scrollTo(0, 0); break;
        case "art-filter": setArtFilter(el.dataset.page, el.dataset.filter); renderPage(); break;
        case "pick": pick(el.dataset.type, el.dataset.id); break;
        case "unslot": if (S.busy) break; if (isLocked(S.forgeSel[Number(el.dataset.i)])) S.forgeLock = null; S.forgeSel.splice(Number(el.dataset.i), 1); S.forgePicks = null; S.forgePreview = null; renderPage(); updateForgeLine(); break;
        case "pot-lock": if (S.busy) break; toggleLock(Number(el.dataset.i)); break;
        case "forge": await forge(); break;
        case "craft-all": craftView().all = true; renderPage(); break;
        case "pot-open": if (S.busy) break; if (S.forgeSel.length >= 2) { toast("爐裡已經放滿了，點上面的拿出來再換。"); break; } S.craftPick = true; renderPage(); break;
        case "pot-close": S.craftPick = false; renderPage(); break; // 縮起來的爐子底下的預覽：捲回去看整張卡
        case "craft-ok": craftView().okOnly = !craftView().okOnly; renderPage(); break;
        case "forge-hub":
          if (forgeReady()) await forge();
          else toast("放一門武學和一個意境，或兩門武學，或兩個意境。");
          break;
    } // craftClick
  } // craftClick
  registerClicks(craftClick, ["secret-close", "secret-book", "book-open", "book-close", "create-kind", "create-pick", "create-begin", "create-preset", "create-pose", "create-intent", "create-back", "create-name", "create-cancel", "create-reroll", "create-reread", "create-open", "create-close", "art-filter", "pick", "unslot", "pot-lock", "forge", "craft-all", "pot-open", "pot-close", "craft-ok", "forge-hub"]);
  async function craftChange(ev) {
    if (ev.target.dataset && ev.target.dataset.act === "craft-view") { // 煉製頁的屬性、品質、排序
      const v = craftView();
      v[ev.target.dataset.key] = ev.target.value;
      v.all = false;
      renderPage();
    }
  } // craftChange
  registerChanges(craftChange);

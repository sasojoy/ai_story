/* 天下大勢的網頁前端：修練（功能包 tianxia/features/cultivation/，開發規範手冊 3.7、G9）。
 *
 * 俠客頁（pagePractice）：武學、裝備、門下、屬性四個分頁、功法庫與篩選、批量熔煉、意境槽、武學卡上的絕招、破境動畫與破境卡（ascendCard）的畫法。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；/ 的 script 標籤由伺服器照 FEATURES 生成，這支排在 app.js 前面。
 * 全部拆包第 64 批從 app.js 逐行切出來（計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第64批.md）。點擊、表單、change 用 registerClicks、registerForms、registerChanges 登記在這支檔；renderPage 照舊在 app.js（殼）。
 */
"use strict";

  const KINDS = ["武學", "內功"];

  // ── 修練 ──
  // 卷軸卡版（企劃者 2026-10-06「先用捲軸卡」）：身上的兩門各一張卡，練成、修練直接在卡上按；
  // 功法庫一門一列，點開才攤成同一張卡的內容。武學多（上限 50 門）時庫可以篩選，先只列 LIB_PAGE 門，其餘按「再列 N 門」

  const LIB_PAGE = 8;
  const LIB_FILTERS = [["all", "全部"], ["武學", "武學"], ["內功", "內功"], ["ready", "可修練"]];

  // 庫的篩選記在這個瀏覽器的 localStorage（FB-085）：重新整理、換頁回來還是上次選的；存不了就只在這一頁有效，讀不到就當沒選過
  const LIB_FILTER_KEY = "tx-arts-filter-practice";
  function libFilter() {
    if (!LIB_FILTERS.some(([f]) => f === S.libFilter)) {
      let saved = null;
      try { saved = localStorage.getItem(LIB_FILTER_KEY); } catch (e) { /* 讀不到就當沒選過 */ }
      S.libFilter = LIB_FILTERS.some(([f]) => f === saved) ? saved : "all";
    }
    return S.libFilter;
  }
  function setLibFilter(value) {
    if (!LIB_FILTERS.some(([f]) => f === value)) return;
    S.libFilter = value;
    S.libAll = false; // 換一類，「再列 N 門」從頭算
    try { localStorage.setItem(LIB_FILTER_KEY, value); } catch (e) { /* 存不了就只在這一頁有效 */ }
  }

  // ── 批量熔煉的判斷資料、篩選與排序（企劃者 2026-10-16「批量分解的時候無法判斷武學或內功意境的好壞……甚至是能篩選條件」）──
  // 勾的時候武學、內功、意境排成同一張清單（meltItems）：每一列寫判斷好壞要的（威力、比身上強弱、境界、功效、絕招；意境寫幾重、圓融駁雜、正邪）
  // 與熔了退多少心得，點右邊的 ▾ 攤開細節。篩選與排序只記在這一頁（S.meltView），不存瀏覽器
  const MELT_SORTS = [["", "原本的順序"], ["power", "威力低的在前"], ["quality", "品質低的在前"], ["value", "心得多的在前"]];
  const MELT_RANKS = ["", "一重", "二重", "三重"]; // 意境（技能）的強度：揣摩一次加一重（Joy 2026-10-20「●好醜」）
  const MELT_NO_GEN = "未合成"; // 境界是空字串（基礎、內容寫的武學）時篩選上寫的字
  function meltView() {
    S.meltView = S.meltView || { kind: "", attr: "", quality: "", gen: "", rank: "", weak: false, sort: "" };
    return S.meltView;
  }
  // 功法庫（身上以外的）與意境排成一份；伺服器沒給 judge（舊版）時那幾欄空著
  function meltItems(x) {
    const arts = x.owned_arts.filter((a) => !a.worn).map((a) => {
      const j = a.judge || {};
      return { t: "arts", id: a.id, name: a.name, kind: a.kind, attr: a.attribute, quality: a.quality, gen: a.gen || "", rank: 0,
        ok: !!a.melt.ok, why: a.melt.ok ? "" : a.melt.note || "", value: a.melt.value | 0, power: typeof j.power === "number" ? j.power : null,
        diff: typeof j.worn_diff === "number" ? j.worn_diff : null, j, a };
    });
    const ins = x.insights.map((i) => ({ t: "ins", id: i.id, name: i.name, kind: "意境", attr: i.attribute, quality: "", gen: "",
      rank: i.rank | 0 || (MELT_RANKS.indexOf(String(i.depth || "").split("・")[0]) > 0 ? MELT_RANKS.indexOf(String(i.depth).split("・")[0]) : 0),
      ok: !i.blocked, why: i.blocked || "", value: i.melt | 0, power: null, diff: null, i }));
    return [...arts, ...ins];
  }
  function meltPass(it, v) {
    return (!v.kind || it.kind === v.kind) && (!v.attr || it.attr === v.attr) && (!v.quality || it.quality === v.quality)
      && (!v.gen || (it.t === "arts" && (it.gen || MELT_NO_GEN) === v.gen)) && (!v.rank || it.rank === Number(v.rank))
      && (!v.weak || (it.diff !== null && it.diff < 0));
  }
  // 篩出來的、照排序排好；沒有那一項的（意境沒有威力、品質）排在最後，其餘照原本的順序（伺服器排好的）
  function meltShown(x) {
    const v = meltView();
    const list = meltItems(x).filter((it) => meltPass(it, v));
    const key = v.sort === "power" ? (it) => it.power : v.sort === "quality" ? (it) => (it.quality ? QUALITY_RANK[it.quality] * 10 + (it.quality === "絕學" ? 1 : 0) : null)
      : v.sort === "value" ? (it) => -it.value : null;
    if (!key) return list;
    return list.map((it, n) => [it, key(it), n]).sort((p, q) => (p[1] === null) - (q[1] === null) || (p[1] === null ? 0 : p[1] - q[1]) || p[2] - q[2]).map((p) => p[0]);
  }
  // 「勾選篩出來的全部」：篩出來、熔得掉的全勾；都已經勾了再按一次全部取消
  function meltPickShown() {
    if (!S.meltSel || !S.menxia) return;
    const shown = meltShown(S.menxia).filter((it) => it.ok);
    const all = shown.length && shown.every((it) => S.meltSel[it.t].includes(it.id));
    const next = { ...S.meltSel };
    for (const t of ["arts", "ins"]) {
      const ids = shown.filter((it) => it.t === t).map((it) => it.id);
      next[t] = all ? next[t].filter((id) => !ids.includes(id)) : [...new Set([...next[t], ...ids])];
    }
    S.meltSel = next;
    renderPage();
  }
  // 篩選一格一個下拉（375 寬兩欄排）：只有兩種以上的值才畫；已經選了的那一格照畫，才改得回來
  function meltFilterHtml(x) {
    const v = meltView(), items = meltItems(x);
    const vals = (f) => [...new Set(items.map(f).filter((s) => s !== "" && s !== null))];
    const qrank = (q) => (QUALITY_RANK[q] || 0) * 10 + (q === "絕學" ? 1 : 0);
    const cells = [
      ["kind", "種類", vals((it) => it.kind).sort((a, b) => ["武學", "內功", "意境"].indexOf(a) - ["武學", "內功", "意境"].indexOf(b)).map((k) => [k, k])],
      ["attr", "屬性", vals((it) => it.attr).sort().map((a) => [a, `屬${a}`])],
      ["quality", "品質", vals((it) => it.quality).sort((a, b) => qrank(a) - qrank(b)).map((q) => [q, q])],
      ["gen", "境界", vals((it) => (it.t === "arts" ? it.gen || MELT_NO_GEN : "")).sort((a, b) => ["未合成", "初成", "精進", "化境"].indexOf(a) - ["未合成", "初成", "精進", "化境"].indexOf(b)).map((g) => [g, g])],
      ["rank", "強度", vals((it) => (it.t === "ins" && it.rank ? it.rank : "")).sort().map((r) => [String(r), MELT_RANKS[r] || `${r}重`])],
    ].filter(([key, , opts]) => opts.length > 1 || v[key]);
    const sel = (key, label, opts) => `<label><span>${label}</span><select class="input" data-act="melt-view" data-key="${key}" aria-label="${label}">
      <option value="">全部</option>${opts.map(([val, text]) => `<option value="${esc(val)}"${v[key] === val ? " selected" : ""}>${esc(text)}</option>`).join("")}</select></label>`;
    const weak = items.some((it) => it.diff !== null);
    return `<div class="melt-filter">${cells.map(([key, label, opts]) => sel(key, label, opts)).join("")}
      <label><span>排序</span><select class="input" data-act="melt-view" data-key="sort" aria-label="排序">${MELT_SORTS.map(([val, text]) =>
        `<option value="${val}"${v.sort === val ? " selected" : ""}>${text}</option>`).join("")}</select></label>
      ${weak || v.weak ? `<button type="button" class="fchip melt-weak${v.weak ? " on" : ""}" data-act="melt-weak" aria-pressed="${!!v.weak}">只看比身上弱的</button>` : ""}</div>`;
  }

  // 一列：左邊勾＋品質印＋名字、判斷的一行、幾個小籤；右邊心得與攤開鈕。熔不掉的灰掉、原因寫在籤那一行
  function meltRowHtml(it, on, open) {
    const act = it.t === "arts" ? "melt-pick" : "melt-pick-ins";
    const mark = it.t === "arts" ? seal(it.quality) : '<span class="qseal qi">意</span>';
    let sub, tags = [];
    if (it.t === "arts") {
      const j = it.j;
      sub = [it.kind, `屬${it.attr}`, it.gen, `${it.a.level}成`, it.power !== null ? `威力 ${it.power}` : ""].filter(Boolean);
      if (it.diff !== null) tags.push(it.diff > 0 ? `<i class="up">比身上強 ${meltNum(it.diff)}</i>` : it.diff < 0 ? `<i class="down">比身上弱 ${meltNum(it.diff)}</i>` : "<i>跟身上一樣</i>");
      if (j.tactic) tags.push(`<i class="hi">${tsealHtml(j.tactic_title || "本命")}${esc(j.tactic)}</i>`);
      if (j.ultimate) tags.push(`<i class="hi">${tsealHtml("絕")}${esc(j.ultimate)}</i>`);
      const tr = j.traits || [];
      tr.slice(0, 2).forEach((t) => tags.push(`<i>${esc(t.name)}${t.layers > 1 ? t.layers : ""}</i>`));
      if (tr.length > 2) tags.push(`<i>+${tr.length - 2}</i>`);
      if (j.special) tags.push(`<i class="hi">${esc(j.special)}</i>`);
    } else {
      const i = it.i;
      sub = ["意境", `屬${it.attr}`, ...String(i.depth || "").split("・"), i.lean && i.lean !== "無" ? i.lean : ""].filter(Boolean);
    }
    if (!it.ok) tags = [`<i class="why">${esc(it.why)}</i>`];
    const key = `${it.t}:${it.id}`;
    return `<div class="mrow${on ? " on" : ""}${it.ok ? "" : " off"}">
      <button class="mpick pick${on ? " on" : ""}" data-act="${act}" data-id="${esc(it.id)}" ${it.ok ? "" : "disabled"} aria-pressed="${on}">
        <i class="tick" aria-hidden="true"></i>${mark}<span class="txt"><b>${esc(it.name)}</b><small>${sub.map((w) => `<span>${esc(w)}</span>`).join("・")}</small>${tags.length ? `<span class="tags">${tags.join("")}</span>` : ""}</span>
        <span class="mval">${it.ok ? (it.value > 0 ? `心得<b>${it.value}</b>` : "沒有心得") : ""}</span></button>
      <button class="mmore${open ? " on" : ""}" data-act="melt-open" data-key="${esc(key)}" aria-expanded="${open}" aria-label="${esc(it.name)}的細節">${open ? "▾" : "›"}</button>
    </div>${open ? `<div class="mdetail">${meltDetailHtml(it)}</div>` : ""}`;
  }
  function meltDetailHtml(it) {
    const lines = [];
    if (it.t === "arts") {
      const j = it.j, a = it.a;
      lines.push(`第${a.level}成${it.power !== null ? `，威力 ${it.power}` : ""}${a.affinity ? `・收${esc(a.affinity)}` : ""}${scoreText(a)}`);
      if ((a.slots || []).length) lines.push(`意境槽 ${a.slots.length} 格：${a.slots.map((t) => (t ? `「${esc(t.name)}」〔${esc(t.skill)}〕${esc(t.mark)}` : "空")).join("、")}`);
      if ((j.traits || []).length) lines.push(`功效：${j.traits.map((t) => `〔${esc(t.name)}〕${t.layers > 1 ? `${t.layers} 層` : ""}`).join("")}`);
      if (j.special) lines.push(`特別功效〔${esc(j.special)}〕`);
      if (j.ultimate) lines.push(`${tsealHtml("絕")}〔${esc(j.ultimate)}〕`);
      if (j.tactic) lines.push(`${tsealHtml(j.tactic_title || "本命")}〔${esc(j.tactic)}〕`);
      if (a.compare) lines.push(esc(a.compare));
      if (a.relearn) lines.push(esc(a.relearn));
    } else {
      const i = it.i;
      lines.push(["意境", `屬${esc(it.attr)}`, esc(i.depth || ""), i.lean && i.lean !== "無" ? esc(i.lean) : ""].filter(Boolean).join("・"));
      if (i.note) lines.push(esc(i.note));
      if (i.own) lines.push(`悟於${esc(i.place || "某處")}・只屬於你`);
    }
    lines.push(it.ok ? (it.value > 0 ? `熔了退回心得 ${it.value}` : "熔了沒有心得，只空出一格") : esc(it.why));
    return lines.map((l) => `<p>${l}</p>`).join("");
  }

  // 剪影照性別與這一季挑的成長（HERO_FIGURES.growth）；遊俠、自己配、還沒挑的照舊用遊俠那張
  const heroFigure = (s) => {
    const sex = s && s.gender === "女" ? "女" : "男";
    const k = s && s.growth && s.growth.chosen, alt = k && HERO_FIGURES.growth[k];
    if (!alt) return HERO_FIGURES[sex];
    const f = alt[sex];
    return { src: `/static/img/growth/${k}-${sex === "女" ? "f" : "m"}.webp`, ratio: f.ratio,
      nodes: f.nodes.map(([key, x, y, side]) => ({ key, kind: "art", x, y, side })) };
  };

  // 一個光點此刻的樣子：標籤、有沒有東西（沒有的點暗著）、底下那一格的標題、說明、按鈕
  function heroInfo(n, x, s) {
    if (n.kind === "art") {
      const a = x.owned_arts.find((r) => r.worn && r.kind === n.key);
      if (!a) return { label: n.key, lit: false, title: n.key, desc: `你身上還沒有${n.key}。`, button: "" };
      const move = moveOf(a.tactic);
      return {
        // 招式與絕學稿案第四輪：亮點旁邊直接寫名字，武學與內功多寫那一招；成數、階數、屬性都不寫
        // 序章指路：卡裡的鈕收進抽屜了，光點自己也帶那幾個鍵（練成看那一欄按不按得下去；applyGlow 只亮這一步的）
        label: `${a.name}${move ? `〔${move}〕` : ""}`, name: a.name, move, lit: true, glow: [...["switch", "cultivate", "melt", "slot"].filter((k) => (a.glow || []).includes(k)), ...(practiceOk(x, n.key) ? ["practice"] : [])],
        title: `${esc(a.name)}<small>${esc(a.quality)}</small>`,
        desc: `${n.key}・屬${a.attribute}・第${a.level | 0}成${a.insight ? `・意境「${a.insight}」` : ""}`,
        button: `<button class="btn small" data-act="hero-jump" data-to="worn" data-kind="${esc(n.key)}">看這一門</button>`,
      };
    }
    const g = x.gear && x.gear.slots.find((sl) => sl.slot === n.key);
    if (!g) return null; // 這一欄關著：不畫這個點
    const label = g.label || HERO_GEAR_NAMES[n.key];
    if (!g.worn) return { label, lit: false, title: label, desc: g.empty || "", button: "" };
    const w = g.worn;
    const desc = n.key === "weapon" ? `${w.noun || w.kind}・屬${w.attribute}${w.grade ? `・${w.grade}` : ""}・鋒利度 ${w.edge | 0}${w.bonus ? `・威力 ${w.bonus}` : "・用不上"}`
      : n.key === "armor" ? `屬${w.attribute}・${w.grade}・${w.wear_word} ${w.edge | 0}・少扣 ${w.cut} 氣血`
      : n.key === "mount" ? `${w.grade}・${w.wear_word} ${w.edge | 0}・疾行省 ${w.save} 體力・路上快 ${w.speed}`
      : w.effect_text || "";
    return {
      label: w.name, lit: true,
      title: `【${esc(w.name)}】<small>${esc(label)}</small>`,
      desc,
      button: `<button class="btn small" data-act="hero-jump" data-to="gear" data-kind="${esc(n.key)}">看這件</button>`,
    };
  }
  const practiceOk = (x, kind) => { const c = (x.slot_cards || []).find((sl) => sl.kind === kind); return !!c && c.learned !== false && !c.blocked && !c.maxed; };
  function heroPanel(x, s) {
    const fig = heroFigure(s);
    // 「俠客」頁（減法季批 1，圖解版第 33 頁）：四欄裝備畫在人像的四個角（selfCorners），身上只留兩門的光點
    const nodes = fig.nodes.filter((n) => n.kind === "art").map((n) => [n, heroInfo(n, x, s)]).filter(([, info]) => info);
    const corners = selfCorners(x, s);
    if (!nodes.length && !corners) return "";
    // 點了開抽屜（practiceDrawer）；抽屜開著的那一個亮著
    const open = S.pdrawer && (S.pdrawer.t === "worn" || S.pdrawer.t === "gear") ? S.pdrawer.key : null;
    return `<section class="hero" aria-label="人物">
      <div class="hero-hd">
        <div><div class="hero-name">${esc(s.name)}</div><div class="hero-tag">${esc(s.affiliation)}</div></div>
        <div class="hero-sub"><div>第 ${s.level | 0} 級</div>${(typeof uiV2 === "function" && uiV2()) && !pro() ? "" : `<div>氣血 ${s.hp | 0}／${s.hp_max | 0}</div>`}${typeof x.might === "number" ? `<div class="hero-might">戰力 <b>${x.might | 0}</b></div>` : ""}${heroAnnalsHtml()}</div>
      </div>
      <div class="hero-stage">
        <div class="hero-halo" aria-hidden="true"></div>
        <div class="hero-fig" style="aspect-ratio:${fig.ratio}">
          <img src="${fig.src}" alt="" draggable="false">
          ${nodes.map(([n, info]) => `<button class="hero-node${n.key === open ? " on" : ""}${info.lit ? "" : " dim"} ${n.side}" style="left:${n.x}%;top:${n.y}%" data-act="hero-node" data-kind="${n.kind}" data-key="${esc(n.key)}"${info.glow && info.glow.length && n.key !== open ? ` data-glow="${info.glow.join(" ")}"` : ""} aria-label="${esc(info.label)}"><i class="pulse"></i><i class="dot"></i><span>${info.move ? `${esc(info.name)}<small>〔${esc(info.move)}〕</small>` : esc(info.label)}</span></button>`).join("")}
        </div>
        ${corners}
      </div>
    </section>`;
  }
  // ── 「俠客」頁（減法季批 1，整合設計 6.5；圖解版第 33、34 頁）：修練頁的上半換成人像四角的四欄裝備、身上兩門的成數條（絕學金框、朱印「絕」）、
  // 心得名望善惡與五項屬性（以前在狀態列，6.2 搬來）、底下三個入口（煉製、自創武學、榜單；行狀、名帖匣是一行小字）。規則一個字都沒改：
  // 點什麼都是原本那一格（抽屜、煉製頁、自創頁、見聞那一段）。字待 joy 潤
  const SELF_CORNERS = [["weapon", "tl"], ["mount", "tr"], ["armor", "bl"], ["treasure", "br"]];

  // 門下卡攤開那一塊：角色卡（member_card）拿掉卡頭已經寫了的（名字、等級氣血、內功、武學；本人的四欄裝備在「裝備」那一段），
  // 只留本命戰法、傳功、加成那幾行；都拿掉了就不畫
  const MATE_DUP = /^(第 \d+ 級|內功|武學|兵器|防具|坐騎|寶物|部下：|威力)/;
  function mateExtra(html) {
    const body = String(html || "").replace(/<h3>[\s\S]*?<\/h3>/, "").replace(/<\/?p>/g, "");
    const lines = body.split(/<br\s*\/?>/).map((t) => t.trim()).filter((t) => t && !MATE_DUP.test(t.replace(/<[^>]+>/g, "")));
    return lines.length ? `<p class="mate-lines">${lines.join("<br>")}</p>` : "";
  }
  const MATE_ROLES = { 本人: "self", 出戰: "fight", 候命: "home", 部下: "follow" }; // 門下卡左邊那枚印的顏色
  function selfCorners(x, s) {
    if (!x.gear) return "";
    const cells = SELF_CORNERS.map(([key, at]) => {
      const g = x.gear.slots.find((sl) => sl.slot === key);
      if (!g) return "";
      const name = g.worn ? g.worn.name : (g.label || HERO_GEAR_NAMES[key]);
      return `<button class="self-gear ${at}${g.worn ? "" : " empty"}" data-act="hero-node" data-kind="gear" data-key="${key}" aria-label="${esc(g.label || HERO_GEAR_NAMES[key])}：${esc(g.worn ? g.worn.name : "空著")}">`
        + `<svg viewBox="0 0 24 24" aria-hidden="true">${GEAR_ICONS[key]}</svg><span>${esc(name)}</span></button>`;
    }).join("");
    return cells ? `<div class="self-gears">${cells}</div>` : "";
  }
  const CN_TENTHS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
  // 武學的成數畫成一筆乾墨（UI 手感戊批，Joy 2026-11-08 看畫稿說可以；以前是十個小方格）：墨走到現在的成數，筆頭蓋一枚小朱印寫「幾成」，
  // 底下九道細刻度（五成那一道長一點）；絕學是金墨，十成的印寫「大成」。沒練過（零成）只有底下那一道淡墨與刻度
  const SA_X0 = 5, SA_X1 = 284; // 墨從哪裡起、十成到哪裡（viewBox 320 寬，右邊留給印）
  function saInk(lv, top) {
    const end = SA_X0 + ((SA_X1 - SA_X0) * lv) / 10;
    const ticks = Array.from({ length: 9 }, (_, k) => { const x = (SA_X0 + ((SA_X1 - SA_X0) * (k + 1)) / 10).toFixed(1); return k === 4 ? `<rect x="${x}" y="24" width="1.8" height="7"/>` : `<rect x="${x}" y="25" width="1.4" height="5"/>`; }).join("");
    const ink = top ? "#8a611a" : "#2a241d", ink2 = top ? "#c9952f" : "#3a3128", seal = top ? "#b7862b" : "#a8322a";
    const d = `M${SA_X0} 18.5 Q${((SA_X0 + end) / 2).toFixed(1)} 15.5 ${end.toFixed(1)} 17.6`;
    const stroke = lv > 0 ? `<path d="${d}" stroke="${ink}" stroke-width="10" stroke-linecap="round" fill="none"/><path d="${d}" stroke="${ink2}" stroke-width="4" stroke-linecap="round" fill="none" opacity=".55"/>`
      + `<path d="${d}" stroke="#fbf7ef" stroke-width="1.2" stroke-dasharray="14 9 30 6 22 11" fill="none" opacity=".5" transform="translate(0 -2)"/>`
      + `<path d="${d}" stroke="#fbf7ef" stroke-width=".9" stroke-dasharray="9 13 24 7" fill="none" opacity=".4" transform="translate(0 2.6)"/>` : "";
    const word = lv >= 10 && top ? "大成" : `${CN_TENTHS[lv]}成`;
    const stamp = lv > 0 ? `<g transform="translate(${Math.min(288, end + 3).toFixed(1)} 4)"><rect width="30" height="22" rx="3" fill="${seal}"/><rect x="2" y="2" width="26" height="18" rx="2" fill="none" stroke="#f6e3cc" stroke-width="1"/>`
      + `<text x="15" y="15.2" text-anchor="middle" font-size="10.5" font-weight="700" fill="#fdf3e4">${word}</text></g>` : "";
    return `<svg class="sa-ink" viewBox="0 0 320 34" aria-hidden="true"><path d="M4 18 Q160 15 316 18" stroke="#d9ccb2" stroke-width="7" stroke-linecap="round" fill="none" opacity=".75"/>`
      + `<g fill="#b8a888">${ticks}</g>${stroke}${stamp}</svg>`;
  }
  // 「武學」那一段（俠客頁重排，Joy 2026-10-24）：小標題右邊一顆「功法庫 N/M・意境 K ›」（攤開底下的功法庫摺疊、捲過去），
  // 底下身上兩門的成數條：點了開那一門的抽屜（同人像上的光點）。絕學金框、左邊一枚朱印「絕」，底下一句破境那一行的話
  function selfArtsHtml(x) {
    const worn = KINDS.map((k) => x.owned_arts.find((a) => a.worn && a.kind === k)).filter(Boolean);
    const lib = x.holdings ? `<button class="linkish" data-act="self-sec" data-sec="lib">功法庫 ${x.holdings.count | 0}/${x.holdings.cap | 0}・意境 ${(x.insights || []).length} ›</button>` : "";
    const head = `<div class="self-hd"><h3>武學</h3>${lib}</div>`;
    if (!worn.length) return `<section class="self-sec" aria-label="武學">${head}<p class="muted">你身上還沒有武學。</p></section>`;
    const hm = S.main && S.main.hero_move;
    return `<section class="self-sec" aria-label="武學">${head}<div class="self-arts">${worn.map((a) => {
      const lv = Math.max(0, Math.min(10, a.level | 0)), top = a.quality === "絕學";
      const note = top ? (a.cultivate && (a.cultivate.legend ? a.cultivate.legend.note : a.cultivate.note)) || "" : "";
      const card = `<button class="self-art${top ? " q4" : ""}" data-act="hero-node" data-kind="art" data-key="${esc(a.kind)}">${top ? '<span class="qseal q4 big">絕</span>' : ""}`
        + `<span class="sa-body"><span class="sa-hd"><b>${esc(a.name)}</b><small>${top ? "絕學" : esc(a.kind)}・第${CN_TENTHS[lv]}成</small></span>`
        + `${note ? `<small class="sa-note">${esc(note)}</small>` : ""}<i class="sa-ten" role="meter" aria-valuemin="0" aria-valuemax="10" aria-valuenow="${lv}" aria-label="${esc(a.name)}第${lv}成">${saInk(lv, top)}</i></span></button>`;
      // 絕招掛在「武學」那一門底下（跟著手上的打法走；內功不掛）
      return a.kind === "武學" && hm ? `<div class="self-art-wrap${top ? " q4" : ""}">${card}${heroMoveHtml(hm, a)}</div>` : card;
    }).join("")}</div></section>`;
  }
  // 俠客頁武學卡底下的絕招（Joy 2026-11-03「俠客頁面的武學那邊，是不是應該跟絕招動畫做聯動」，示意稿 CZbfm371…；main.hero_move）：
  // 穿著、打法對得上：「演一次」在卡上直接演（arena_scene.js 的 scenePreview，同萬寶閣那一塊畫布），旁邊「換一招」去萬寶閣絕招那一頁；
  // 穿著、打法不對：寫一句擂台上不會演、連過去換；沒穿：招式庫有招的叫你去換上，沒有的叫你去寫一招
  function heroMoveHtml(hm, a) {
    const w = hm.worn, go = (text) => `<button class="linkish hm-go" data-act="hero-move-go" data-style="${esc(hm.style || "")}">${esc(text)} ›</button>`;
    if (!w) {
      const say = hm.count ? `招式庫有 ${hm.count | 0} 招，身上沒穿` : "寫一句長什麼樣子，擂台與決戰放手一搏就照它演";
      const link = hm.count ? "去換上" : hm.has_art ? `替「${hm.art || a.name}」寫一招` : "去萬寶閣看看";
      return `<div class="hm-strip empty"><span class="hm-seal" aria-hidden="true">絕</span><span class="hm-main"><b>還沒有絕招</b><small>${esc(say)}</small></span></div>
        <div class="hm-foot">${go(link)}</div>`;
    }
    const on = S.heroMoveShow === w.id;
    const play = w.show ? `<button class="btn small ${on ? "primary" : "ghost"} hm-play" data-act="hero-move-show" data-id="${esc(w.id)}">${on ? "收起 ■" : "演一次 ▶"}</button>` : "";
    const sub = w.plays ? `${esc(w.style_text)}・擂台與決戰放手一搏都演這一招` : `${esc(w.style_text)}・你現在的打法是${esc(hm.style_text)}，擂台上不會演`;
    return `<div class="hm-strip"><span class="hm-seal on" aria-hidden="true">絕</span><span class="hm-main"><b>絕招「${esc(w.name)}」</b><small>${sub}</small></span>${play}</div>
      ${on ? `<div class="hm-stage"><canvas id="scene-preview" class="scene-preview" width="720" height="320" aria-label="絕招「${esc(w.name)}」演一次"></canvas></div>` : ""}
      ${w.asleep_text ? `<p class="hm-warn">${esc(w.asleep_text)}</p>` : ""}
      <div class="hm-foot">${go(w.plays ? "換一招" : `換一招${hm.style_text}的`)}</div>`;
  }
  async function heroMoveShow(mid) {
    if (!mid || S.heroMoveShow === mid) { S.heroMoveShow = null; render(); return; }
    const r = await api(`/api/looks/scene/${mid}`).catch(() => null);
    if (!r || !r.scene) { toast("這一招演不出來，等一下再試。"); return; }
    S.heroMoveShow = mid;
    render();
    const hm = S.main && S.main.hero_move;
    sceneAsMe(hm && hm.worn ? hm.worn.style : ""); // 台上站的是自己（looks.js）
    if (typeof scenePreview === "function") scenePreview(r.scene, mid);
  }
  // 「換一招」：萬寶閣絕招那一頁、招式庫開那一種打法的分頁（looks.js 的 openMallMoves）。
  // 萬寶閣也用 #scene-preview 那一塊畫布：先把俠客頁這一塊收起來
  async function heroMoveGo(style) {
    S.heroMoveShow = null;
    await openMallMoves(style);
  }
  // 「屬性」那一段（以前在狀態列與點名號攤開的那一塊，整合設計 6.2）：五項一格一欄（名字、數字），有點可配時每格底下一顆「＋」、
  // 小標題右邊寫「可配 N 點」、格子底下一行五項各管什麼（statUsesHtml）；再一行名望、善名、惡名；心得一行在最底下（序章照舊點名號配）
  // compact（介面重整的屬性頁）：名望善惡不在這裡（名聲那一段一份）、五項各管什麼收在「？」後面（S.attrHelp）、心得提示一行（點開看全文，S.xindeOpen）
  function selfStatsHtml(s, compact = false) {
    if (!s || !s.attrs || (!shown("stats") && !shown("xinde"))) return "";
    if (compact) {
      const pts = s.stat_points | 0;
      const cols = s.attrs.map(([k, v, key]) => `<div class="attr"><em>${esc(k)}</em><b>${v}</b>${pts
        ? `<button class="btn small alloc" data-act="allocate" data-stat="${esc(key)}" aria-label="${esc(k)}加一點" ${v >= s.stat_cap ? "disabled" : ""}>＋</button>` : ""}</div>`).join("");
      const help = s.stat_uses ? `<button class="linkish attr-q" data-act="attr-help" aria-expanded="${!!S.attrHelp}" aria-label="五項各管什麼">？</button>` : "";
      const stats = shown("stats") ? `<div class="self-hd"><h3>屬性</h3>${pts ? `<b class="pts">可配 ${pts} 點</b>` : ""}${help}</div><div class="self-attrs">${cols}</div>${S.attrHelp ? statUsesHtml(s) : ""}` : "";
      const tip = s.hint ? `<button class="xinde-tip${S.xindeOpen ? " open" : ""}" data-act="xinde-more" aria-expanded="${!!S.xindeOpen}">${esc(s.hint)}</button>` : "";
      const xinde = shown("xinde") ? `<div class="self-xinde one"><em>心得</em><b>${s.xinde | 0}</b>${tip}</div>` : "";
      return `<section class="self-stats self-sec" aria-label="心得與屬性">${stats}${xinde}</section>`;
    }
    const pts = s.stat_points | 0;
    const cols = s.attrs.map(([k, v, key]) => `<div class="attr"><em>${esc(k)}</em><b>${v}</b>${pts
      ? `<button class="btn small alloc" data-act="allocate" data-stat="${esc(key)}" aria-label="${esc(k)}加一點" ${v >= s.stat_cap ? "disabled" : ""}>＋</button>` : ""}</div>`).join("");
    const minor = (s.minor || []).map(([k, v]) => `<span><em>${esc(k)}</em>${v}</span>`).join("");
    const stats = shown("stats") ? `<div class="self-hd"><h3>屬性</h3>${pts ? `<b class="pts">可配 ${pts} 點</b>` : ""}</div><div class="self-attrs">${cols}</div>${pts ? statUsesHtml(s) : ""}${minor ? `<div class="self-nums">${minor}</div>` : ""}` : "";
    const xinde = shown("xinde") ? `<p class="self-xinde"><em>心得</em><b>${s.xinde | 0}</b>${s.hint ? `<small>${esc(s.hint)}</small>` : ""}</p>` : "";
    return `<section class="self-stats self-sec" aria-label="心得與屬性">${stats}${xinde}</section>`;
  }
  // 功法庫裡沒有閒置的武學（手機介面自檢 U-14）：標題的「3/50」連身上練的與意境一起算，這裡不說「空的」，說清楚那幾格是誰佔的
  function libEmptyHtml(x) {
    const worn = (x.owned_arts || []).filter((a) => a.worn).length, ins = (x.insights || []).length;
    const held = [worn ? `身上練的 ${worn} 門` : "", ins ? `意境 ${ins} 份` : ""].filter(Boolean).join("、");
    const why = held && x.holdings ? `上面的 ${x.holdings.count | 0}/${x.holdings.cap | 0} 是${held}佔的。` : "";
    return `<p class="muted lib-empty">庫裡還沒有閒置的武學。${why}合成出來的武學、學來的武學會放在這裡。</p>`;
  }
  // 「去做」那一段：兩格——煉製（煉製頁）、自創武學（自創頁）。療傷與閉關 Joy 2026-10-25 拿掉：療傷只在醫館做得了，
  // 入口就是江湖頁「此地還能做」的「醫館療傷」（act:heal），這裡再放一顆多半是灰的；閉關現在的玩法用不到。兩個都沒有時整段不畫
  function selfEntriesHtml(x) {
    const c = S.main && S.main.status && S.main.status.create;
    const craft = shown("tab:craft") ? '<button class="btn self-go" data-act="tab" data-tab="craft" data-glow="tab:craft">煉製<small>意境合成、看爐</small></button>' : "";
    // 心得不夠開始自創（還沒起意）：入口灰掉、小字寫還差多少（手機介面自檢 U-04），不讓人進去挑了才在下一步被踢回來
    const create = c && c.on ? `<button class="btn self-go" data-act="create-open"${createShort(c) ? " disabled" : ""}>${c.draft ? "接著自創" : "自創武學"}<small>${createSub(c)}</small></button>` : "";
    if (!craft && !create) return "";
    return `<section class="self-sec" aria-label="去做"><div class="self-hd"><h3>去做</h3></div><div class="self-goes">${craft}${create}</div></section>`;
  }
  // 行狀（自己的傳，見聞那一頁的一段，SELF_NEWS）：人像那張卡右上角一顆「行狀 ›」（Joy 2026-10-24：榜單、名帖匣回見聞；榜單是籤、名帖匣在紀錄底下）
  const heroAnnalsHtml = () => (shown("tab:news") ? SELF_NEWS.filter((n) => !n.when || n.when(S.main)).map((n) => `<button class="linkish hero-annals" data-act="news" data-news="${n.id}">${n.name}${n.id === "mail" && typeof mailUnread === "function" && mailUnread() > 0 ? ` <i class="mail-dot">${mailUnread()}</i>` : ""} ›</button>`).join("") : "");

  // 點光點（招式與絕學稿案第四輪）：從底下升起那一樣的抽屜——武學、內功是那一門的卡（練、槽、改練），裝備是那一欄的裝備庫
  function heroTap(el) {
    S.pdrawer = { t: el.dataset.kind === "art" ? "worn" : "gear", key: el.dataset.key };
    S.artOpen = null; S.insOpen = null;
    renderPage();
  }
  // 卡上那一行「沈〔追風影〕出招・…」裡的招名
  const moveOf = (tactic) => ((/〔([^〕]+)〕/.exec(String(tactic || "")) || [])[1] || "");
  // 那一行開頭的印（看家、本命、絕、私印）
  const sealOf = (tactic) => ((/^([^〔]{1,2})〔/.exec(String(tactic || "")) || [])[1] || "");

  // ── 玉環與火柴人（Joy 2026-10-20：槽分顏色、自創擺式當圖示；草案 https://claude.ai/artifact/54XJZ7jutrsND8YLnyCC4x）──
  // 每一格是一枚玉環：單色一種屬性、雙色斜分兩種、任色八色一圈。顏色照屬性（--at-*，style.css）。
  const ATTR_VAR = { 剛: "gang", 柔: "rou", 快: "kuai", 慢: "man", 陽: "yang", 陰: "yin", 虛: "xu", 實: "shi" };
  function ringHtml(colors, inner, cls) {
    const c = (colors || []).filter((k) => ATTR_VAR[k]);
    const kind = c.length === 0 ? "any" : c.length === 1 ? "one" : "two";
    const style = c.length ? ` style="--a:var(--at-${ATTR_VAR[c[0]]});--b:var(--at-${ATTR_VAR[c[c.length > 1 ? 1 : 0]]})"` : "";
    return `<span class="jring ${kind}${cls ? ` ${cls}` : ""}"${style}><span class="jin">${inner || ""}</span></span>`;
  }

  // 意境效果池（第二批）：一份意境的品質（下中上，玉環右上角一枚小印）與一到兩個效果——一般功效寫名字加三節玉，大獎金底，秘方的特別功效朱底。
  // 資料是伺服器給的 fx（skillview.fx_traits：name、layers、grand、special）
  const Q_SHORT = { 下品: "下", 中品: "中", 上品: "上" };
  const qMark = (q) => (Q_SHORT[q] ? `<em class="iq q-${Q_SHORT[q] === "上" ? 3 : Q_SHORT[q] === "中" ? 2 : 1}" title="${esc(q)}">${Q_SHORT[q]}</em>` : "");
  const FX_LAYERS = ["", "一重", "二重", "三重"];
  // 評分（第三批）：「・評 87」；上品還沒成絕學的寫門檻「・評 87／100」
  const scoreText = (a) => (typeof a.score === "number" ? `・評 ${a.score}` : ""); // 評分沒有上限、不是門檻（Joy 2026-10-20）

  const fxOne = (e) => e.grand ? `<i class="fx grand${e.maybe ? " maybe" : ""}">${esc(e.name)}</i>`
    : e.special ? `<i class="fx sp${e.idle ? " idle" : ""}"${e.idle ? ' title="不發動"' : ""}>${e.idle ? `<s>${esc(e.name)}</s><small>不發動</small>` : esc(e.name)}</i>`
    : `<i class="fx${e.maybe ? " maybe" : ""}">${esc(e.name)}${e.maybe ? "" : lvHtml(e.layers)}</i>`;
  const fxHtml = (fx, cls) => (Array.isArray(fx) && fx.length ? `<span class="fxs${cls ? ` ${cls}` : ""}">${fx.map(fxOne).join("")}</span>` : "");
  // 意境的品相（招式與絕學稿案第五輪）：凡不蓋印，佳藍、珍紫、神金；修練頁的列、抽屜、出爐卡同一枚。底子（下中上）不給玩家看
  const LOOK_CLS = { 凡: "l1", 佳: "l2", 珍: "l3", 神: "l4" };
  const lookSeal = (look, big) => (LOOK_CLS[look] ? `<em class="look ${LOOK_CLS[look]}${big ? " big" : ""}" title="${esc(look)}品">${esc(look)}</em>` : "");
  // 品相的四級一眼看懂（Joy 2026-10-21「合出來我根本看不懂這是不是好的」「沒有直接把珍品還是什麼顯示在剛合好那邊」）：
  // 凡佳珍神排成一條，這一份那一級亮著，底下一句這一級是什麼、再往上要什麼（insight_fx.look 的條件）。字待 joy 潤
  const LOOK_STEPS = [["凡", "一個效果、只有一重"], ["佳", "二重，或兩個效果"], ["珍", "三重，或悟出真意"], ["神", "真意再加三重：最好的一級"]];

  function lookLadder(look, steps = LOOK_STEPS) {
    const at = steps.findIndex(([k]) => k === look);
    if (at < 0) return "";
    const up = steps[at + 1];
    return `<div class="look-ladder"><div class="ll-steps">${steps.map(([k], n) => `<i class="${LOOK_CLS[k]}${n === at ? " on" : n < at ? " past" : ""}">${k}</i>`).join("")}</div>
      <p><b class="${LOOK_CLS[look]}">${esc(look)}品</b>・四品裡第 ${at + 1} 級：${esc(steps[at][1])}。${up ? `再往上是${up[0]}品：${esc(up[1])}。` : ""}</p></div>`;
  }
  // 裝在身上哪一格最強（伺服器 i.best，might.best_place）：會更強寫綠字的戰力，不會寫一句灰字。字待 joy 潤
  function bestLine(i) {
    const b = i.best, now = S.menxia && typeof S.menxia.might === "number" ? S.menxia.might : null;
    if (i.slotted) return "";
    if (!b || now == null || b.might <= now) return '<p class="ic-best">身上兩門裝在哪一格都不會更強。</p>';
    return `<p class="ic-best up">裝進【${esc(b.name)}】第 ${(b.i | 0) + 1} 格${b.swap ? `（換下「${esc(b.swap)}」）` : ""}最強：戰力 ${now | 0} → <b>${b.might | 0}</b></p>`;
  }
  // 意境卡（第五輪第三節）：名字、屬性玉環、品相印；功效籤當摘要，底下每個功效一句白話（大獎金底）；
  // o.fits：「裝進【某門】第 N 格」的鈕（伺服器算好裝得進哪裡，skillview._fits）；o.melt：化成心得；o.reveal：出爐的排場；o.cmp：跟舊的比
  function insightCardHtml(i, o = {}) {
    if (!i) return "";
    const fx = (i.effects || []).map((e) => `<li class="${e.grand ? "grand" : e.special ? `sp${e.idle ? " idle" : ""}` : ""}"><b>${esc(e.name)}${e.grand || e.special ? "" : esc(FX_LAYERS[e.layers] || "")}</b>${e.desc ? `<span>${esc(e.desc)}</span>` : ""}${e.idle && i.idle ? `<em class="idle-why">${esc(i.idle)}</em>` : ""}</li>`).join("");
    const fits = o.fits ? (i.fits || []).map((f) => `<button class="btn small" data-act="slot-in" data-id="${esc(f.art)}" data-i="${f.i | 0}" data-ins="${esc(i.id)}">裝進【${esc(f.name)}】第 ${(f.i | 0) + 1} 格</button>${f.stack ? `<small class="stk">${esc(f.stack)}</small>` : ""}`).join("") : "";
    const where = i.slotted ? `裝在【${esc(i.slotted)}】` : o.fits && !fits ? "身上的武學沒有空格收得下它。" : ""; // 待 joy 潤
    const rare = i.look === "珍" || i.look === "神";
    return `<div class="ins-card${o.reveal ? " reveal" : ""}${o.reveal && rare ? " rare" : ""}">
      <div class="ic-head">${ringHtml([i.attribute], i.own && i.glyph ? glyphSvg(i.glyph, "glyph-mini") : `<b>${esc(String(i.name).slice(0, 1))}</b>`)}<div><b>「${esc(i.name)}」</b><small>屬${esc(i.attribute)}${i.lean && i.lean !== "無" ? `・${esc(i.lean)}` : ""}</small></div>${lookSeal(i.look, true)}</div>
      ${lookLadder(i.look)}
      ${fx ? `<ul class="ic-fx">${fx}</ul>` : fxHtml(i.fx)}
      ${bestLine(i)}
      ${o.cmp ? `<p class="ic-cmp">${esc(o.cmp)}</p>` : ""}
      ${i.note ? `<p class="ic-note">${esc(i.note)}</p>` : ""}
      ${i.own ? `<p class="glyph-from">悟於${esc(i.place || "某處")}・只屬於你</p>` : ""}
      ${where ? `<p class="muted small">${where}</p>` : ""}
      ${fits ? `<div class="ic-fits">${fits}</div>` : ""}
      ${o.melt ? `<div class="ic-melt"><button class="btn small" data-act="melt-insight" data-id="${esc(i.id)}" data-name="${esc(i.name)}" ${i.blocked ? "disabled" : ""}>化成心得 ${i.melt | 0}</button>${i.blocked ? `<small class="muted">${esc(i.blocked)}</small>` : ""}</div>` : ""}
    </div>`;
  }

  // 自創撞到稀有路數的招，伺服器在招那一行後面補「（稀有路數）」（moves.RARE_WORD）：畫成一枚小章（Joy 2026-10-23「玩家要怎樣才知道自己的是」）
  function tacticHtml(text) {
    const RARE_MARK = "（稀有路數）";
    const m = /^([^〔]{1,2})〔/.exec(String(text || ""));
    const body = (s) => esc(s).split(esc(RARE_MARK)).join(`<span class="rare-tag">${esc(RARE_MARK.slice(1, -1))}</span>`);
    return m ? `${tsealHtml(m[1])}${body(String(text).slice(m[1].length))}` : body(text || "");
  }

  // 意境槽：一門武學一排玉環。裝著的環心寫意境的名字、底下〔技能〕與三節玉，點了拆下；空的環照它的顏色畫、底下寫收什麼，
  // 點了在底下攤開手上空著的意境，顏色收得下的點了裝進「這一格」（送 index），收不下的灰掉寫原因。裝、拆都不花東西。
  // 寫死的武學（本命、部下的上品）slots 是空清單，不畫。字待 joy 潤
  // ro：別人的卡（榜單點開的，Joy 2026-10-22）：一樣畫，但格子點不了、不攤意境
  // 同效果好幾份（Joy 2026-10-22「第二份算半」）：格子上那一份算了幾成（skillview.slot_stack_marks，伺服器寫好的字）
  const stkHtml = (t) => (t ? `<small class="stk">${esc(t)}</small>` : "");
  function slotsHtml(a, x, ro = false) {
    if (!Array.isArray(a.slots) || !a.slots.length) return "";
    const colors = Array.isArray(a.colors) ? a.colors : [];
    const pick = !ro && S.slotPick && S.slotPick.art === a.id ? S.slotPick.i : null;
    // 序章裝意境那一步（prologue.art_glow 給師父點名的那一門 "slot"）：空格與可裝的意境亮
    const glowSlot = (a.glow || []).includes("slot") ? ' data-glow="slot"' : "";
    const cells = a.slots.map((s, i) => {
      const c = colors[i] || [];
      if (ro) return s
        ? `<span class="jd full" title="${esc(`「${s.name}」${s.look || ""}・${fxText(s.fx) || s.skill}${s.desc ? `：${s.desc}` : ""}`)}">${ringHtml(c, `<b>${esc(String(s.name).slice(0, 2))}</b>`)}${lookSeal(s.look)}${fxHtml(s.fx, "col") || `<small>〔${esc(s.skill)}〕</small>${lvHtml(s.strength)}`}${stkHtml(s.stack)}</span>`
        : `<span class="jd empty">${ringHtml(c, "", "vacant")}<small class="dim">空著</small></span>`;
      return s
        ? `<button type="button" class="jd full" data-act="slot-out" data-id="${esc(a.id)}" data-ins="${esc(s.id)}" title="${esc(`「${s.name}」${s.look || ""}・${fxText(s.fx) || s.skill}${s.desc ? `：${s.desc}` : ""}（點了拆下）`)}">${ringHtml(c, `<b>${esc(String(s.name).slice(0, 2))}</b>`)}${lookSeal(s.look)}${fxHtml(s.fx, "col") || `<small>〔${esc(s.skill)}〕</small>${lvHtml(s.strength)}`}${stkHtml(s.stack)}</button>`
        : `<button type="button" class="jd empty${pick === i ? " on" : ""}" data-act="slot-pick" data-id="${esc(a.id)}" data-i="${i}"${glowSlot} title="${esc(ringWord(c))}">${ringHtml(c, "<i>＋</i>", "vacant")}<small class="dim">${esc(ringWord(c))}</small></button>`;
    }).join("");
    let picker = "";
    if (pick !== null) {
      const c = colors[pick] || [];
      const fits = (i) => !c.length || c.includes(i.attribute);
      const free = (x.insights || []).filter((i) => !i.slotted);
      picker = `<div class="slot-pick">${a.stack_rule ? `<p class="stk-rule">${esc(a.stack_rule)}</p>` : ""}${free.length ? free.map((i) => `<button type="button" class="${fits(i) ? "" : "no"}" data-act="slot-in" data-id="${esc(a.id)}" data-i="${pick}" data-ins="${esc(i.id)}"${glowSlot} ${fits(i) ? "" : "disabled"} title="${esc(fits(i) ? i.skill_desc || "" : `這一格${ringWord(c)}`)}">${ringHtml([i.attribute], "", "jmini")}<span>「${esc(i.name)}」${lookSeal(i.look)}<small>${fxHtml(i.fx) || `〔${esc(i.skill || "")}〕${lvHtml(i.strength)}`}${fits(i) ? "" : "・顏色不合"}</small>${a.stack && a.stack[i.id] ? `<em class="stk">${esc(a.stack[i.id])}</em>` : ""}</span></button>`).join("")
        : '<span class="muted">手上沒有空著的意境——去探索悟一個，或從別門武學上拆下來。</span>'}</div>`;
    }
    // 第五個玉環（自創的才有，招式與絕學稿案第三節）：破境了亮金色寫絕招，還沒破境是暗的
    const f = a.fifth;
    const fifth = !f ? "" : f.on
      ? `<span class="jd fifth on" title="絕招〔${esc(f.name)}〕">${ringHtml([], `<b>絕</b>`, "gold")}<small>〔${esc(f.name)}〕</small></span>`
      : `<span class="jd fifth" title="${esc(f.note)}">${ringHtml([], "<i>絕</i>", "vacant")}<small class="dim">${esc(f.note)}</small></span>`;
    // 每一格裝的那一招寫出來（Joy 2026-10-25「武學裡面槽裡面擺的，他效果好像不會顯示」）：玉環上只放得下兩個字與效果名，
    // 做什麼原本只在 title（手機上看不到）；底下一格一行：第幾格、意境、效果、這一招做什麼。字待 joy 潤
    const notes = a.slots.map((s, i) => (s ? `<li><b>第 ${i + 1} 格「${esc(s.name)}」</b>${lookSeal(s.look)}<span class="jdn-fx">${esc(fxText(s.fx) || s.skill || "")}</span>${s.desc ? `<span class="jdn-desc">${esc(String(s.desc).replace(/^〔[^〕]*〕/, ""))}</span>` : ""}${stkHtml(s.stack)}${s.idle ? `<em class="idle-why">${esc(s.idle)}</em>` : ""}</li>` : "")).join("");
    return `<div class="jade">${cells}${fifth}</div>${notes ? `<ul class="jd-notes">${notes}</ul>` : ""}${picker}`;
  }

  // 衝關鈕（Joy 2026-10-21「把破境丹也加入商城，取消可以用心得衝」）：只剩服丹衝關，手上有丹、到了極處才亮；
  // 沒丹時這一格只寫等契機（丹從探索、醫館與萬寶閣來）。序章點名的那一顆照舊發光。字待 joy 潤
  function breakBtns(a, has) {
    const lg = a.cultivate.legend;
    const glow = has("cultivate") ? ' data-glow="cultivate"' : "";
    if (lg) return `<div class="pk-btns"><button class="btn small primary" data-act="cultivate" data-by="pill"${glow} data-id="${esc(a.id)}">服丹衝關<small>剩 ${lg.count | 0} 枚</small></button></div>`;
    // 到了極處、手上沒丹：一顆去萬寶閣的鈕，打開就停在破境丹那一件（Joy 2026-10-21「破境丹沒有可以引導他去商城」）。字待 joy 潤
    if (a.cultivate.shop) return `<div class="pk-btns"><button class="btn small" data-act="mall-goto" data-id="${esc(a.cultivate.shop)}">去萬寶閣<small>買破境丹</small></button></div>`;
    return has("cultivate") ? `<div class="pk-btns"><button class="btn small" data-act="cultivate"${glow} data-id="${esc(a.id)}" disabled>衝關</button></div>` : "";
  }

  // 衝關的小動畫（Joy 2026-10-21「衝關那邊做一個小動畫，可以運用到玩家畫的火柴人武學，分成功跟失敗」）：
  // 那一門的火柴人（自創的是玩家自己擺的式，學來的照兵器挑的架式）運氣、衝向一道「關」。衝開了關碎成幾塊、金光、蓋「破境」；
  // 沒衝開撞上去、關裂一道縫、人被彈回來、蓋「彈回」。點一下或播完就收掉；破境卡（ascendCard）在它底下，收掉就看得到。
  // 減少動態的人不播（結果那一句照樣寫在修練頁）。字待 joy 潤
  function breakAnim(a, won) {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const old = document.getElementById("cg-anim");
    if (old) old.remove();
    const box = document.createElement("div");
    box.id = "cg-anim";
    box.className = `cg-wrap ${won ? "won" : "lost"}`;
    const bricks = [0, 1, 2, 3, 4].map((k) => `<g class="cg-brick b${k}"><rect x="262" y="${28 + k * 38}" width="34" height="36" rx="3"/><line x1="268" y1="${40 + k * 38}" x2="290" y2="${40 + k * 38}"/></g>`).join("");
    box.innerHTML = `<div class="cg-stage" role="img" aria-label="${won ? "衝關成功" : "衝關失敗"}">
      <svg class="cg-scene" viewBox="0 0 360 240" aria-hidden="true">
        <line class="cg-ground" x1="0" y1="222" x2="360" y2="222"/>
        <circle class="cg-burst" cx="279" cy="122" r="20"/>
        <g class="cg-gate">${bricks}<text class="cg-guan" x="279" y="132">關</text></g>
        <path class="cg-crack" d="M279 40 L272 82 L286 110 L270 150 L284 196"/>
        <g class="cg-man"><circle class="cg-aura a1" cx="90" cy="130" r="46"/><circle class="cg-aura a2" cx="90" cy="130" r="46"/>
          <svg class="fig cg-fig" x="20" y="22" width="140" height="200" viewBox="30 40 160 200">${figBody(a.pose || {}, a.weapon, false)}</svg></g>
      </svg>
      <p class="cg-stamp">${won ? "破境" : "彈回"}</p>
      <p class="cg-line">${won ? `【${esc(a.name)}】衝開了那一層` : `【${esc(a.name)}】撞在那一層上，又彈了回來`}</p>
    </div>`;
    const close = () => { clearTimeout(timer); box.remove(); };
    const timer = setTimeout(close, 3600);
    box.addEventListener("click", close);
    document.body.appendChild(box);
  }

  function pagePractice() {
    const x = S.menxia;
    if (!x) return '<p class="muted">載入中…</p>';
    // 自創武學從煉製搬到修練（招式與絕學稿案第四輪）：自創本身還是整頁
    if (S.createOpen && S.main && S.main.status && S.main.status.create && S.main.status.create.on) return createPageHtml();
    const s = S.main.status;
    // 第一個練成絕學的人：替它取正式的名字（武學與成長設計 3.6）。名字是玩家打的，伺服器會驗；表單的字跳脫
    const naming = x.naming ? `<form class="naming" id="name-art">
        <small>你練成了絕學</small>
        <p>你是江湖上第一個把【${esc(x.naming.name)}】練成絕學的人，替它取一個正式的名字（2～6 個字，全服不能重名）。</p>
        <div class="row"><input class="input" name="name" maxlength="6" placeholder="正式的名字"><button class="btn primary small" type="submit">定名</button></div>
      </form>` : "";
    // 卡的本體（身上的卡、庫裡點開的那一列共用）：十成的格子、第幾成、兩顆大鈕、破境丹、機率條、改練／熔煉／詳情。
    // slot 是這一門那一欄的 slot_cards（只有身上的才有）：練成鈕亮不亮、價錢、序章的原因都看它
    const body = (a, slot) => {
      const level = Math.max(0, Math.min(10, a.level | 0));
      // 序章指路（T7 走查 W-A）：卡裡哪幾顆鈕發光由伺服器說（a.glow，只有序章裡才有；art_rows 照序章的拒絕算過），網頁不猜。
      // data-glow 的鍵寫成字面（test_content 掃 app.js 對照 models.GLOW_KEYS，內容才叫得動它們）
      const has = (key) => (a.glow || []).includes(key);
      // 練成（Joy 2026-10-20「練成第x成這邊介面按鈕超醜」）：十成的格子旁邊一顆朱印「練」，下一格會亮；按不下去時印是灰的、原因寫在底下一行
      let train = "", why = "";
      if (slot) {
        why = slot.blocked || "";
        const off = !!slot.blocked || slot.maxed;
        const label = slot.maxed ? "已到第十成" : `練成第${level + 1}成（心得 ${slot.price}）`;
        train = `<button class="train-go${off ? "" : " hot"}" data-act="mx" data-op="practice" data-glow="practice" data-kind="${esc(a.kind)}" aria-label="${esc(slot.blocked || label)}" title="${esc(slot.blocked || label)}" ${off ? "disabled" : ""}><b>${slot.maxed ? "滿" : "練"}</b><small>${slot.maxed ? "十成" : `心得 ${slot.price}`}</small></button>`;
      }
      // 武學打了才升的季（slot.progress，別的季沒有）：這一成的熟練與今天還能長多少；打仗長、也能按「練」用心得補滿這一成  // 待 joy 潤
      const pg = slot && slot.progress;
      const prog = !pg ? "" : `<p class="train-why train-prog">${slot.maxed ? "已到第十成" : `熟練 ${pg.exp}/${pg.need}・今天打仗還能長 ${pg.today_left}`}</p>`;
      const next = slot && !slot.blocked && !slot.maxed ? level : -1; // 練下去會亮的那一格
      const pips = `<div class="ten">${Array.from({ length: 10 }, (_, k) => `<i${k < level ? ' class="on"' : k === next ? ' class="next"' : ""}></i>`).join("")}</div>`;
      const switchBtn = slot ? "" : `<div class="acts"><button class="btn" data-act="switch"${has("switch") ? ' data-glow="switch"' : ""} data-id="${esc(a.id)}">改練這一門<small>換上身，熟練度各自保留</small></button></div>`;
      // 衝絕學（武學重構）：只有上品還沒成絕學的才有這一塊；到了極處才有「衝關」與破境丹，沒到只寫還差什麼。不寫下一品是哪一品（企劃者 2026-10-06）
      const ripe = a.cultivate.ok;
      const peakOn = ripe || has("cultivate") || (a.quality === "上品" && (a.slots || []).length > 0);
      const peak = !peakOn ? "" : `<div class="peak${ripe ? " ready" : ""}">
          <div class="pk-txt"><b>破境</b><small class="cnote">${esc(a.cultivate.legend ? a.cultivate.legend.note : a.cultivate.note)}</small></div>
          ${breakBtns(a, has)}
        </div>`;
      const info = S.artInfo === a.id;
      // 功法庫的卡：跟身上同一種那門的比較（W6）直接寫在鈕的上面，改練之前看得到，不必先點「詳情」；點開詳情時功法卡裡也有，這裡就不重複
      const compare = !slot && a.compare && !info ? `<p class="cmp">${esc(a.compare)}</p>` : "";
      return `<div class="train">
          <div class="tr-meter"><div class="tr-lv"><b>第${level}成</b>${scoreHtml(a)}</div>${pips}</div>
          ${train}
        </div>
        ${why ? `<p class="train-why">${esc(why)}</p>` : ""}
        ${prog}
        <div class="lvline"><span>${esc(a.kind)}${a.attribute ? `・屬${esc(a.attribute)}` : ""}・收${esc(a.affinity || "")}</span></div>
        ${slotsHtml(a, x)}
        ${a.tactic && !info ? `<p class="art-tactic">${tacticHtml(a.tactic)}</p>` : ""}
        ${compare}
        ${switchBtn}
        ${S.artNote && S.artNote.id === a.id ? `<div class="msg art-result">${S.artNote.html}</div>` : ""}
        ${peak}
        <div class="more">
          ${a.melt.ok ? "" : `<span class="why">${esc(a.melt.note)}</span>`}
          <button class="linkish" data-act="melt"${has("melt") ? ' data-glow="melt"' : ""} data-id="${esc(a.id)}" data-name="${esc(a.name)}" data-confirm="${esc(a.melt.confirm)}" ${a.melt.ok ? "" : "disabled"} title="${esc(a.melt.note)}">熔煉${a.melt.ok ? `（${/^退回/.test(a.melt.note) ? esc(a.melt.note.replace(/^退回/, "")) : "只空出一格"}）` : ""}</button>
          <button class="linkish" data-act="art-info" data-id="${esc(a.id)}" aria-expanded="${info}">詳情 ${info ? "▴" : "›"}</button>
        </div>
        ${info ? `<div class="art-card">${tenCells(a.card)}</div>` : ""}`;
    };
    // 一門武學在抽屜裡的樣子（招式與絕學稿案第四輪：身上的兩門、庫裡的都進同一個抽屜）：印記、名字、品相，底下是卡的本體
    const artSheet = (a, slot) => `<div class="acard${a.quality === "絕學" ? " q4" : ""}"${a.worn ? ` data-worn="${esc(a.kind)}"` : ""}>
        <div class="hd">${a.quality === "絕學" ? '<span class="qseal q4 big">絕</span>' : ""}<div><h3>${esc(a.name)}</h3><div class="sub">${[a.kind, a.look].filter(Boolean).map(esc).join("・")}</div></div>${a.pose ? figSvg(a.pose, a.weapon, "card-fig") : ""}${a.worn ? '<span class="worn">身上</span>' : ""}</div>
        ${a.tier && a.quality !== "絕學" ? lookLadder(a.tier, ART_LOOK_STEPS) : ""}
        ${body(a, slot)}</div>`;
    // 功法庫：身上以外的。篩選（全部／武學／內功／可修練）與「再列 N 門」只是看的方式，記在 S，輪詢重畫不會跳回去
    // 排序是伺服器排好的（FB-085：身上的先，再品質、成、名字），這裡照順序列；選哪一類記在 localStorage（libFilter）
    const lib = x.owned_arts.filter((a) => !a.worn);
    const pass = (a, f) => f === "all" || (f === "ready" ? a.cultivate.ok : a.kind === f);
    // 篩選鈕只在庫超過 LIB_PAGE 門時才畫（chips）：沒畫鈕就不套記著的篩選——不然庫縮到 8 門以下、或換了新角色（序章的草廬庫只有一兩門），
    // 記在瀏覽器裡的篩選會把武學藏起來、又沒有鈕可以改回來（review-ap3 I1）
    const filter = lib.length > LIB_PAGE ? libFilter() : "all";
    // 展開著的那一門永遠留在清單裡：照「可修練」篩選時，最後一次修練把它修到不能再修（體力不夠、練成絕學）就不合篩選了，
    // 它的結果卻還寫在卡裡、頁面也不該跳走（W7）
    const picked = lib.filter((a) => pass(a, filter) || a.id === S.artOpen);
    // 批量熔煉（企劃者 2026-10-14「合成越來越多，需要能快速熔煉的機制」）：S.meltSel 是勾著的 { arts, ins }（id 串列），null＝沒在勾。
    // 勾的時候功法庫整份列出（不分頁）、每一列一個勾，意境的籤也能勾；底下浮一條「熔掉 N 樣・心得 +X」。序章裡不給（照師父一門一門熔）
    const meltOn = !!S.meltSel;
    const showAll = meltOn || S.libAll || picked.length <= LIB_PAGE + 2; // 只多一兩門就直接列完，不必多按一次
    const first = picked.slice(0, LIB_PAGE);
    const openArt = picked.find((a) => a.id === S.artOpen);
    const rows = showAll ? picked : openArt && !first.includes(openArt) ? [...first, openArt] : first; // 展開著的那一門排在第 8 門之後時也要看得到
    // 序章指路：收著的這一列發光，要按的是它裡面的改練、修練、熔煉（要先點開它）。哪一列、哪幾個鍵由伺服器說（a.glow，只有序章裡才有；
    // art_rows 照序章的拒絕算過：改練只有師父點名的那一門、修練、熔煉只有按得下去的），網頁不猜（T7 走查 W-A）
    // 功法庫一列（招式與絕學稿案第四輪）：印記、名字、招、品相、換上後的戰力；點了開抽屜（詳情、改練、熔煉都在裡面）
    const libRow = (a) => {
      const todo = ["switch", "cultivate", "melt"].filter((key) => (a.glow || []).includes(key)).join(" ");
      const open = S.artOpen === a.id;
      const mark = sealOf(a.tactic), move = moveOf(a.tactic);
      const diff = typeof a.might === "number" && typeof x.might === "number" ? a.might - x.might : 0;
      return `<button class="art libr ${open ? "on" : ""}" data-act="art" data-id="${esc(a.id)}"${todo && !open ? ` data-glow="${todo}"` : ""}>${mark ? tsealHtml(mark) : ""}<span class="txt"><b>${esc(a.name)}</b><small>${[move ? `〔${move}〕` : "", a.tier || ""].filter(Boolean).map(esc).join("・")}</small></span>${typeof a.might === "number" ? `<span class="lib-might${diff > 0 ? " up" : diff < 0 ? " down" : ""}">戰力 ${x.might | 0} → ${a.might | 0}</span>` : ""}</button>`;
    };
    const libGroups = (list) => KINDS.map((k) => {
      const rows = list.filter((a) => a.kind === k);
      return rows.length ? `<div class="sub lib-kind">${k}</div><div class="lib">${rows.map(libRow).join("")}</div>` : "";
    }).join("");
    const tutorial = x.owned_arts.some((a) => a.glow) || x.insights.some((i) => i.blocked);
    const meltable = lib.filter((a) => a.melt.ok);
    const meltSwitch = !tutorial && meltable.length + x.insights.length >= 2
      ? `<button class="linkish melt-mode" data-act="melt-mode">${meltOn ? "收起" : "批量熔煉"}</button>` : "";
    // 勾著的照現在的功法庫過一遍：熔掉了、輪詢回來已經不在的、改成熔不掉的（換上身了）不算
    const sel = S.meltSel ? {
      arts: S.meltSel.arts.filter((id) => meltable.some((a) => a.id === id)),
      ins: S.meltSel.ins.filter((id) => x.insights.some((i) => i.id === id)),
    } : { arts: [], ins: [] };
    if (meltOn) S.meltSel = sel;
    // 勾的時候：篩選、排序（meltFilterHtml／meltShown）與「勾選篩出來的全部」；清單是武學、內功、意境同一張（meltRowHtml）
    const shown = meltOn ? meltShown(x) : [];
    const shownOk = shown.filter((it) => it.ok);
    const allShown = shownOk.length > 0 && shownOk.every((it) => sel[it.t].includes(it.id));
    const meltTools = meltOn ? `${meltFilterHtml(x)}<div class="melt-tools"><span>篩出 ${shown.length} 樣</span>
        ${shownOk.length ? `<button class="${allShown ? "on" : ""}" data-act="melt-shown">${allShown ? "✓ " : ""}勾選篩出來的全部 ${shownOk.length}</button>` : ""}
        <button data-act="melt-clear">全不勾</button></div>` : "";
    const meltList = meltOn ? (shown.length ? `<div class="lib mlist">${shown.map((it) => meltRowHtml(it, sel[it.t].includes(it.id), S.meltOpen === `${it.t}:${it.id}`)).join("")}</div>`
      : '<p class="muted">沒有合這些條件的功法與意境。</p>') : "";
    const meltValue = sel.arts.reduce((sum, id) => sum + ((lib.find((a) => a.id === id) || {}).melt?.value | 0), 0)
      + sel.ins.reduce((sum, id) => sum + ((x.insights.find((i) => i.id === id) || {}).melt | 0), 0);
    const meltCount = sel.arts.length + sel.ins.length;
    const meltGo = meltOn ? `<div class="melt-gap"></div><div class="melt-go"><span>已勾 <b>${meltCount}</b> 樣<small>心得 +${meltValue}</small></span>
        <button class="btn" data-act="melt-mode">取消</button>
        <button class="btn danger" data-act="melt-go" data-n="${meltCount}" data-v="${meltValue}" ${meltCount ? "" : "disabled"}>熔掉</button></div>` : "";
    const chips = lib.length > LIB_PAGE ? `<div class="lib-filter">${LIB_FILTERS.map(([f, label]) => {
      const n = lib.filter((a) => pass(a, f)).length;
      return `<button class="${filter === f ? "on" : ""}" data-act="lib-filter" data-filter="${f}">${label} ${n}</button>`;
    }).join("")}</div>` : "";
    // 意境（招式與絕學稿案第四輪）：籤改成列——玉環、名字、品相、效果一行、裝在哪；沒裝的排前面。點了開抽屜（意境卡）
    const insOpen = x.insights.find((i) => i.id === S.insOpen);
    const insF = S.insFilter || "all";
    const insPass = (i) => insF === "all" || (insF === "free" ? !i.slotted : !!i.slotted);
    const insList = x.insights.filter(insPass).sort((p, q) => Number(!!p.slotted) - Number(!!q.slotted));
    const insRow = (i) => `<button class="insr${S.insOpen === i.id ? " on" : ""}" data-act="ins-open" data-id="${esc(i.id)}">${ringHtml([i.attribute], i.own && i.glyph ? glyphSvg(i.glyph, "glyph-mini") : `<b>${esc(String(i.name).slice(0, 1))}</b>`, "jmini")}<span class="txt"><b>「${esc(i.name)}」${lookSeal(i.look)}</b><small>${esc(fxText(i.fx) || i.depth || "")}${i.slotted ? `・裝在【${esc(i.slotted)}】` : ""}</small></span></button>`;
    const INS_FILTERS = [["all", "全部"], ["free", "沒裝的"], ["used", "裝著的"]]; // 待 joy 潤
    const insFilterRow = x.insights.length > 3 ? `<div class="lib-filter">${INS_FILTERS.map(([f, label]) => `<button class="${insF === f ? "on" : ""}" data-act="ins-filter" data-filter="${f}">${label} ${x.insights.filter((i) => f === "all" || (f === "free" ? !i.slotted : !!i.slotted)).length}</button>`).join("")}</div>` : "";
    // 名冊只有本人一列（還沒有同伴）時跟上面的本人卡重複，不畫（C6）
    const mates = x.roster.length > 1;
    // 裝備（裝備四欄設計 2.5）：開著的欄位一段一段（武器、防具、坐騎、寶物），每段先列身上那件、再列裝備庫裡同一欄的。
    // 格數四欄合算（gear.used／gear.cap）。字都是伺服器給的資料，一律 esc。這一版畫不出的欄位（新伺服器多了一欄）整段略過。
    // FB-125（兵器第二批 Task 1）：名字與說明在左邊（.winfo，塞不下自己折行），「換上」「拆解」包在右邊一個不折行的 .wbtns 裡；拆解按了先問一次（data-confirm）
    const gear = x.gear;
    // 換上後的戰力（招式與絕學稿案第四輪）：跟人形圖上那個數比，強了綠、弱了紅
    const mightTag = (w) => (typeof w.might === "number" && typeof x.might === "number"
      ? `<small class="lib-might${w.might > x.might ? " up" : w.might < x.might ? " down" : ""}">換上後戰力 ${x.might | 0} → ${w.might | 0}</small>` : "");
    // 神器原品不能拆（打造隱藏配方設計 5.4）：伺服器給 keep（原因），拆解鈕灰掉寫它，不送、不問
    // 神器 15 級才穿得上（正式季整合 5.8）：伺服器給 wield_ok／wield_note（同坐騎那一列），「換上」灰掉、原因寫在說明底下與 title
    const rowButtons = (w) => `<div class="wbtns"><button class="btn small" data-act="wield" data-id="${esc(w.id)}"${w.wield_ok === false ? ` disabled title="${esc(w.wield_note || "")}"` : ""}>換上</button>${w.keep
      ? `<button class="btn small ghost" disabled>${esc(w.keep)}</button>`
      : `<button class="btn small ghost" data-act="dismantle" data-id="${esc(w.id)}" data-confirm="${esc(w.confirm || "")}">拆解</button>`}</div>`;
    // 神器原品定名（打造隱藏配方設計 5.2）：還沒定名的原品那一列底下一張表單——自己打一個名字，或「沿用譜名【…】」。
    // 一個人可以同時有好幾把，表單照裝備 id 各一張（data-op 認，id 不重複）。名字合不合格由伺服器驗；字一律 esc。整段待 joy 潤
    // 表單接在 .wrow 的外面、緊貼著它底下（.wrow 是橫排的 flex，放進去會被擠到鈕的右邊）
    const divineForm = (w) => divineFormHtml(w.id, w.divine.pattern, false, w.divine.unit); // 店面的出爐卡與裝備庫共用同一張（divineFormHtml）；量詞照伺服器給的（FB-197）
    // 以器配招（玩家武學追上本命定案 四）：自己手上還沒配招的神器原品那一列底下一小塊：挑一門有絕招的絕學、按「以器配招」（綁了不能改配）。
    // 沒有配得上的寫一句怎麼才有。select 的 id 帶裝備 id 的冒號，用 getElementById 找
    const bindForm = (w) => !w.bind ? "" : `<div class="gear-bind">${w.bind.options.length
      ? `<small>以器配招：把這件綁在你一門絕學上，那一招更強（綁了不能改配）</small>
        <div class="row"><select class="input" id="bind-art-${esc(w.id)}">${w.bind.options.map((o) => `<option value="${esc(o.id)}">【${esc(o.name)}】${esc(o.bond)}</option>`).join("")}</select>
        <button class="btn small primary" data-act="bind-art" data-id="${esc(w.id)}">以器配招</button></div>`
      : `<small class="muted">以器配招：自己合成的武學練成絕學、有了絕招，就能把這件神器綁在那一門上。</small>`}</div>`;
    // 武器：淬過的寫「淬煉 N/M」（M 照這一件的品質，鐵匠鋪與合成流程 3.6：下品 5、中品 6、上品 7，伺服器給 temper_max），自己打的寫配方（兵器第二批 Task 8）；
    // 上品磨得慢（wear_note，3.6）接在鋒利度後面
    // 待 joy 潤：「淬煉 N/M」「配方 …」「磨得慢」這幾段字
    const slowNote = (w) => (w.wear_note ? `・${esc(w.wear_note)}` : "");
    const weaponRow = (w, wornNow) => `<div class="wrow${w.fits ? "" : " muted"}">
        <div class="winfo"><b>【${esc(w.name)}】</b><span>${esc(w.noun || w.kind)}・屬${esc(w.attribute)}${w.grade ? `・${esc(w.grade)}` : ""}${w.tempers ? `・淬煉 ${w.tempers | 0}/${w.temper_max | 0}` : ""}・鋒利度 ${w.edge | 0}${slowNote(w)}${w.bonus ? `・威力 ${esc(w.bonus)}` : "・用不上"}</span>${w.recipe ? `<small class="muted">配方 ${esc(w.recipe)}</small>` : ""}${(w.tactic || []).map((t) => `<small class="gear-tactic">${esc(t)}</small>`).join("")}${w.wield_ok === false && !wornNow ? `<small class="rwhy">${esc(w.wield_note || "")}</small>` : ""}${wornNow ? "" : mightTag(w)}</div>
        ${wornNow ? "" : rowButtons(w)}
      </div>${w.divine ? divineForm(w) : ""}${bindForm(w)}`;
    // 防具：不分種類、沒有「配不上」；寫耐久度與這件一場少扣幾成氣血、對不對得上你的內功（裝備四欄設計 4.1、4.2）。
    // 磨損的叫法照伺服器給的 wear_word（equipment.WEAR_WORDS，2.5、3.1），不寫死。這一行的寫法待 joy 潤；淬過的寫「淬煉 N/M」、自己打的寫配方（防具打造，同武器列）
    const armorRow = (a, wornNow) => `<div class="wrow">
        <div class="winfo"><b>【${esc(a.name)}】</b><span>屬${esc(a.attribute)}・${esc(a.grade)}${a.tempers ? `・淬煉 ${a.tempers | 0}/${a.temper_max | 0}` : ""}・${esc(a.wear_word)} ${a.edge | 0}${slowNote(a)}・少扣 ${esc(a.cut)} 氣血${a.fit ? `・${esc(a.fit)}` : ""}</span>${a.recipe ? `<small class="muted">配方 ${esc(a.recipe)}</small>` : ""}${(a.tactic || []).map((t) => `<small class="gear-tactic">${esc(t)}</small>`).join("")}${a.wield_ok === false && !wornNow ? `<small class="rwhy">${esc(a.wield_note || "")}</small>` : ""}${wornNow ? "" : mightTag(a)}</div>
        ${wornNow ? "" : rowButtons(a)}
      </div>${a.divine ? divineForm(a) : ""}${bindForm(a)}`;
    // 坐騎（裝備四欄設計第五節）：駑馬、良駒、名駒的階品，飽足度（照伺服器給的 wear_word）、疾行省幾成體力、路上快幾成、
    // 決戰強攻奇襲多幾成、落敗脫身的機會（2.5：後三項寫在修練頁這一列，不擠進角色卡）。
    // 身上那匹一顆「餵」（餵不了的灰掉、寫為什麼；餵得了寫用哪一種素材），裝備庫裡的只有「換上」：坐騎不能拆（4.8），不用 rowButtons；
    // 路上不能換坐騎（2.3），「換上」照伺服器給的 wield_ok 灰掉、寫 wield_note（同「餵」的灰掉做法）。
    // FB-137：灰掉的鈕上只寫動詞（原因寫在鈕上，會把左邊的說明擠成一行六、七個字、那一列變 4～6 行）；原因放鈕的 title，
    // 也寫在這一列自己的說明底下（.rwhy；手機沒有 title 可看）。能按的「餵」照舊寫用哪一種素材（短）。
    // 這一行的寫法待 joy 潤
    const mountRow = (h, wornNow) => {
      const why = wornNow ? (h.feed ? "" : h.feed_note || "") : (h.wield_ok ? "" : h.wield_note || "");
      return `<div class="wrow">${horseImg(h.art, "horse-thumb")}
        <div class="winfo"><b>【${esc(h.name)}】</b><span>${esc(h.grade)}・${esc(h.wear_word)} ${h.edge | 0}・疾行省 ${esc(h.save)} 體力・路上快 ${esc(h.speed)}・決戰強攻奇襲 +${esc(h.cavalry)}・落敗脫身 ${esc(h.escape)}</span>${why ? `<small class="rwhy">${esc(why)}</small>` : ""}${wornNow ? "" : mightTag(h)}</div>
        <div class="wbtns">${wornNow
          ? (h.feed ? `<button class="btn small" data-act="feed">餵${h.feed_note ? `（${esc(h.feed_note)}）` : ""}</button>` : `<button class="btn small" data-act="feed" disabled${why ? ` title="${esc(why)}"` : ""}>餵</button>`)
          : `<button class="btn small" data-act="wield" data-id="${esc(h.id)}"${h.wield_ok ? "" : ` disabled${why ? ` title="${esc(why)}"` : ""}`}>換上</button>`}</div>
      </div>`;
    };
    // 寶物（裝備四欄設計第六節）：一件一種效果、不分階品、不磨損；身上那件寫效果，裝備庫裡的只有「換上」（寶物不能拆，4.8，不用 rowButtons）。
    // 寶物隨時能換（2.3【定】，企劃者 2026-10-11），「換上」不灰掉。這一行的寫法待 joy 潤
    const treasureRow = (t, wornNow) => `<div class="wrow">
        <div class="winfo"><b>【${esc(t.name)}】</b><span>${esc(t.effect_text)}</span>${wornNow ? "" : mightTag(t)}</div>
        ${wornNow ? "" : `<div class="wbtns"><button class="btn small" data-act="wield" data-id="${esc(t.id)}">換上</button></div>`}
      </div>`;
    // 修練頁其他動作的結果（mxPlace）：寫在按的那一塊裡，頁首那一行不寫
    const noteAt = (at) => S.mxNote && S.mxNote.at === at ? `<div class="msg mx-note">${S.mxNote.html}</div>` : "";
    const GEAR_ROWS = { weapon: weaponRow, armor: armorRow, mount: mountRow, treasure: treasureRow };
    const slotBlock = (g) => {
      const row = GEAR_ROWS[g.slot];
      if (!row) return "";
      const shown = S.rackAll || g.rack.length <= LIB_PAGE ? g.rack : g.rack.slice(0, LIB_PAGE);
      // 傳承那一列（玉璽碎片的抄本，玉璽碎片設計 7.3）：寶物段身上那件之前；有獨門行動的碎片多一顆鈕（heirloomRow，改版第 2 批）；
      // 寶物的開關關著、只有傳承時不寫「身上沒有寶物」（待 joy 潤）
      return `<section class="gear-slot" data-slot="${esc(g.slot)}"><div class="sub">${esc(g.label)}</div>${noteAt("gear:" + g.slot)}
        ${g.fit_line ? `<p class="muted gear-fit">${esc(g.fit_line)}</p>` : ""}
        ${g.heirloom ? heirloomRow(g.heirloom, sealActNow()) : ""}
        ${g.worn ? row(g.worn, true) : g.heirloom && !g.rack.length ? "" : `<p class="muted">${esc(g.empty)}</p>`}
        ${shown.map((w) => row(w, false)).join("")}
        ${shown.length < g.rack.length ? `<button class="btn ghost lib-more" data-act="rack-all">再列 ${g.rack.length - shown.length} 件</button>` : ""}
        <p class="muted">${esc(g.note)}</p>
      </section>`;
    };
    // 寄放著的東西（裝備四欄 6.5：懸賞的重賞、名將贈禮在裝備庫滿了時先寄放）寫在塊底下一行灰字；身上、裝備庫都空著也照樣畫這一塊
    const heldLine = gear && gear.held_note ? `<p class="muted">${esc(gear.held_note)}</p>` : "";
    // 塊名由「兵器」改成「裝備」（待 joy 潤）；段名（武器、防具）是伺服器給的 label
    const hasGear = gear && (heldLine || gear.slots.some((g) => g.worn || g.heirloom || g.rack.length)); // 傳承那一列（玉璽碎片）也算有東西
    // FB-138：空著的那一格寫空著的那一句與哪裡拿得到（where，伺服器照內容的地點標籤給；內容裡沒有那種地點時是空字串）
    // 「裝備」那一段（Joy 2026-10-26「裝備跟門下顯示優化，裝備可以類似意境那樣，要直覺好看懂」）：四欄一欄一格（2×2），
    // 空的也畫（虛線框、寫哪裡拿得到）；格子裡寫裝了什麼、一句效果、還剩幾成（鋒利、耐久、飽足）。點一格開那一欄的抽屜（slotBlock：
    // 換上、拆解、修、餵都在那裡，同人像四角）。這一版畫不出的欄位略過；四欄都關著（slots 空）整段不畫。字待 joy 潤
    const gearBlock = gear && gear.slots.some((g) => GEAR_ROWS[g.slot]) ? `<section class="self-sec gear-sec" aria-label="裝備"><div class="self-hd"><h3>裝備</h3>${hasGear ? `<small class="muted">裝備庫 ${gear.used | 0}/${gear.cap | 0}</small>` : ""}</div>
      <div class="gear-grid">${gear.slots.filter((g) => GEAR_ROWS[g.slot]).map(gearCell).join("")}</div>
      ${heldLine}</section>` : "";
    // 抽屜（招式與絕學稿案第四輪：點什麼，內容就從底下升起；整頁只用這一個）：庫裡的一門、意境、身上的一門、一欄裝備。
    // S.pdrawer 是點了哪個光點（false 是剛關上）；序章裡師父點名要按的鈕在身上那一門時，沒點過也先攤開那一門
    const stepGlow = (S.main && S.main.prologue && S.main.prologue.glow) || [];
    const tutorWorn = S.pdrawer == null && !S.artOpen && !S.insOpen && (
      x.owned_arts.find((a) => a.worn && ["slot", "cultivate", "melt"].some((k) => stepGlow.includes(k) && (a.glow || []).includes(k)))
      || (stepGlow.includes("practice") && x.owned_arts.find((a) => a.worn && practiceOk(x, a.kind))));
    const pd = S.pdrawer || (tutorWorn ? { t: "worn", key: tutorWorn.kind } : null);
    let drawerTitle = "", drawerBody = "";
    const openLib = S.artOpen && lib.find((a) => a.id === S.artOpen);
    if (openLib) {
      drawerTitle = `功法庫・${openLib.kind}`; drawerBody = artSheet(openLib, null); // 抽屜的標題寫是哪一類，名字在卡上
    } else if (insOpen) {
      drawerTitle = "意境"; drawerBody = insightCardHtml(insOpen, { fits: true, melt: true }) + noteAt("ins");
    } else if (pd && pd.t === "worn") {
      const slot = x.slot_cards.find((c) => c.kind === pd.key) || { learned: false };
      const a = x.owned_arts.find((r) => r.worn && r.kind === pd.key);
      drawerTitle = `身上的${pd.key}`;
      drawerBody = (a ? artSheet(a, slot) : `<div class="acard empty">${slot.card || `你還沒有${esc(pd.key)}。`}</div>`) + (pro() || !(typeof uiV2 === "function" && uiV2()) ? "" : swapListHtml(x, pd.key));
    } else if (pd && pd.t === "gear" && gear) {
      const g = gear.slots.find((sl) => sl.slot === pd.key);
      drawerTitle = g ? g.label : ""; drawerBody = g ? `<div class="gear">${slotBlock(g)}${heldLine}</div>` : ""; // .gear：一件一行、鈕靠右（同以前的摺疊）
    }
    const drawerHtml = drawerBody ? `<div class="sheet-bg" data-act="drawer-close"></div>
      <div class="sheet pr-sheet" role="dialog" aria-label="${esc(drawerTitle)}"><div class="grip"></div>
        <div class="top-row"><h3 style="flex:1">${esc(drawerTitle)}</h3><button type="button" class="btn small ghost" data-act="drawer-close">關閉</button></div>
        ${drawerBody}</div>` : "";
    // 俠客頁的排法（Joy 2026-10-24「這頁既然都要重做了，為什麼不整體重新規劃」；草圖 https://claude.ai/artifact/DcuRiGjo9CtcBJoY87wu9m）：
    // 人像與四欄裝備 → 武學（身上兩門；功法庫、意境是右上那一顆）→ 屬性五格 → 去做四格 → 記錄清單（行狀、榜單、名帖匣）→
    // 四個收著的摺疊：功法庫（武學、意境、批量熔煉）、裝備、門下、修練的規矩。開合記在 S.selfOpen（toggle 事件）；勾著批量熔煉時功法庫一定攤開
    const fold = (sec, title, body) => `<details class="fold self-fold" data-sec="${sec}"${(S.selfOpen && S.selfOpen[sec]) || (sec === "lib" && meltOn) ? " open" : ""}><summary>${title}</summary><div class="fold-body">${body}</div></details>`;
    const libBody = `${meltSwitch}${S.meltNote ? `<div class="msg melt-result">${S.meltNote}</div>` : ""}
      ${meltOn ? `<p class="muted melt-hint">點一列勾起來，再按底下的「熔掉」；點右邊的 › 看細節。身上正在練的與本命武學熔不掉。</p>
      ${meltTools}
      ${meltList}` : `${chips}
      ${lib.length ? (picked.length ? libGroups(rows) : '<p class="muted">這一類沒有功法。</p>')
        : libEmptyHtml(x)}
      ${showAll ? "" : `<button class="btn ghost lib-more" data-act="lib-all">再列 ${picked.length - LIB_PAGE} 門</button>`}`}
      ${meltOn ? "" : `<div class="label">意境</div>
      ${x.insights.length ? `${insFilterRow}${insList.length ? `<div class="lib insl">${insList.map(insRow).join("")}</div>` : '<p class="muted">這一類沒有意境。</p>'}`
        : '<p class="muted">還沒悟到任何意境。去探索，荒郊野外最容易有所領悟。</p>'}`}`;
    const rosterBody = `<details class="fold" open><summary>本人</summary><div class="fold-body">${tenCells(x.player_card)}</div></details>
      ${mates ? `<div class="list">${x.roster.map((r) => `<button class="${x.person === r.key ? "on" : ""}" data-act="person" data-key="${esc(r.key)}">${esc(r.label)}</button>`).join("")}</div>` : ""}
      ${mates && x.person ? `<div class="card person-card">${tenCells(x.person_card)}${noteAt("person")}
        ${x.person === "player" ? '<p class="muted">本人一直都在隊伍裡。</p>' // 本人不能加入、移出（引擎也會擋）
          : x.person.startsWith("follower:") ? "" // 部下（計畫 T5）也不能加入、移出；角色卡已經寫了
          : `<button class="btn ${x.on_team ? "" : "primary"}" data-act="mx" data-op="${x.on_team ? "leave" : "join"}">${x.on_team ? "移出隊伍" : "加入隊伍"}</button>`}
        ${x.release ? `<button class="btn ghost" data-act="release-mate" data-confirm="${esc(x.release.confirm)}">放他回江湖</button>` : ""}
        ${lessonsHtml(x.lessons)}</div>` : ""}`;
    // 「同伴」那一段（2026-11-09 前叫門下）（Joy 2026-10-26「門下顯示優化」）：一人一張卡（server 的 roster_cards）——名字、本人／出戰／候命／部下的印、等級、
    // 氣血一條、身上兩門各一行（名字、品質、成數十格）。點一張在它底下攤開角色卡與加入、移出、放回江湖、傳功（同以前名冊點人）；再點收起。
    // 舊伺服器沒有 roster_cards 時照舊畫摺疊裡的名冊
    const mateCard = (c) => {
      const on = x.person === c.key;
      const hp = c.hp_max ? `<span class="mate-hp" role="meter" aria-valuemin="0" aria-valuemax="${c.hp_max}" aria-valuenow="${c.hp}" aria-label="氣血"><i style="width:${Math.max(0, Math.min(100, Math.round((c.hp / c.hp_max) * 100)))}%"></i></span><small class="mate-hpn">氣血 ${c.hp}／${c.hp_max}</small>` : "";
      const arts = c.arts.map((a) => `<span class="mate-art"><em>${esc(a.kind)}</em>${a.name ? `<b>${esc(a.name)}</b><small>${esc(a.quality)}${a.attribute ? `・屬${esc(a.attribute)}` : ""}</small>`
        + `<i class="sa-ten" role="meter" aria-valuemin="0" aria-valuemax="10" aria-valuenow="${a.level | 0}" aria-label="${esc(a.name)}第${a.level | 0}成">${saInk(Math.max(0, Math.min(10, a.level | 0)), a.quality === "絕學")}</i>` : '<small class="muted">尚未習得</small>'}</span>`).join("");
      const detail = on && x.person_card ? `<div class="mate-detail">${mateExtra(x.person_card)}${noteAt("person")}
        ${x.person === "player" || x.person.startsWith("follower:") ? ""
          : `<button class="btn ${x.on_team ? "" : "primary"}" data-act="mx" data-op="${x.on_team ? "leave" : "join"}">${x.on_team ? "移出隊伍" : "加入隊伍"}</button>`}
        ${x.release ? `<button class="btn ghost" data-act="release-mate" data-confirm="${esc(x.release.confirm)}">放他回江湖</button>` : ""}
        ${lessonsHtml(x.lessons)}</div>` : "";
      return `<div class="mate${on ? " on" : ""} role-${MATE_ROLES[c.role] || "home"}"><button class="mate-hd" data-act="person" data-key="${esc(c.key)}" aria-expanded="${on}">
        <span class="mate-seal" aria-hidden="true">${esc(c.role.slice(0, 1))}</span>
        <span class="mate-body"><span class="mate-name"><b>${esc(c.name)}</b>${c.level != null ? `<small>第 ${c.level | 0} 級</small>` : ""}<em>${esc(c.role)}</em></span>${hp}${arts}</span>
        <span class="mate-arrow" aria-hidden="true">${on ? "▴" : "›"}</span></button>${detail}</div>`;
    };
    const cards = x.roster_cards;
    const fighting = cards ? cards.filter((c) => c.role === "出戰" || c.role === "部下").length : 0;
    const rosterBlock = cards ? `<section class="self-sec mates-sec" aria-label="同伴"><div class="self-hd"><h3>同伴</h3><small class="muted">${cards.length > 1 ? `${cards.length - 1} 人・出戰 ${fighting} 人` : "還沒有同伴"}</small></div>
      <div class="mates">${cards.map(mateCard).join("")}</div>
      ${cards.length > 1 ? "" : '<p class="muted mates-none">交友、結識大勢人物，情誼夠了就有人願意追隨你。</p>'}</section>`
        : fold("roster", `同伴${mates ? ` <small class="muted">${x.roster.length} 人</small>` : ""}`, rosterBody);
    const gdBlock = typeof guardHtml === "function" ? guardHtml(S.main) : ""; // 親衛隊長的養成冊（web/guard.js；收養了才畫）：同伴那一頁最上面
    const zmBlock = typeof zongmenHtml === "function" ? zongmenHtml(S.main) : ""; // 師門（web/zongmen.js；不是哪一門的人不畫）：介面重整後自己一個分頁
    // 紀念物（長篇奇事，企劃者 2026-10-27）：故事裡收下的小東西，沒有效果、不能賣，跨季跟著角色；一件都沒有不畫
    const keepItems = (S.main && S.main.keepsakes) || [];
    const keeps = keepItems.length ? `<section class="self-sec keepsakes" aria-label="紀念"><div class="self-hd"><h3>紀念</h3><small class="muted">故事裡收下的，留著</small></div>
      <p class="keep-list">${keepItems.map((k) => `<span class="keep">${esc(k)}</span>`).join("")}</p></section>` : "";
    // 介面重整（2026-11-05，Joy「點了看武學或是裝備，卻不能馬上換…自創武學甚至要滑很下面才能看到」）：序章以外分四頁——
    // 武學（自創、煉製排第一屏，身上兩門，功法庫攤開）、裝備、門下、屬性（以前狀態列點名號攤開的那一大串也在這裡）。記在 S.heroTab
    if ((typeof uiV2 === "function" && uiV2()) && !pro()) {
      const heroTabs = zmBlock ? [...HERO_TABS.slice(0, 3), HERO_SECT, ...HERO_TABS.slice(3)] : HERO_TABS; // 師門：是哪一門的人（或有殘頁）才有這一頁
      const tab = heroTabs.some(([k]) => k === S.heroTab) ? S.heroTab : "arts";
      const tabs = `<div class="hero-tabs" role="tablist">${heroTabs.map(([k, n]) => `<button role="tab" class="${tab === k ? "on" : ""}" aria-selected="${tab === k}" data-act="hero-tab" data-tab="${k}">${n}</button>`).join("")}</div>`;
      const page = tab === "arts" ? `${selfEntriesHtml(x)}${naming}${selfArtsHtml(x)}${attrNoteHtml(x)}<section class="self-sec lib-sec"><div class="self-hd"><h3>功法庫</h3><small class="muted">武學與意境 ${x.holdings.count}/${x.holdings.cap}</small></div>${libBody}</section>${fold("rules", "修練的規矩", x.rules)}`
        : tab === "gear" ? `${gearBlock}${keeps}`
        : tab === "mates" ? `${gdBlock}${rosterBlock}`
        : tab === "sect" ? zmBlock
        : `${selfStatsHtml(s, true)}${heroMoreHtml(s)}`;
      return `${proGuide()}${heroPanel(x, s)}${tabs}<div class="msg" id="mx-msg">${S.message}</div>${page}${meltGo}${meltOn ? "" : drawerHtml}`;
    }
    return `
      ${proGuide()}
      ${heroPanel(x, s)}
      ${selfArtsHtml(x)}
      ${gearBlock}
      ${gdBlock}
      ${rosterBlock}
      ${zmBlock}
      ${keeps}
      ${selfStatsHtml(s)}
      ${selfEntriesHtml(x)}
      <div class="msg" id="mx-msg">${S.message}</div>
      ${naming}
      ${attrNoteHtml(x)}
      ${fold("lib", `功法庫 <small class="muted">武學與意境 ${x.holdings.count}/${x.holdings.cap}</small>`, libBody)}
      ${fold("rules", "修練的規矩", x.rules)}
      ${meltGo}
      ${meltOn ? "" : drawerHtml}`;
  }

  const HERO_TABS = [["arts", "武學"], ["gear", "裝備"], ["mates", "同伴"], ["attrs", "屬性"]]; // 待 joy 潤（Joy 2026-11-09：門下跟門派放一起怪，改名）
  const HERO_SECT = ["sect", "師門"]; // 待 joy 潤：門派包開著、是哪一門的人才插在同伴後面（web/zongmen.js）
  // 屬性頁（Joy 2026-11-06「這一定要預設展開那麼多說明？上面已經有屬性了下面還有文字版」）：屬性一份（上面那一格一欄，selfStatsHtml）、
  // 名聲一份（名望、善名、惡名一行，點「怎麼來」才攤開那一條階梯與來源）、經驗與歷練兩條細條並排、成長一行、傳承一行。
  // 只放跟自己成長有關的：兩軍態勢在江湖頁、修練的規矩（講武學與意境）在武學那一頁、等級在人像卡上
  // 同伴不在這裡重複（門下那一頁有）
  // 待 joy 潤：「怎麼來」「升第 N 級」
  const meterHtml = (cls, label, have, need) => `<div class="hm-meter ${cls}"><span>${label}</span><i style="--w:${need ? Math.min(100, Math.round((have / need) * 100)) : 100}%"></i></div>`;
  function heroMoreHtml(s) {
    const exp = s.exp === undefined ? "" : !s.exp ? `<div class="hm-meter who-exp full"><span>經驗已到頂</span><i style="--w:100%"></i></div>`
      : meterHtml("who-exp", `經驗 ${s.exp.have}／${s.exp.need}<small>升第 ${(s.level | 0) + 1} 級</small>`, s.exp.have, s.exp.need);
    const meters = exp || s.lilian ? `<div class="hm-meters">${exp}${s.lilian ? lilianHtml(s.lilian) : ""}</div>` : "";
    const r = s.renown;
    const nums = (s.minor || []).map(([k, v]) => `<span><em>${esc(k)}</em><b>${v}</b></span>`).join("");
    const titles = r && r.short && r.short.length ? `<span class="rn-titles">${rnTitleSpans(r).join("・")}</span>` : "";
    const how = r ? `<button class="linkish rn-how" data-act="renown-toggle" aria-expanded="${!!S.renownOpen}">怎麼來 ${S.renownOpen ? "▴" : "▾"}</button>` : "";
    const fame = `<section class="self-sec hm-fame" aria-label="名聲"><div class="hm-line">${nums}${titles}${how}</div>${r ? (S.renownOpen ? `<div class="hm-renown">${renownStripHtml(r)}</div>` : "") : rangerHtml(s.ranger)}</section>`;
    const alloc = s.stat_points && !shown("stats") ? `<div class="pts-label"><b class="pts">可配 ${s.stat_points} 點</b></div><div class="row alloc">${s.attrs.map(([k, v, key]) => `<button class="btn small" data-act="allocate" data-stat="${esc(key)}" data-glow="allocate" ${v >= s.stat_cap ? "disabled" : ""}>＋${esc(k)}</button>`).join("")}</div>` : "";
    // 兩軍態勢不放這裡（Joy 2026-11-06「屬性那邊還有放態勢」）：那是戰局，不是自己的成長；江湖頁本週卡那一行有
    const tail = S.main && S.main.legacy ? legacyHtml(S.main.legacy) : "";
    return `<section class="self-sec hero-more" aria-label="經驗與成長">${meters}<div class="more-stats">${alloc}${s.growth ? growthHtml(s.growth) : ""}</div></section>${fame}${tail ? `<section class="self-sec hm-tail">${tail}</section>` : ""}`;
  }
  // 點身上那一門（人像的光點、武學那一段）：抽屜底下列功法庫裡同一類的，每一門一行「換上」與換上後的戰力（Joy「點了…卻不能馬上換」）
  function swapListHtml(x, kind) {
    const same = x.owned_arts.filter((a) => !a.worn && a.kind === kind);
    if (!same.length) return `<p class="muted swap-none">功法庫裡沒有別的${esc(kind)}。</p>`;
    return `<div class="swap-list"><div class="label">換一門${esc(kind)}</div>${same.map((a) => {
      const diff = typeof a.might === "number" && typeof x.might === "number" ? a.might - x.might : 0;
      return `<div class="swap-row"><span class="txt"><b>${esc(a.name)}</b><small>${esc([a.quality, a.tier, `第${a.level | 0}成`].filter(Boolean).join("・"))}</small></span>${typeof a.might === "number" ? `<span class="lib-might${diff > 0 ? " up" : diff < 0 ? " down" : ""}">戰力 ${x.might | 0} → ${a.might | 0}</span>` : ""}<button class="btn small primary" data-act="switch" data-id="${esc(a.id)}">換上</button></div>`;
    }).join("")}</div>`;
  }

  // 傳功門下（Config.chuangong）：人物卡底下一排鈕，鈕上寫要練什麼與心得，底下一行寫效果；按不下去的灰掉、原因寫在效果那一行
  function lessonsHtml(rows) {
    if (!rows || !rows.length) return "";
    return `<div class="label">傳功</div><div class="lessons">${rows.map((r) =>
      `<button class="btn small" data-act="teach" data-what="${esc(r.what)}" ${r.problem ? "disabled" : ""}${r.problem ? ` title="${esc(r.problem)}"` : ""}>${esc(r.label)}<small>${esc(r.problem || r.effect)}</small></button>`).join("")}</div>`;
  }

  // ── 煉製 ──
  const QUALITY_RANK = { 下品: 1, 中品: 2, 上品: 3, 絕學: 3 };

  // 破境卡（tianxia/ascend.py；招式與絕學稿案第三節）：剛破境就蓋一張在畫面上——左邊破境前的招、右邊絕招、中間模型寫的一句、
  // 戰力從多少到多少、底下江湖史那一行。那一句還沒寫就請伺服器寫一次（/api/do/ascend_line，三段式）；收下了才收掉。字待 joy 潤
  let ascendAsked = "";
  function ascendCard() {
    const card = S.main && S.main.status && S.main.status.ascension;
    let box = document.getElementById("ascend");
    if (!card) { if (box) box.remove(); return; }
    if (!box) { box = document.createElement("div"); box.id = "ascend"; box.className = "asc-wrap"; document.body.appendChild(box); }
    const [was, now] = card.power || [];
    box.innerHTML = `<div class="asc-card" role="dialog" aria-label="破境">
      <p class="asc-head">${tsealHtml("絕")}<b>【${esc(card.name)}】破境</b></p>
      <div class="asc-moves"><div class="asc-was"><small>破境前</small><p>${tacticHtml(card.before)}</p></div>
        <div class="asc-arrow">›</div><div class="asc-now"><small>絕招</small><p>${tacticHtml(card.after)}</p>${card.after_tail ? `<p>${tacticHtml(card.after_tail)}</p>` : ""}</div></div>
      <p class="asc-line">${card.line ? `「${esc(card.line)}」` : `<span class="muted">……</span>`}</p>
      ${was != null && now != null ? `<p class="asc-power">戰力 ${was | 0} → <b>${now | 0}</b></p>` : ""}
      <p class="muted small asc-chron">江湖史：${esc(card.chronicle || "")}</p>
      <button class="btn primary" data-act="ascend-ok">收下</button></div>`;
    if (!card.line && ascendAsked !== card.art) {
      ascendAsked = card.art;
      api("/api/do/ascend_line", {}).then((r) => { if (r && r.main) applyMain(r.main); }).catch(() => {});
    }
  }

  registerPage("practice", { render: pagePractice });

  // 熔煉的問句（W9、FB-081）：整句由伺服器寫好、放在按鈕的 data-confirm（library.melt_confirm：有心得就寫退回多少，沒有就直說
  // 只空出一格；基礎武學再接一句去哪裡重學，只說一次）。伺服器沒給（舊版）才用這句老問題
  // 批量熔煉（修練頁功法庫）：勾、勾選篩出來的全部（meltPickShown）、確認之後一次送出
  function meltToggle(key, id) {
    if (!S.meltSel || !id) return;
    const list = S.meltSel[key];
    S.meltSel = { ...S.meltSel, [key]: list.includes(id) ? list.filter((v) => v !== id) : [...list, id] };
    renderPage();
  }
  function askMeltMany(el) {
    const sel = S.meltSel;
    if (!sel || !(sel.arts.length + sel.ins.length)) return;
    const parts = [sel.arts.length ? `${sel.arts.length} 門武學` : "", sel.ins.length ? `${sel.ins.length} 個意境` : ""].filter(Boolean).join("、");
    const v = el.dataset.v | 0;
    const warn = sel.ins.length ? "靠這些意境修練的武學，熔了就不能再修練。" : "";
    ask(`把勾的 ${parts}一起熔掉？${v > 0 ? `心得 +${v}。` : ""}熔掉就沒了。${warn}`, "熔掉", async () => {
      const body = { arts: sel.arts, insights: sel.ins };
      S.meltSel = null;
      await mx("melt_many", body);
    });
  }
  const meltAskText = (el) => el.dataset.confirm || `把【${el.dataset.name}】熔成心得？熔掉就沒了。`;

  // 熔煉與意境化成心得都先問一次，用頁面自己的確認層（ask，管理者工具用的那一個；FB-085）：以前是瀏覽器內建的確認框，
  // 跟其他按鈕不一樣、手機上還會被擋掉。按「熔掉」才送，取消或點旁邊暗處什麼都不送
  function askMelt(el) {
    ask(meltAskText(el), "熔掉", () => mx("melt", { art: el.dataset.id }));
  }
  function askMeltInsight(el) {
    ask(`把「${el.dataset.name}」化成心得？靠它的武學從此不能修練。`, "化成心得", () => mx("melt_insight", { insight: el.dataset.id }));
  }
  // 俠客頁原地重畫（Joy 2026-11-07「不要每次點門下、裝備那些按鈕，按完都給我跳置頂」）：捲到哪留在哪。
  // 換到比較短的分頁時，最多往上收到分頁鈕剛好在頂上（#page 撐高到那個位置還捲得到，不讓瀏覽器把頁面收回底部）
  function heroStay(draw) {
    const page = document.getElementById("page");
    const y = window.scrollY || 0;
    draw();
    const tabs = typeof document.querySelector === "function" ? document.querySelector("#page .hero-tabs") : null;
    if (!page || !page.style || !tabs || typeof tabs.getBoundingClientRect !== "function" || typeof window.scrollTo !== "function") return;
    const tabsTop = tabs.getBoundingClientRect().top + (window.scrollY || 0);
    const target = Math.min(y, Math.max(0, tabsTop - 8));
    const need = target + window.innerHeight - page.getBoundingClientRect().top - (window.scrollY || 0);
    page.style.minHeight = `${Math.max(0, Math.ceil(need))}px`;
    window.scrollTo(0, target);
  }
  async function cultivationClick(act, el, ev) {
    switch (act) {
        case "hero-tab": heroStay(() => { S.heroTab = el.dataset.tab; S.pdrawer = false; renderPage(); }); break; // Joy 11/7「按完不要都給我跳置頂」
        case "attr-help": heroStay(() => { S.attrHelp = !S.attrHelp; renderPage(); }); break; // 屬性頁的「？」：五項各管什麼
        case "xinde-more": heroStay(() => { S.xindeOpen = !S.xindeOpen; renderPage(); }); break; // 屬性頁心得那一行：點開看整句提示
        case "hero-move-show": await heroMoveShow(el.dataset.id || ""); break; // 俠客頁武學卡底下的絕招演一次
        case "hero-move-go": await heroMoveGo(el.dataset.style || ""); break; // 換一招：萬寶閣絕招那一頁
        case "hero-node": heroTap(el); break; // 修練頁人物面板的光點：開那一樣的抽屜
        case "self-sec": { // 俠客頁「功法庫・意境 ›」那一顆：攤開底下那個摺疊、捲到它
          (S.selfOpen || (S.selfOpen = {}))[el.dataset.sec] = true;
          renderPage();
          const box = document.querySelector(`details.self-fold[data-sec="${CSS.escape(el.dataset.sec)}"]`);
          if (box && box.scrollIntoView) box.scrollIntoView({ behavior: "smooth", block: "start" });
          break;
        }
        case "drawer-close": S.pdrawer = false; S.artOpen = null; S.insOpen = null; S.slotPick = null; renderPage(); break;
        case "ins-filter": S.insFilter = el.dataset.filter; renderPage(); break;
        case "kind": S.kind = el.dataset.kind; renderPage(); break;
        case "mx": if (el.dataset.kind) S.kind = el.dataset.kind; await mx(el.dataset.op); break; // 卷軸卡上的練成鈕帶著是哪一欄
        case "art-info": S.artInfo = S.artInfo === el.dataset.id ? null : el.dataset.id; renderPage(); break;
        case "lib-filter": setLibFilter(el.dataset.filter); renderPage(); break;
        case "lib-all": S.libAll = true; renderPage(); break;
        case "melt-mode": S.meltSel = S.meltSel ? null : { arts: [], ins: [] }; S.artOpen = null; S.meltOpen = null; S.meltNote = null; renderPage(); break;
        case "melt-pick": meltToggle("arts", el.dataset.id); break;
        case "melt-pick-ins": meltToggle("ins", el.dataset.id); break;
        case "melt-shown": meltPickShown(); break;
        case "melt-weak": meltView().weak = !meltView().weak; renderPage(); break;
        case "melt-open": S.meltOpen = S.meltOpen === el.dataset.key ? null : el.dataset.key; renderPage(); break;
        case "melt-clear": if (S.meltSel) { S.meltSel = { arts: [], ins: [] }; renderPage(); } break;
        case "melt-go": askMeltMany(el); break;
        case "rack-all": S.rackAll = true; renderPage(); break;
        case "ins-open": S.insOpen = S.insOpen === el.dataset.id ? null : el.dataset.id; S.artOpen = null; S.pdrawer = false; renderPage(); break;
        case "slot-pick": { // 空槽：攤開（再點收起）手上空著的意境
          const same = S.slotPick && S.slotPick.art === el.dataset.id && S.slotPick.i === Number(el.dataset.i);
          S.slotPick = same ? null : { art: el.dataset.id, i: Number(el.dataset.i) };
          renderPage(); break;
        }
        case "slot-in": S.slotPick = null; await mx("slot", { art: el.dataset.id, insight: el.dataset.ins, index: Number(el.dataset.i) }); break;
        case "ascend-ok": await mx("ascend_dismiss", {}); break;
        case "slot-out": await mx("unslot", { art: el.dataset.id, insight: el.dataset.ins }); break;
        case "person":
          S.person = S.person === el.dataset.key ? null : el.dataset.key;
          await loadMenxia();
          break;
        case "wield": await mx("wield", { weapon: el.dataset.id }); break; // 裝備庫上那一把換到手上
        case "feed": await mx("feed"); break;
        case "release-mate": { // 歷史武將同行：放他回江湖，先問一次（問句伺服器寫好，roster.RELEASE_CONFIRM）
          const who = S.person;
          ask(el.dataset.confirm, "放他走", async () => { S.person = null; await mx("release", { person: who }); });
          break;
        }
        case "teach": await mx("chuangong", { what: el.dataset.what }); break; // 傳功門下：person 是名冊上點的那個人 // 身上那匹餵一個一階素材（裝備四欄 5.4）
        case "bind-art": { // 以器配招：送挑好的那一門（select 的 id 帶冒號，用 getElementById）
          const pick = document.getElementById("bind-art-" + el.dataset.id);
          if (pick && pick.value) ask("綁了之後不能改配（那一門熔掉、交掉才能再配），確定嗎？", "綁上", () => mx("bind_art", { weapon: el.dataset.id, art: pick.value }));
          break;
        }
        case "dismantle": // 裝備庫上那一把拆成一個素材（兵器設計 4.7.1）：先問一次（FB-125），按「拆掉」才送
          ask(el.dataset.confirm || "把這一件拆成素材？拆掉就沒了。", "拆掉", () => mx("dismantle", { weapon: el.dataset.id }));
          break;
        case "switch": {
          // 改練真的送出了（mx 換上伺服器回來的那一份 menxia）才收起卡片；還在忙（mx 直接返回）或請求失敗就照舊開著
          await mx("switch", { art: el.dataset.id }); // 真的送出了才收起卡片（mx 換上伺服器回來的那一份才收）；還在忙或失敗就照舊開著
          break;
        }
        case "art": S.artOpen = S.artOpen === el.dataset.id ? null : el.dataset.id; S.artNote = null; S.insOpen = null; S.pdrawer = false; renderPage(); break;
        case "cultivate": {
          // 服丹衝關（use_legend，伺服器只認真正的布林 true）。真的擲了骰（mx 換上了伺服器回來的那一份 menxia、丹少了一枚）
          // 才播衝關的小動畫：那一門變成絕學是衝開了，不然是彈回來
          const id = el.dataset.id, pill = el.dataset.by === "pill";
          const row = (S.menxia?.owned_arts || []).find((a) => a.id === id);
          const was = S.menxia?.legend_items;
          await mx("cultivate", { art: id, use_legend: pill });
          if (row && pill && typeof was === "number") {
            // 看手上的丹（不是那一列的 legend：被拒絕時那一列也會變成 null，例如體力在別處花掉了，那時不能播彈回）
            const now = (S.menxia?.owned_arts || []).find((a) => a.id === id);
            const won = !!now && now.quality === "絕學";
            if (won || (S.menxia?.legend_items ?? was) < was) breakAnim(row, won);
          }
          break;
        }
        case "melt": askMelt(el); break;
        case "melt-insight": askMeltInsight(el); break;
    } // cultivationClick
  } // cultivationClick
  registerClicks(cultivationClick, ["hero-tab", "attr-help", "xinde-more", "hero-move-show", "hero-move-go", "hero-node", "self-sec", "drawer-close", "ins-filter", "kind", "mx", "art-info", "lib-filter", "lib-all", "melt-mode", "melt-pick", "melt-pick-ins", "melt-shown", "melt-weak", "melt-open", "melt-clear", "melt-go", "rack-all", "ins-open", "slot-pick", "slot-in", "ascend-ok", "slot-out", "person", "wield", "feed", "release-mate", "teach", "bind-art", "dismantle", "switch", "art", "cultivate", "melt", "melt-insight"]);
  async function cultivationForm(form, data) {
      if (form.id === "name-art") {
        // 絕學定名：名字合不合格、有沒有人用過都由伺服器驗，結果寫在頁面上方那一行；定成了表單就不再畫
        if (!data.name.trim()) { toast("先取個名字。"); return; }
        await mx("name", { name: data.name });
        // 被拒了（表單還在，原因寫在頁面上方那一行）：mx 重畫的表單是空的，把剛打的字放回去，不用重打；定成了表單就不在
        const again = document.querySelector('#name-art input[name="name"]');
        if (again && S.menxia && S.menxia.naming) again.value = data.name;
      } else if (form.dataset && form.dataset.op === "name-divine") {
        // 神器原品定名（5.2）：名字合不合格、有沒有人用過都由伺服器驗，結果寫在頁面上方那一行；定成了那一列就不再畫表單
        if (!data.name.trim()) { toast("先取個名字。"); return; }
        await mx("name_divine", { weapon: form.dataset.id, name: data.name.trim() });
        // 被拒了（那一列的表單還在，原因寫在頁面上方那一行）：原因也記下來、表單裡留一行（FB-193），重畫；mx 重畫的表單是空的，
        // 把剛打的字放回去，不用重打（同絕學定名那張）。表單 id 帶著裝備 id 的冒號，用 getElementById 找（不走選擇器）；
        // 定成了那一列不再畫表單，找不到就什麼都不放
        if (document.getElementById("name-divine-" + form.dataset.id)) {
          S.divineWhy[form.dataset.id] = (S.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
          renderPage();
        }
        const again = document.getElementById("name-divine-" + form.dataset.id)?.querySelector('input[name="name"]');
        if (again) again.value = data.name;
      } // cultivationForm
  } // cultivationForm
  registerForms(cultivationForm, ["name-art", "op:name-divine"]);
  async function cultivationChange(ev) {
    if (ev.target.dataset && ev.target.dataset.act === "melt-view") { // 批量熔煉的篩選與排序
      meltView()[ev.target.dataset.key] = ev.target.value;
      renderPage();
    }
  } // cultivationChange
  registerChanges(cultivationChange);

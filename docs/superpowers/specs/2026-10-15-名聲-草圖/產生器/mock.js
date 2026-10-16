
  // ── 名聲草圖（只在草圖裡，不是遊戲程式）：S.rv 決定每一處畫哪一種 ──
  const RV = () => S.rv || {};
  // 假瀏覽器量不到字寬：中文一個字算一個字寬、數字與英文算半個多一點（真的做時照 fitBars 量）
  const textW = (t, px) => [...String(t)].reduce((w, ch) => w + (/[0-9A-Za-z .]/.test(ch) ? px * 0.58 : px), 0);
  function rnTitles(r, opts = {}) {
    if (!r) return [];
    const out = [];
    if (r.fame && r.fame.tier >= (opts.fameFrom || 1)) out.push(r.fame.title);
    if (r.virtue && r.virtue.tier >= 1) out.push(r.virtue.title);
    return out;
  }
  const pathClass = (p) => (p === "寇" ? "kou" : "xia");
  function whoNameHtml(s) {
    const v = RV(), r = s.renown;
    if (!r) return whoNameHtml_orig(s);
    const pts = s.stat_points ? `<b class="pts">可配 ${s.stat_points} 點</b>` : "";
    const base = [s.affiliation, ...(s.anonymous ? ["匿名"] : [])].filter(Boolean).join("・");
    const tail = `第${s.level}級`;
    if (!S.showMore) {
      let titles = rnTitles(r);
      const room = 295 - textW(s.name, 17) - 6 - 18 - (s.stat_points ? 62 : 0);
      const lineW = (ts, px) => textW([base, ...ts, tail].join("・"), px);
      if (v.top === "B") {
        return `<div class="who-name"><span>${esc(s.name)}<small>${esc(base)}・${tail}</small></span>${pts}<i class="more-ico" aria-hidden="true">▾</i></div>`
          + (titles.length ? `<div class="sx-rn-line sx-mark">${titles.map((t, i) => `<span class="${i === titles.length - 1 && r.virtue.tier ? pathClass(r.virtue.path) : "fame"}">${esc(t)}</span>`).join("・")}</div>` : "");
      }
      if (v.top === "C") {
        const tight = lineW(titles, 12) > room;
        return `<div class="who-name${tight ? " sx-shrink" : ""}"><span>${esc(s.name)}<small>${esc(base)}・<span class="sx-mark sx-in">${esc(titles.join("・"))}</span>・${tail}</small></span>${pts}<i class="more-ico" aria-hidden="true">▾</i></div>`;
      }
      // A（設計的預設）：接在頭銜後面，放不下先收名望稱號
      if (lineW(titles, 12) > room && titles.length > 1) titles = titles.slice(1);
      const mid = titles.length ? `・<span class="sx-mark sx-in">${esc(titles.join("・"))}</span>` : "";
      return `<div class="who-name"><span>${esc(s.name)}<small>${esc(base)}${mid}・${tail}</small></span>${pts}<i class="more-ico" aria-hidden="true">▾</i></div>`;
    }
    // 展開：頭銜那一行照舊（不再接遊俠名號），經驗底下多一行「名聲」，點了開說明卡
    const segs = [...s.affiliation.split("・"), ...(s.anonymous ? ["匿名"] : []), tail].filter(Boolean);
    const titles = rnTitles(r);
    const line = `<div class="who-renown sx-mark"><em>名聲</em><b>${titles.length ? titles.map((t) => esc(t)).join("・") : "還沒有稱號"}</b><i>${v.card === "A" || v.card === "C" ? "▴" : "›"}</i></div>`;
    return `<div class="who-name"><span>${esc(s.name)}</span><i class="more-ico" aria-hidden="true">▴</i></div>
          <div class="who-title">${segs.map((t) => `<span class="who-seg">${esc(t)}</span>`).join("・")}</div>${expHtml(s)}${line}`;
  }
  // 2A、2C 攤開的那一塊：排在名號那一塊底下、整個寬度（不擠在設定鈕旁邊）
  function sxPanel() {
    const s = S.main.status, r = s.renown, v = RV();
    if (!S.showMore || !r) return "";
    return v.card === "A" ? rnPanelHtml(r) : v.card === "C" ? rnStripHtml(r) : "";
  }

  // 說明卡的一段：一級一列，已經有的打勾、現在這一段框起來，往上的淡一點
  function rnLadder(rows, cur, compact = false) {
    return `<ol class="sx-ladder${compact ? " compact" : ""}">${rows.map((t, i) => {
      const cls = i < cur ? "have" : i === cur ? "have cur" : "off";
      return `<li class="${cls}"><span class="ck">${i <= cur ? "✓" : ""}</span><b>${esc(t.title)}</b><small>${t.at}</small>${t.perks.length ? `<p>${esc(t.perks.join("・"))}</p>` : ""}</li>`;
    }).join("")}</ol>`;
  }
  function rnBar(x) {
    if (x.next == null) return `<p class="sx-rn-gap">已是最高的一段</p>`;
    const w = Math.max(3, Math.min(100, Math.round(100 * (x.n - x.from) / (x.at - x.from))));
    return `<div class="sx-rn-bar"><i style="width:${w}%"></i></div><p class="sx-rn-gap">再 ${x.gap} 點到「${esc(x.next)}」</p>`;
  }
  function rnFameBlock(r, compact) {
    const f = r.fame;
    return `<div class="sx-rn-big"><b class="fame">${esc(f.title)}</b><span>名望 ${f.n}</span></div>${rnBar(f)}`
      + rnLadder(r.ladders.fame.slice(1), f.tier - 1, compact)
      + `<p class="sx-rn-note">高一段的折扣取代低一段；其餘的好處升上去照留。</p>`
      + `<p class="sx-rn-src"><b>名望從哪裡來</b>${esc(r.sources.fame)}</p>`;
  }
  function rnVirtueBlock(r, compact) {
    const v = r.virtue, mine = v.path === "寇" ? "kou" : "xia";
    const other = mine === "kou" ? "xia" : "kou";
    const otherName = mine === "kou" ? "俠" : "寇";
    return `<div class="sx-rn-big"><b class="${mine}">${esc(v.title)}</b><span>善名 ${v.good}・惡名 ${v.evil}（照${esc(v.by)}算）</span></div>${rnBar({ n: v.by === "惡名" ? v.evil : v.good, from: v.from, at: v.at, gap: v.gap, next: v.next })}`
      + `<p class="sx-rn-sub ${mine}">${mine === "kou" ? "寇" : "俠"}的路</p>` + rnLadder(r.ladders[mine], v.tier - 1, compact)
      + `<details class="sx-rn-other"><summary>${otherName}的路（${otherName === "俠" ? "善名" : "惡名"}比${otherName === "俠" ? "惡名" : "善名"}高就換過去）</summary>${rnLadder(r.ladders[other], -1, true)}</details>`
      + (r.sanren ? `<div class="sx-rn-sanren"><p class="sx-rn-sub">散人另有的好處（遊俠名號留下來的，照善惡稱號的段）</p><ul>${r.sanren.map(([k, x]) => `<li><b>${esc(k)}</b>${esc(x)}</li>`).join("")}</ul></div>` : "")
      + `<p class="sx-rn-src"><b>善名、惡名從哪裡來</b>${esc(r.sources.virtue)}</p>`;
  }
  // 2A：在狀態列裡就地攤開（自己捲，限高）
  function rnPanelHtml(r) {
    return `<div class="sx-rn-panel sx-mark"><p class="sx-rn-h">名望</p>${rnFameBlock(r, true)}<p class="sx-rn-h">善惡</p>${rnVirtueBlock(r, true)}</div>`;
  }
  // 2B：底部抽屜（同玩家卡、設定），名望、善惡兩頁
  function renownSheetHtml() {
    const r = S.main.status.renown, tab = S.renownSheet;
    const t = rnTitles(r);
    return `<div class="sheet-bg" data-act="renown-close"></div>
      <div class="sheet sx-rn-sheet sx-mark" role="dialog" aria-label="名聲">
        <div class="grip"></div>
        <h3 class="sx-rn-title">名聲<small>${esc(t.join("・"))}</small></h3>
        <div class="seg sx-rn-tabs"><button class="${tab === "fame" ? "on" : ""}">名望・${esc(r.fame.title)}</button><button class="${tab === "virtue" ? "on" : ""}">善惡・${esc(r.virtue.title || "無")}</button></div>
        ${tab === "fame" ? rnFameBlock(r, false) : rnVirtueBlock(r, false)}
        ${r.scale_note ? `<p class="sx-rn-note">${esc(r.scale_note)}</p>` : ""}
        <div class="row"><button class="btn ghost">關閉</button></div>
      </div>`;
  }
  // 2C：兩條段落條＋這一段、下一段各一句（點圓點看別段）
  function rnStripHtml(r) {
    const dots = (rows, cur, cls) => `<ol class="sx-dots ${cls}">${rows.map((t, i) => `<li class="${i < cur ? "have" : i === cur ? "have cur" : ""}"><i></i><small>${esc(t.title)}</small></li>`).join("")}</ol>`;
    const f = r.fame, v = r.virtue, mine = v.path === "寇" ? "kou" : "xia";
    const fr = r.ladders.fame.slice(1), vr = r.ladders[mine];
    const nextF = fr[f.tier] ? `<span>再 ${f.gap} 到${esc(fr[f.tier].title)}：${esc(fr[f.tier].perks.join("・"))}</span>` : "";
    const nextV = vr[v.tier] ? `<span>再 ${v.gap} 到${esc(vr[v.tier].title)}：${esc(vr[v.tier].perks.join("・"))}</span>` : "";
    return `<div class="sx-strip sx-mark">
      <div class="sx-srow"><span class="sx-slbl">名望 <b>${f.n}</b></span>${dots(fr, f.tier - 1, "fame")}</div>
      <p class="sx-snote"><b class="fame">${esc(f.title)}</b>${esc(fr[f.tier - 1].perks.join("・"))}${nextF}</p>
      <div class="sx-srow"><span class="sx-slbl">${mine === "kou" ? "惡名" : "善名"} <b>${mine === "kou" ? v.evil : v.good}</b></span>${dots(vr, v.tier - 1, mine)}</div>
      <p class="sx-snote"><b class="${mine}">${esc(v.title)}</b>${esc(vr[v.tier - 1].perks.join("・"))}${nextV}</p>
      <p class="sx-shint">點圓點看那一段給什麼・${mine === "kou" ? "善名" : "惡名"} ${mine === "kou" ? v.good : v.evil}，走${mine === "kou" ? "寇" : "俠"}的路${r.sanren ? "・散人另有遊俠的好處（點開看）" : ""}</p>
    </div>`;
  }

  // 玩家卡（第三處）：別人的名聲只寫稱號、不寫數字
  function peerSegs(c) {
    const segs = [...c.affiliation.split("・")];
    if (RV().peer === "C" && c.renown) segs.push(...c.renown.titles.map((t) => `\u0000${t}`));
    segs.push(`第${c.level}級`);
    return segs;
  }
  const peerSeg = (t) => (t[0] === "\u0000" ? `<span class="peer-seg sx-mark sx-in">${esc(t.slice(1))}</span>` : `<span class="peer-seg">${esc(t)}</span>`);
  function peerRenown(c) {
    const r = c.renown, v = RV().peer;
    if (!r || !r.titles.length || v === "C") return "";
    if (v === "B") {
      return `<div class="sx-chips sx-mark">${r.titles.map((t, i) => `<span class="sx-chip ${i === r.titles.length - 1 && r.path ? pathClass(r.path) : "fame"}">${esc(t)}</span>`).join("")}<i class="sx-chip-more">›</i></div>`;
    }
    return `<div class="peer-renown sx-mark"><em>名聲</em><b>${r.titles.map((t) => esc(t)).join("・")}</b><i>›</i></div>`;
  }

  // 本場戰功（第四處）：名字後面寫稱號（善惡第 1 段起、名望名動一方起；在加入決戰時快照）
  function meritName(r) {
    const t = r.renown || [], v = RV().merit;
    if (!t.length) return `<span>${esc(r.name)}</span>`;
    if (v === "B") return `<span class="sx-two">${esc(r.name)}<small class="sx-mark sx-in">${esc(t.join("・"))}</small></span>`;
    if (v === "C") return `<span>${esc(r.name)}<small class="sx-t sx-mark sx-in">${esc(t.join("・"))}</small></span>`;
    return `<span>${esc(r.name)}<small class="sx-t sx-mark sx-in">${esc(t[0])}</small></span>`; // A：一行只放得下一個，名望優先
  }

  // 事件選項（第五處）：5C 不畫那一顆，選單底下一行小字
  function sxAfterMenu() {
    const h = S.main && S.main.sx_hint;
    return h ? `<p class="sx-opt-hint sx-mark">${esc(h)}</p>` : "";
  }
  // ── 名聲草圖（完）──


/* 俠客頁重排（功能包 xiake；Joy 2026-11-26 看示意稿「好 很棒」；示意稿 https://claude.ai/artifact/QYC9xRw99gfH3ULcRLxLJC）。
 *
 * 開關 Config.xiake.enabled（預設關）：伺服器送 main.xiake 時，俠客頁（web/cultivation.js 的 pagePractice，序章以外）改用這裡的排法；
 * 關著照舊是那一排六顆小分頁。
 *
 * 由上到下（照江湖頁重排定下的元件：場景圖滿版、狀態一行、旁白不裝框、眼下一張卡、同一種牌子、點了從底下拉起）：
 *   1. 人像當主角：所在地的圖滿版、暈進紙色；墨色人像在右，名號楷書大字、身分小印、戰力在左；行狀、名帖匣、信匣一行小字
 *   2. 旁白兩行：手上拿什麼、練什麼；哪一門的人、親衛跟在身邊
 *   3. 眼下一張卡：這一頁現在最該理的一件（親衛有事、絕學定名、升級的點、來信、江湖錄的新一筆），鈕就在卡上；其餘收成「另有 N 件」
 *   4. 六面牌（武學、裝備、同伴、師門、屬性、江湖錄；還沒長出來的不畫）：點一面拉起那一塊，裡面照舊是原本那一頁的內容（pageOf）
 * 同伴那一塊另外排過：親衛一張卡（鈕在卡上）、同伴排成立繪方格，點一位拉起他的卡。
 * 拉起的那一塊記在 S.xkSec；別處跳過來（狀態列的名號、江湖錄的連結、慢慢長出來的引路）照舊設 S.heroTab，這裡看到它變了就拉起那一塊。
 */
"use strict";

  const xkOn = (m) => !!(m && m.xiake && m.xiake.on);

  const XK_GLYPH = { arts: "劍", gear: "甲", mates: "伴", sect: "門", attrs: "骨", codex: "錄" }; // 牌面的底紋大字（之後要畫圖再換）
  const XK_CLOSE = "關閉"; // 待 joy 潤
  const XK_MORE = "另有 {n} 件"; // 待 joy 潤
  const XK_LATER = "知道了"; // 待 joy 潤
  const XK_MIGHT = "戰力"; // 待 joy 潤
  const XK_NO_MATES = "還沒有同伴。交友、結識大勢人物，情誼夠了就有人願意追隨你。"; // 待 joy 潤
  const XK_MATES_HEAD = "同伴"; // 待 joy 潤
  const XK_MATES_TAP = "點一位看他"; // 待 joy 潤
  const XK_TEACH = "傳功"; // 待 joy 潤
  const XK_TEACH_SUB = "用你的心得教他"; // 待 joy 潤
  const XK_RELEASE = "放他回江湖"; // 待 joy 潤
  const XK_GUARD_GO = "去看看"; // 待 joy 潤
  const XK_GUARD_ALL = "他的事"; // 待 joy 潤
  const XK_GUARD_BACK = "收起"; // 待 joy 潤

  const xkPct = (now, max) => (max ? Math.max(0, Math.min(100, Math.round(((now | 0) / max) * 100))) : 0);
  const xkTenths = (lv) => (typeof CN_TENTHS !== "undefined" ? CN_TENTHS[Math.max(0, Math.min(10, lv | 0))] : String(lv | 0));
  const xkWorn = (x, kind) => (x.owned_arts || []).find((a) => a.worn && a.kind === kind);
  const xkGear = (x, slot) => { const g = x.gear && x.gear.slots.find((sl) => sl.slot === slot); return g && g.worn ? g.worn : null; };
  const xkMates = (x) => (x.roster_cards || []).filter((c) => c.role !== "本人");

  // 場景圖：閒著時是所在地的圖（江湖頁那一張）；眼前不是地點時用上一張地點的圖，都沒有就只有紙
  function xkArt(m) {
    if (m.art && m.art.kind === "place") return m.art.src;
    return S.lastPlaceArt || "";
  }

  // 旁白兩行（待 joy 潤）：手上的兵器與身上的武學；哪一門的人、親衛跟在身邊
  function xkProse(m, x) {
    const w = xkGear(x, "weapon"), a = xkWorn(x, "武學");
    const head = `${w ? `手上${esc(w.name)}，` : "赤手空拳，"}${a ? `練的是${esc(a.name)}。` : "身上還沒有武學。"}`;
    const z = m.zongmen && m.zongmen.sect, g = m.guard;
    const two = [z ? `${esc(z)}門下` : "", g && g.along ? `${esc(g.name)}跟在身邊` : ""].filter(Boolean).join("・");
    return `<div class="xk-prose"><p>${head}</p>${two ? `<p class="em">${two}。</p>` : ""}</div>`;
  }

  // 眼下：這一頁現在該理的事，照先後排；第一件畫成卡，其餘收在「另有 N 件」
  function xkEyeItems(m, p) {
    const s = p.s, out = [];
    const g = m.guard;
    if (g && g.event && !g.event.shown) out.push({ key: "guard", seal: "親衛", title: `${g.name}有事找你`, sub: g.stage_text || "", btn: XK_GUARD_GO, attrs: 'data-act="xk-guard"' }); // 待 joy 潤
    else if (g && g.schools && g.schools.length) out.push({ key: "guard", seal: "親衛", title: `${g.name}要去求學了`, sub: "替他挑一個地方", btn: XK_GUARD_GO, attrs: 'data-act="xk-guard"' }); // 待 joy 潤
    if (p.naming) out.push({ key: "naming", seal: "絕學", title: "替你的絕學定個名", sub: "江湖上第一個練成的人才能定名", btn: "去定名", attrs: 'data-act="xk-open" data-sec="arts"' }); // 待 joy 潤
    if ((s.stat_points | 0) > 0 && p.tabs.some(([k]) => k === "attrs")) out.push({ key: `pts:${s.level | 0}`, seal: "升級", title: `還有 ${s.stat_points | 0} 點可配`, sub: "五項自己挑", btn: "去配", attrs: 'data-act="xk-open" data-sec="attrs"' }); // 待 joy 潤
    const mail = typeof mailUnread === "function" ? mailUnread() : 0;
    if (mail > 0) out.push({ key: `mail:${mail}`, seal: "來信", title: `信匣有 ${mail} 封沒看`, sub: "", btn: "打開", attrs: 'data-act="news" data-news="mail"' }); // 待 joy 潤
    if (typeof cxDot === "function" && cxDot() && p.tabs.some(([k]) => k === "codex")) out.push({ key: "codex", seal: "江湖錄", title: "江湖錄添了新的一筆", sub: "", btn: "去看", attrs: 'data-act="xk-open" data-sec="codex"' }); // 待 joy 潤
    return out.filter((it) => !(S.xkLater || []).includes(it.key));
  }
  function xkEyeHtml(m, p) {
    const items = xkEyeItems(m, p);
    if (!items.length) return "";
    const [top, ...rest] = items;
    const more = rest.length ? `<button class="xk-more" data-act="xk-eye-all" aria-expanded="${!!S.xkEyeAll}">${esc(XK_MORE.replace("{n}", rest.length))}<i aria-hidden="true">${S.xkEyeAll ? "▴" : "›"}</i></button>` : "";
    const rows = S.xkEyeAll ? rest.map((it) => `<div class="xk-row"><span class="xk-seal">${esc(it.seal)}</span><b>${esc(it.title)}</b><button class="btn small" ${it.attrs}>${esc(it.btn)}</button></div>`).join("") : "";
    return `<section class="xk-eye" aria-label="眼下"><div class="xk-eye-hd"><span class="xk-seal">${esc(top.seal)}</span><h2>${esc(top.title)}</h2>${more}</div>
      ${top.sub ? `<p>${esc(top.sub)}</p>` : ""}
      <div class="xk-eye-go"><button class="btn primary" ${top.attrs}>${esc(top.btn)}</button><button class="btn ghost" data-act="xk-later" data-key="${esc(top.key)}">${XK_LATER}</button></div>${rows}</section>`;
  }

  // 六面牌上的一行小字：現在的樣子（待 joy 潤）
  function xkPlaqueLine(k, m, p) {
    const x = p.x, s = p.s;
    if (k === "arts") { const a = xkWorn(x, "武學") || xkWorn(x, "內功"); return a ? `${a.name} ${xkTenths(a.level)}成` : "還沒有武學"; }
    if (k === "gear") { const w = xkGear(x, "weapon"); return w ? w.name : "還沒有兵器"; }
    if (k === "mates") {
      const mates = xkMates(x), fight = mates.filter((c) => c.role === "出戰" || c.role === "部下").length;
      if (m.guard) return mates.length ? `${m.guard.name}・同伴 ${mates.length}` : m.guard.name;
      return mates.length ? `出戰 ${fight}・共 ${mates.length}` : "還沒有同伴";
    }
    if (k === "sect") return (m.zongmen && m.zongmen.sect) || "師門殘頁";
    if (k === "attrs") return (s.stat_points | 0) > 0 ? `可配 ${s.stat_points | 0} 點` : `第 ${s.level | 0} 級`;
    if (k === "codex") return "奇遇與圖鑑";
    return "";
  }
  function xkPlaques(m, p) {
    const cells = p.tabs.map(([k, n]) => `<button class="xk-pl" data-act="xk-open" data-sec="${esc(k)}"><i aria-hidden="true">${XK_GLYPH[k] || esc(n.slice(0, 1))}</i><b>${esc(n)}</b><small>${esc(xkPlaqueLine(k, m, p))}</small>${dotHtml(dotAt("practice", k))}</button>`).join("");
    return `<nav class="xk-pls${p.tabs.length === 1 ? " one" : p.tabs.length <= 2 || p.tabs.length === 4 ? " two" : ""}" aria-label="俠客">${cells}</nav>`;
  }

  // 人像：所在地的圖滿版、狀態一行（江湖頁那一條；沒有就不畫，照舊用頂上的狀態列）、墨色人像、名號與小印、戰力
  function xkHero(m, p, mini) {
    const s = p.s, src = xkArt(m);
    const st = typeof jhStatusHtml === "function" ? jhStatusHtml(m) : "";
    const art = src ? `<img class="xk-art" src="${esc(src)}" alt="" decoding="async">` : '<div class="xk-art none"></div>';
    if (mini) return `<section class="xk-hero mini${st ? " st" : ""}">${art}${st}<button class="xk-dim" data-act="xk-close" aria-label="${XK_CLOSE}"></button></section>`;
    const tags = String(s.affiliation || "").split(/\s+/).filter(Boolean).map((t) => `<span class="xk-tag">${esc(t)}</span>`).join("");
    const might = typeof p.x.might === "number" ? `<div class="xk-pw">${XK_MIGHT}<b>${p.x.might | 0}</b></div>` : "";
    return `<section class="xk-hero${st ? " st" : ""}">${art}${st}
      <img class="xk-fig" src="${esc(p.fig)}" alt="" draggable="false">
      <div class="xk-who"><h1>${esc(s.name || "")}</h1>${tags ? `<div class="xk-tags">${tags}</div>` : ""}${might}${p.annals ? `<div class="xk-links">${p.annals}</div>` : ""}</div>
    </section>`;
  }

  // ── 同伴那一塊：親衛一張卡、同伴排成立繪方格、點一位拉起他的卡 ──
  function xkGuardCard(m) {
    const g = m.guard;
    if (!g) return "";
    if (S.xkGuardFull && typeof guardHtml === "function") return `<div class="xk-gd-full">${guardHtml(m)}<button class="btn ghost xk-gd-back" data-act="xk-guard-back">${XK_GUARD_BACK}</button></div>`;
    const face = (g.art && (g.art.face || g.art.hero)) || "";
    const ev = g.event, waiting = (ev && !ev.shown) || (g.schools && g.schools.length);
    const line = ev && ev.shown ? ev.text : waiting ? `${g.name}有事找你。` : (g.bio || ""); // 待 joy 潤
    return `<section class="xk-gd${waiting ? " hot" : ""}">${face ? `<span class="xk-gd-face" style="background-image:url('${esc(face)}')" aria-hidden="true"></span>` : ""}
      <div class="xk-gd-bd"><h3>${esc(g.name)}<span class="xk-seal">${esc(g.band || "")}</span>${dotHtml(typeof guardDot === "function" && guardDot())}</h3>
        <div class="xk-gd-sub">${esc(g.stage_text || "")}${g.path ? `・${esc(g.path)}「${esc(g.title || "")}」` : ""}</div>
        ${line ? `<p>${esc(line)}</p>` : ""}
        <div class="xk-gd-go">${waiting || (ev && ev.shown) ? `<button class="btn primary" data-act="xk-guard">${XK_GUARD_GO}</button>` : ""}<button class="btn ghost" data-act="xk-guard-all">${XK_GUARD_ALL} ›</button></div></div></section>`;
  }
  function xkFace(m, c) {
    const src = m.xiake && m.xiake.faces && m.xiake.faces[c.key];
    return src ? `<span class="xk-mt-face" style="background-image:url('${esc(src)}')"></span>` : `<span class="xk-mt-face tx">${esc((c.name || "").slice(0, 1))}</span>`;
  }
  function xkMatesHtml(m, p) {
    const x = p.x, mates = xkMates(x);
    if (!x.roster_cards) return p.pageOf("mates"); // 舊伺服器沒有 roster_cards：照舊那一頁
    const fight = mates.filter((c) => c.role === "出戰" || c.role === "部下").length;
    const grid = mates.length ? `<div class="xk-mates">${mates.map((c) => {
      const seal = c.role === "候命" ? "" : `<i class="xk-seal">${esc(c.role)}</i>`;
      return `<button class="xk-mt${c.role === "候命" ? "" : " fight"}" data-act="person" data-key="${esc(c.key)}">${xkFace(m, c)}${seal}<b>${esc(c.name)}</b>${c.level != null ? `<small>${c.level | 0} 級</small>` : ""}</button>`;
    }).join("")}</div>` : `<p class="xk-none">${XK_NO_MATES}</p>`;
    const head = `<div class="xk-sec"><h3>${XK_MATES_HEAD}</h3><small>${mates.length ? `出戰 ${fight}・共 ${mates.length}・${XK_MATES_TAP}` : ""}</small></div>`;
    return `${xkGuardCard(m)}${head}${grid}`;
  }
  // 點一位同伴：拉起他的卡（江湖頁點人物同一種）——立繪、第幾級、身上兩門的墨條、出戰／候命、傳功、放回江湖
  function xkPersonCard(m, p) {
    const x = p.x;
    if (S.xkSec !== "mates" || !x.person || x.person === "player") return "";
    const c = (x.roster_cards || []).find((r) => r.key === x.person);
    if (!c) return "";
    const src = m.xiake && m.xiake.faces && m.xiake.faces[c.key];
    const arts = (c.arts || []).map((a) => {
      const lv = Math.max(0, Math.min(10, a.level | 0)), top = a.quality === "絕學";
      return `<div class="xk-ak${top ? " q4" : ""}"><div class="xk-ak-t"><b>${a.name ? esc(a.name) : "尚未習得"}</b><small>${esc(a.kind)}${a.quality ? `・${esc(a.quality)}` : ""}</small></div>${a.name && typeof saInk === "function" ? `<i class="sa-ten" role="meter" aria-valuemin="0" aria-valuemax="10" aria-valuenow="${lv}" aria-label="${esc(a.name)}第${lv}成">${saInk(lv, top)}</i>` : ""}</div>`;
    }).join("");
    const extra = typeof mateExtra === "function" ? mateExtra(x.person_card) : "";
    const follower = x.person.startsWith("follower:");
    const team = follower ? "" : `<button class="btn ${x.on_team ? "" : "primary"}" data-act="mx" data-op="${x.on_team ? "leave" : "join"}">${x.on_team ? "讓他候命" : "讓他出戰"}</button>`; // 待 joy 潤
    const teach = x.lessons && x.lessons.length ? `<button class="btn xk-teach" data-act="xk-teach" aria-expanded="${!!S.xkTeach}"><span>${XK_TEACH}</span><small>${XK_TEACH_SUB}</small></button>` : "";
    const lessons = S.xkTeach && typeof lessonsHtml === "function" ? lessonsHtml(x.lessons) : "";
    const release = x.release ? `<button class="linkish xk-release" data-act="release-mate" data-confirm="${esc(x.release.confirm)}">${XK_RELEASE} ›</button>` : "";
    return `<div class="sheet-bg" data-act="person" data-key="${esc(c.key)}"></div><div class="sheet xk-card" role="dialog" aria-label="${esc(c.name)}">
      <div class="xk-card-pt${src ? "" : " tx"}"${src ? ` style="background-image:url('${esc(src)}')"` : ""}>${src ? "" : `<span>${esc((c.name || "").slice(0, 1))}</span>`}</div>
      <div class="xk-card-in"><h2>${esc(c.name)}<small>${c.level != null ? `第 ${c.level | 0} 級・` : ""}${esc(c.role)}</small></h2>
        ${arts}${extra}${typeof noteAt === "function" ? noteAt("person") : ""}
        <div class="xk-dos">${team}${teach}</div>${lessons}${release}
        <button class="btn ghost xk-card-x" data-act="person" data-key="${esc(c.key)}">${XK_CLOSE}</button></div></div>`;
  }

  // 拉起的那一塊：頂上一條小小的圖與狀態（點了收起），底下那一塊的名字、關閉、內容
  function xkSheetHtml(m, p, k) {
    const name = (p.tabs.find(([t]) => t === k) || [k, k])[1];
    const body = (k === "mates" ? xkMatesHtml(m, p) : p.pageOf(k)).replace(`<h3>${name}</h3>`, ""); // 那一頁自己的小標題跟拉起的這一塊同名：不寫第二次
    return `<section class="xk-sheet sec-${esc(k)}" aria-label="${esc(name)}"><div class="xk-grip" aria-hidden="true"></div>
      <div class="xk-sh"><h2>${esc(name)}</h2>${dotHtml(dotAt("practice", k))}<button class="xk-x" data-act="xk-close" aria-label="${XK_CLOSE}">✕</button></div>
      <div class="msg" id="mx-msg">${S.message}</div>${body}</section>`;
  }

  function xkPageHtml(m, p) {
    try { return xkPage(m, p); } catch (e) { if (typeof console !== "undefined") console.error(e); return p.pageOf("arts"); }
  }
  function xkPage(m, p) {
    // 別處跳過來（S.heroTab 變了）：拉起那一塊；那一塊已經沒有了（例如叛出師門）就收起
    if (S.heroTab && S.heroTab !== S.xkSeen) S.xkSec = S.heroTab;
    S.xkSeen = S.heroTab;
    if (S.xkSec && !p.tabs.some(([k]) => k === S.xkSec)) S.xkSec = null;
    const tail = `${p.meltGo || ""}${p.drawer || ""}`;
    if (S.xkSec) return `<div class="xk-page open">${xkHero(m, p, true)}${xkSheetHtml(m, p, S.xkSec)}${xkPersonCard(m, p)}${tail}</div>`;
    return `<div class="xk-page">${p.guide || ""}${xkHero(m, p, false)}${xkProse(m, p.x)}<div class="msg" id="mx-msg">${S.message}</div>${xkEyeHtml(m, p)}${xkPlaques(m, p)}${tail}</div>`;
  }

  function xkGo(sec) {
    S.heroTab = sec; S.xkSeen = sec; S.xkSec = sec;
    S.pdrawer = false; S.xkTeach = false; S.xkGuardFull = false;
    renderPage();
    if (typeof window !== "undefined" && window.scrollTo) window.scrollTo(0, 0);
  }

  async function xiakeClick(act, el, ev) {
    switch (act) {
        case "xk-open": xkGo(el.dataset.sec); break;
        case "xk-close": S.xkSec = null; S.heroTab = null; S.xkSeen = null; S.pdrawer = false; S.xkGuardFull = false; S.person = null; renderPage(); if (window.scrollTo) window.scrollTo(0, 0); break;
        case "xk-later": S.xkLater = [...(S.xkLater || []), el.dataset.key]; S.xkEyeAll = false; renderPage(); break;
        case "xk-eye-all": S.xkEyeAll = !S.xkEyeAll; renderPage(); break;
        case "xk-teach": S.xkTeach = !S.xkTeach; renderPage(); break;
        case "xk-guard-all": S.xkGuardFull = true; renderPage(); break;
        case "xk-guard-back": S.xkGuardFull = false; renderPage(); break;
        case "xk-guard": { // 親衛有事：拉起同伴那一塊、攤開他的整頁；還沒打開的那件事順手打開（鈕在卡上就做那一件，Joy 11/14）
          const g = S.main && S.main.guard;
          S.heroTab = "mates"; S.xkSeen = "mates"; S.xkSec = "mates"; S.xkGuardFull = true;
          if (g && g.event && !g.event.shown) await choose(el, "guard:open");
          else renderPage();
          if (window.scrollTo) window.scrollTo(0, 0);
          break;
        }
    } // xiakeClick
  } // xiakeClick
  registerClicks(xiakeClick, ["xk-open", "xk-close", "xk-later", "xk-eye-all", "xk-teach", "xk-guard-all", "xk-guard-back", "xk-guard"]);

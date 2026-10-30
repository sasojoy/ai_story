/* 天下大勢的網頁前端：走一趟（探索一次走一、三、五段；企劃者 2026-10-29～30，引擎 tianxia/outing.py）。說明見 app.js 檔頭。
 *
 * 伺服器一次算到「下一件要選的事」為止，沿路每一段放在 main.outing.trip.beats；這裡只把已經算好的結果演出來：
 * 斗笠小童在野地四層背景上跑（越近的層捲得越快），到了那一段照類別演動作（撿、打、停步），演完寫一行。
 * 要選的事（事件、有所感、頭目）：畫面停住，按「去看看」收起這一層，玩家在江湖頁照平常選；選完了（trip.can_go）自動接著走、重新打開。
 * 演完一整趟給結算卡。動畫可以 2×、可以略過；系統設定「減少動態」的人直接快轉。圖是 Joy 10/30 生的（web/img/outing/）。
 */
"use strict";

  const OUTING_IMG = "/static/img/outing/";
  // 每一張動作圖幾格（每格 220×220，腳底在 (100, 212)；去背切格的腳本在專案檔案 design/走一趟/sprites.py）
  const OUTING_SHEETS = {
    hero_idle: 4, hero_run: 8, hero_pickup: 6, hero_lift: 3, hero_slash: 6, hero_hit: 3, hero_kneel: 4, hero_meditate: 4, hero_push: 4,
    foe_idle_attack: 8, foe_hit_fall: 6,
  };
  // 野地四層（由遠到近）與各自捲的速度：遠景最慢、前景比角色快、蓋在角色前面。別的地點類型的四層還沒畫，先都用野地
  const OUTING_LAYERS = [["bg_wild_far", 0.1, -30, 400], ["bg_wild_mid", 0.4, 50, 260], ["bg_wild_ground", 1, 210, 150]];
  const OUTING_FRONT = ["bg_wild_front", 1.6, 240, 150];
  const OUTING_W = 480, OUTING_H = 360, OUTING_GY = 300, OUTING_HX = 140; // 4:3，手機上畫面占上半、人物夠大
  const OUTING_CELL = 220, OUTING_AX = 100, OUTING_BY = 212;
  const OUTING_KIND = { material: "料", encounter: "戰", event: "事", insight: "悟" };
  const OUTING_SPEED_KEY = "outing-speed";
  // 畫面上的字（待 joy 潤）
  const OUTING_WAIT = "路上碰到要選的事。";
  const OUTING_AWAY = "去看看";
  const OUTING_CLOSE = "收起";
  const OUTING_AGAIN = "再走一趟";
  const OUTING_SKIP = "略過";
  const OUTING_SET_OFF = "出發";

  // 這一層自己的狀態（不放進 S：每一格動畫都會改，不該讓整頁重畫）
  const OW = { imgs: null, open: false, away: false, shown: 0, played: 0, tasks: [], cur: null, raf: 0, last: 0, scroll: 0, props: [], parts: [],
    hero: { pose: "idle", k: 0, t: 0, runP: 0, kx: 0, red: 0, bubble: "", glow: 0, gold: false }, turbo: false, speed: 1, going: false };

  function outingSpeed() { try { return Number(localStorage.getItem(OUTING_SPEED_KEY)) === 2 ? 2 : 1; } catch (e) { return 1; } }
  function outingSaveSpeed(v) { try { localStorage.setItem(OUTING_SPEED_KEY, String(v)); } catch (e) { /* 存不了就這一頁有效 */ } }

  function outingImages() {
    if (OW.imgs) return OW.imgs;
    OW.imgs = {};
    for (const name of [...Object.keys(OUTING_SHEETS), ...OUTING_LAYERS.map((x) => x[0]), OUTING_FRONT[0]]) {
      const img = new Image();
      img.src = `${OUTING_IMG}${name}.webp`;
      OW.imgs[name] = img;
    }
    return OW.imgs;
  }

  // 探索那一格點開的段數選單（main.outing.picker）：一、三、五段，底下一行「走得越遠，越容易碰上稀有的東西」（不寫倍數，Joy 10/30）
  function outingPickerHtml(m) {
    const o = m.outing;
    return `<div class="card act-explore outing-pick"><div class="outing-segs" role="group" aria-label="走幾段">${o.picker.map((x) => `
      <button class="btn" data-act="outing-go" data-n="${x.n}" ${x.ok ? "" : "disabled"}><span><b>${x.n} 段</b><small>體力 ${x.stamina}</small></span></button>`).join("")}</div>
      <p class="muted small outing-note">${esc(o.note)}</p></div>`;
  }

  async function outingGo(n) {
    await busy(async () => {
      const r = await api("/api/do/outing", n ? { n } : {});
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (n) { OW.shown = 0; OW.away = false; }
      S.wheelSel = null;
      applyMain(r.main);
      if (text) toast(text);
      const trip = r.main.outing && r.main.outing.trip;
      if (trip && trip.beats.length > OW.shown || (trip && trip.end && OW.shown && !n)) outingOpen();
    });
  }

  // 每次拿到新的畫面（setMain 之後）：停在要選的事上、玩家去選了、選完了（can_go）就自己接著走
  function outingSync() {
    const trip = S.main && S.main.outing && S.main.outing.trip;
    // 重新整理頁面（或換了分頁）時那一趟還停在要選的事上：當作已經按過「去看看」，選完照樣接著走（沿路那幾行不重演）
    if (trip && !trip.end && !OW.open && !OW.away && OW.shown === 0) { OW.away = true; OW.shown = OW.played = trip.beats.length; }
    if (!trip || !OW.away || OW.going || S.busy) return;
    if (trip.end) { OW.away = false; outingOpen(); return; }
    if (!trip.can_go) return;
    OW.going = true;
    OW.away = false;
    outingGo(0).finally(() => { OW.going = false; });
  }

  function outingTrip() { return S.main && S.main.outing && S.main.outing.trip; }

  function outingOpen() {
    const trip = outingTrip();
    if (!trip) return;
    outingImages();
    let box = document.getElementById("outing-pop");
    if (!box) {
      box = document.createElement("div");
      box.id = "outing-pop";
      box.className = "outing-wrap";
      box.innerHTML = `<div class="outing-card" role="dialog" aria-label="走一趟">
        <div class="outing-stage"><canvas class="outing-cv" width="${OUTING_W}" height="${OUTING_H}" aria-label="走一趟"></canvas>
        <p class="outing-head"><b class="outing-place"></b><span class="outing-step"></span></p></div>
        <div class="outing-log" aria-live="polite"></div>
        <div class="outing-foot"></div></div>`;
      document.body.appendChild(box);
    }
    if (!OW.raf) { OW.last = performance.now(); OW.raf = requestAnimationFrame(outingFrame); }
    if (!OW.open) {
      OW.open = true;
      OW.speed = outingSpeed();
      if (OW.shown === 0) { OW.played = 0; box.querySelector(".outing-log").innerHTML = ""; OW.props = []; OW.parts = []; OW.hero.pose = "idle"; OW.hero.kx = 0; OW.hero.glow = 0; }
    }
    // 重新整理頁面之後接著走：已經演過的那幾段直接寫回去，不重演
    if (OW.shown && !box.querySelector(".outing-line")) trip.beats.slice(0, OW.shown).forEach((b) => outingLine(b, false));
    box.hidden = false;
    box.querySelector(".outing-place").textContent = trip.place;
    outingQueue(trip);
    outingFoot();
  }

  // 停在要選的事上按「去看看」：這一層先藏起來（沿路那幾行留著），選完接著走時再打開；動畫停掉省電
  function outingHide() {
    OW.open = false;
    const box = document.getElementById("outing-pop");
    if (box) box.hidden = true;
    if (OW.raf) cancelAnimationFrame(OW.raf);
    OW.raf = 0;
  }

  function outingShut() {
    OW.open = false;
    OW.tasks = [];
    OW.cur = null;
    OW.turbo = false;
    const box = document.getElementById("outing-pop");
    if (box) box.remove();
    if (OW.raf) cancelAnimationFrame(OW.raf);
    OW.raf = 0;
  }

  // 底下那一排：走著是速度與略過；停在要選的事上是「去看看」；走完是結算卡
  function outingFoot() {
    const box = document.getElementById("outing-pop");
    const trip = outingTrip();
    if (!box || !trip) return;
    box.querySelector(".outing-step").textContent = `第 ${Math.min(Math.max(OW.played, 1), trip.total)}／${trip.total} 段`;
    const foot = box.querySelector(".outing-foot");
    const walking = OW.cur || OW.tasks.length;
    if (walking) {
      foot.innerHTML = `<div class="outing-ctl"><button class="btn" data-act="outing-speed">速度 ${OW.speed}×</button>
        <button class="btn" data-act="outing-skip">${OUTING_SKIP}</button></div>`;
    } else if (!trip.end) {
      foot.innerHTML = `<div class="outing-wait"><p>${OUTING_WAIT}</p><button class="btn primary" data-act="outing-away">${OUTING_AWAY}</button></div>`;
    } else {
      foot.innerHTML = outingResultHtml(trip);
    }
  }

  // 結算卡：每一段的「得：…　失：…」併起來，同一樣東西加總（「驚羽 ×1」兩次寫「驚羽 ×2」、「氣血 -6」兩次寫「氣血 -12」）
  function outingSum(items) {
    const order = [], got = {};
    for (const x of items) {
      const hit = /^(.*?)\s*([×+-])\s*(\d+)$/.exec(x.g);
      const key = hit ? `${hit[1]}|${hit[2] === "×" ? "×" : "±"}` : x.g;
      if (!(key in got)) { order.push(key); got[key] = { name: hit ? hit[1] : x.g, mark: hit ? hit[2] : "", n: 0, rare: false }; }
      const it = got[key];
      if (hit) it.n += (hit[2] === "-" ? -1 : 1) * Number(hit[3]);
      it.rare = it.rare || x.rare;
    }
    return order.map((k) => {
      const it = got[k];
      const text = !it.mark ? it.name : it.mark === "×" ? `${it.name} ×${it.n}` : `${it.name} ${it.n < 0 ? "-" : "+"}${Math.abs(it.n)}`;
      return { g: text, rare: it.rare };
    });
  }

  function outingResultHtml(trip) {
    const gains = [], losses = [];
    for (const b of trip.beats) {
      for (const part of (b.ledger || "").split("　")) {
        if (part.startsWith("得：")) gains.push(...part.slice(2).split("、").map((g) => ({ g, rare: b.rare && b.kind === "material" })));
        if (part.startsWith("失：")) losses.push(...part.slice(2).split("、").map((g) => ({ g, rare: false })));
      }
    }
    const chips = outingSum(gains).map((x) => `<span class="oc${x.rare ? " rare" : ""}">${esc(x.g)}</span>`).join("");
    const lost = outingSum(losses).map((x) => `<span class="oc down">${esc(x.g)}</span>`).join("");
    return `<div class="outing-result"><p class="outing-title"><b>${esc(trip.title)}</b>・${trip.done} 段</p>
      ${trip.end_line ? `<p class="muted small">${esc(trip.end_line)}</p>` : ""}
      ${chips ? `<p class="outing-chips">${chips}</p>` : ""}${lost ? `<p class="outing-chips">${lost}</p>` : ""}
      <div class="outing-ctl"><button class="btn" data-act="outing-close">${OUTING_CLOSE}</button>
      <button class="btn primary" data-act="outing-again">${OUTING_AGAIN}</button></div></div>`;
  }

  // 一段的帳：「得：…」綠、「失：…」紅
  function outingLedgerHtml(ledger) {
    return ledger.split("　").map((part) => `<small class="${part.startsWith("失：") ? "down" : "up"}">${esc(part)}</small>`).join("");
  }

  function outingLine(b, lost) {
    const box = document.getElementById("outing-pop");
    if (!box) return;
    const log = box.querySelector(".outing-log");
    const row = document.createElement("p");
    row.className = `outing-line${b.rare ? " rare" : ""}${lost ? " bad" : ""}`;
    row.innerHTML = `<span class="k">${OUTING_KIND[b.kind] || "行"}</span><span>${esc(b.text)}${b.ledger ? outingLedgerHtml(b.ledger) : ""}</span>`;
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  // ── 動畫：一串任務（跑過去、做動作、寫一行），時間照速度乘；略過＝快轉到停下或走完 ──
  function outingQueue(trip) {
    while (OW.shown < trip.beats.length) {
      const i = OW.shown, b = trip.beats[i];
      const lost = trip.end === "lost" && i === trip.beats.length - 1;
      OW.tasks.push(outingCall(() => { OW.played = i + 1; OW.hero.bubble = ""; outingFoot(); }), ...outingBeatTasks(b, lost), { dur: 0, end: () => { outingLine(b, lost); outingFoot(); } });
      OW.shown += 1;
    }
    OW.tasks.push({ dur: 0, end: () => { OW.turbo = false; if (trip.end) OW.hero.bubble = ""; outingFoot(); } }); // end：OW.cur 清掉之後才畫底下那一排（不然還當作在走）
  }

  function outingRun(target, gap) {
    return { start() { OW.hero.pose = "run"; }, update(t, d) {
      OW.hero.runP += d * 14;
      const v = 300 * d;
      OW.scroll += v;
      OW.props.forEach((p) => { p.x -= v * (p.par || 1); });
      if (Math.random() < d * 12) outingBurst(OUTING_HX - 14, OUTING_GY - 2, 1, "rgba(150,120,80,.7)", 30);
      return target ? target.x <= OUTING_HX + gap : t >= gap;
    }, end() { OW.hero.pose = "idle"; } };
  }
  function outingPose(name, dur, start) { return { dur, start() { OW.hero.pose = name; OW.hero.k = 0; if (start) start(); }, update(t) { OW.hero.k = Math.min(1, t / (dur * 0.8)); } }; }
  function outingCall(fn) { return { dur: 0, start: fn }; }

  function outingBeatTasks(b, lost) {
    const H = OW.hero;
    if (b.kind === "material") {
      const g = { kind: "glint", x: OUTING_W + 20, rare: b.rare };
      return [outingCall(() => OW.props.push(g)), outingRun(g, 50), outingPose("crouch", 0.45),
        outingCall(() => { g.taken = true; outingBurst(OUTING_HX + 50, OUTING_GY - 6, b.rare ? 40 : 12, b.rare ? "#ffd36e" : "#fff8e6", b.rare ? 200 : 110);
          if (b.rare) { OW.props.push({ kind: "pillar", x: OUTING_HX + 50, a: 1 }); outingFloat(OUTING_HX + 40, OUTING_GY - 200, "稀有", "#b8862a", true); } }),
        outingPose("raise", 0.9), { dur: 0.3 }];
    }
    if (b.kind === "encounter") {
      const foes = [0, 1].map((i) => ({ kind: "foe", x: OUTING_W + 40 + i * 80, flash: 0, fall: 0, fade: 0, dying: false, atk: 0 }));
      const hit = (f) => outingCall(() => { f.flash = 1; outingBurst(f.x, OUTING_GY - 100, 10, "#8a6a48", 140); });
      const atk = (f) => [{ dur: 0.4, update(t) { f.atk = Math.min(1, t / 0.4); f.lunge = -30 * Math.sin(f.atk * Math.PI); }, end() { f.atk = 0; f.lunge = 0; } },
        outingCall(() => { H.red = 1; H.kx = -26; outingBurst(OUTING_HX + 10, OUTING_GY - 100, 10, "#e0665a", 120); }), outingPose("hurt", 0.45)];
      const out = [outingCall(() => OW.props.push(...foes)), outingRun(foes[0], 150), outingPose("stance", 0.3)];
      if (b.won) {
        out.push(outingPose("slash", 0.5), hit(foes[0]), outingCall(() => { foes[0].dying = true; }), { dur: 0.15 }, ...atk(foes[1]),
          outingPose("stance", 0.2), outingPose("slash", 0.5), hit(foes[1]), outingCall(() => { foes[1].dying = true; }), { dur: 0.6 }, outingPose("idle", 0.2));
      } else if (lost) {
        out.push(outingPose("slash", 0.5), hit(foes[0]), ...atk(foes[1]), ...atk(foes[0]), outingPose("kneel", 0.8), { dur: 0.4, start() { H.pose = "kneel"; H.k = 1; } });
      } else { // 平手：互換一招，對手退走
        out.push(outingPose("slash", 0.5), hit(foes[0]), ...atk(foes[1]), { dur: 0.6, update(t, d) { foes.forEach((f) => { f.x += 260 * d; }); } });
      }
      out.push(outingCall(() => { OW.props = OW.props.filter((p) => !foes.includes(p)); }));
      return out;
    }
    // 事件、有所感：跑一段、停步、頭上冒字（要選的就停在這裡，結算交給江湖頁）
    const mark = b.kind === "insight" ? "…" : "！";
    return [outingRun(null, 1.3), outingCall(() => { H.bubble = mark; }), { dur: 0.6 },
      ...(b.kind === "insight" && !b.stop ? [outingPose("sit", 0.4), { dur: 1.2, start() { H.pose = "sit"; H.k = 1; H.glow = 1; H.gold = b.rare; }, end() { H.glow = 0; } }] : []),
      outingCall(() => { if (!b.stop) H.bubble = ""; })];
  }

  function outingFrame(now) {
    const dt = Math.min(0.05, (now - OW.last) / 1000);
    OW.last = now;
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const d = dt * (OW.turbo ? 18 : reduce ? 6 : OW.speed);
    if (!OW.cur && OW.tasks.length) { OW.cur = OW.tasks.shift(); OW.cur.t = 0; if (OW.cur.start) OW.cur.start(); }
    if (OW.cur) {
      OW.cur.t += d;
      const done = OW.cur.update ? OW.cur.update(OW.cur.t, d) : false;
      if (done || (OW.cur.dur != null && OW.cur.t >= OW.cur.dur)) { const c = OW.cur; OW.cur = null; if (c.end) c.end(); }
    }
    const H = OW.hero;
    H.t += d;
    H.red = Math.max(0, H.red - d * 2.2);
    H.kx *= Math.pow(0.02, d);
    for (const p of OW.props) {
      if (p.flash) p.flash = Math.max(0, p.flash - d * 3);
      if (p.dying) { p.fall = Math.min(1, p.fall + d * 2.4); if (p.fall >= 1) p.fade = Math.min(1, p.fade + d * 2); }
      if (p.kind === "pillar") p.a = Math.max(0, p.a - d * 0.5);
    }
    outingDraw(d);
    OW.raf = requestAnimationFrame(outingFrame);
  }

  function outingTile(cx, img, par, y, h) {
    if (!img || !img.complete || !img.naturalWidth) return;
    const w = img.naturalWidth * h / img.naturalHeight, o = ((OW.scroll * par) % w + w) % w;
    for (let x = -o; x < OUTING_W; x += w) cx.drawImage(img, x, y, w + 1, h);
  }

  let outingOff = null;
  function outingSprite(cx, name, i, x, opt = {}) {
    const img = OW.imgs[name];
    if (!img || !img.complete || !img.naturalWidth) return;
    const n = OUTING_SHEETS[name];
    i = ((i % n) + n) % n;
    const k = 0.9 * (opt.scale || 1);
    let src = img, sx = i * OUTING_CELL;
    if (opt.tintA > 0) { // 挨打閃紅、被砍中閃白：在一張小畫布上把那一格塗色（只塗有畫的地方）
      if (!outingOff) { outingOff = document.createElement("canvas"); outingOff.width = outingOff.height = OUTING_CELL; }
      const o = outingOff.getContext("2d");
      o.clearRect(0, 0, OUTING_CELL, OUTING_CELL);
      o.globalCompositeOperation = "source-over";
      o.drawImage(img, sx, 0, OUTING_CELL, OUTING_CELL, 0, 0, OUTING_CELL, OUTING_CELL);
      o.globalCompositeOperation = "source-atop";
      o.globalAlpha = opt.tintA;
      o.fillStyle = opt.tint;
      o.fillRect(0, 0, OUTING_CELL, OUTING_CELL);
      o.globalAlpha = 1;
      src = outingOff;
      sx = 0;
    }
    cx.save();
    cx.globalAlpha = opt.alpha == null ? 1 : opt.alpha;
    cx.translate(x, OUTING_GY);
    if (opt.flip) cx.scale(-1, 1);
    cx.drawImage(src, sx, 0, OUTING_CELL, OUTING_CELL, -OUTING_AX * k, -OUTING_BY * k, OUTING_CELL * k, OUTING_CELL * k);
    cx.restore();
  }

  function outingHeroFrame() {
    const H = OW.hero, k = H.k;
    switch (H.pose) {
      case "run": return ["hero_run", Math.floor(H.runP)];
      case "crouch": return ["hero_pickup", Math.min(5, Math.floor(k * 6))];
      case "raise": return ["hero_lift", Math.min(2, Math.floor(k * 3))];
      case "stance": return ["hero_slash", 0];
      case "slash": return ["hero_slash", 1 + Math.min(4, Math.floor(k * 5))];
      case "hurt": return ["hero_hit", Math.min(2, Math.floor(k * 3))];
      case "kneel": return ["hero_kneel", Math.min(3, Math.floor(k * 4))];
      case "sit": return ["hero_meditate", Math.floor(H.t * 2.5)];
      default: return ["hero_idle", Math.floor(H.t * 4)];
    }
  }

  function outingDraw(d) {
    const cv = document.querySelector("#outing-pop .outing-cv");
    if (!cv || !OW.imgs) return;
    const cx = cv.getContext("2d"), I = OW.imgs, H = OW.hero, now = performance.now();
    cx.fillStyle = "#efe6d2";
    cx.fillRect(0, 0, OUTING_W, OUTING_H);
    for (const [name, par, y, h] of OUTING_LAYERS) outingTile(cx, I[name], par, y, h);
    for (const p of OW.props) {
      if (p.kind === "glint" && !p.taken) {
        cx.fillStyle = p.rare ? `rgba(255,200,80,${0.5 + 0.5 * Math.sin(now / 120)})` : `rgba(255,255,240,${0.5 + 0.5 * Math.sin(now / 120)})`;
        outingStar(cx, p.x, OUTING_GY, p.rare ? 11 : 8);
      } else if (p.kind === "pillar") {
        const g = cx.createLinearGradient(0, 0, 0, OUTING_GY);
        g.addColorStop(0, "rgba(255,214,120,0)");
        g.addColorStop(1, `rgba(255,214,120,${0.6 * p.a})`);
        cx.fillStyle = g;
        cx.fillRect(p.x - 24, 0, 48, OUTING_GY);
      } else if (p.kind === "foe") {
        const x = p.x + (p.lunge || 0), opt = { flip: true, scale: 0.85 };
        if (p.dying) outingSprite(cx, "foe_hit_fall", 1 + Math.min(4, Math.floor(p.fall * 5)), x, { ...opt, alpha: 1 - p.fade });
        else if (p.flash > 0) outingSprite(cx, "foe_hit_fall", 0, x, { ...opt, tint: "#fff", tintA: p.flash * 0.8 });
        else if (p.atk > 0) outingSprite(cx, "foe_idle_attack", 4 + Math.min(3, Math.floor(p.atk * 4)), x, opt);
        else outingSprite(cx, "foe_idle_attack", Math.floor(now / 180 + p.x) % 4, x, opt);
      }
    }
    if (H.glow > 0) {
      const r0 = (now / 14) % 60;
      for (let i = 0; i < 3; i++) {
        const r = 24 + ((r0 + i * 20) % 60);
        cx.strokeStyle = `${H.gold ? "rgba(214,160,40," : "rgba(47,122,98,"}${H.glow * (1 - r / 84)})`;
        cx.lineWidth = 3;
        cx.beginPath();
        cx.ellipse(OUTING_HX, OUTING_GY - 60, r * 1.9, r, 0, 0, 7);
        cx.stroke();
      }
    }
    const [name, i] = outingHeroFrame();
    outingSprite(cx, name, i, OUTING_HX + H.kx, { tint: "#ffe9e0", tintA: H.red * 0.6 }); // 挨打閃一下淡色，不把整個人塗紅
    if (H.bubble) {
      const x = OUTING_HX + H.kx + 38, y = OUTING_GY - 204;
      cx.fillStyle = "#fffaf0";
      cx.strokeStyle = "#3b3128";
      cx.lineWidth = 2;
      cx.beginPath();
      cx.ellipse(x, y, 18, 17, 0, 0, 7);
      cx.fill();
      cx.stroke();
      cx.fillStyle = "#b23a2b";
      cx.font = '900 24px "Noto Serif TC", serif';
      cx.textAlign = "center";
      cx.fillText(H.bubble, x, y + 9);
    }
    const [fname, par, y, h] = OUTING_FRONT;
    cx.globalAlpha = 0.95;
    outingTile(cx, I[fname], par, y, h);
    cx.globalAlpha = 1;
    for (const p of OW.parts) {
      p.life += d; p.x += p.vx * d; p.y += p.vy * d;
      if (!p.text) p.vy += 160 * d;
      const a = Math.max(0, 1 - p.life / p.max);
      cx.globalAlpha = a;
      if (p.text) {
        cx.font = `700 ${p.size}px "Noto Serif TC", serif`;
        cx.textAlign = "center";
        cx.strokeStyle = "rgba(255,250,235,.85)";
        cx.lineWidth = 5;
        cx.strokeText(p.text, p.x, p.y);
        cx.fillStyle = p.col;
        cx.fillText(p.text, p.x, p.y);
      } else {
        cx.fillStyle = p.col;
        cx.fillRect(p.x, p.y, p.size, p.size);
      }
      cx.globalAlpha = 1;
    }
    OW.parts = OW.parts.filter((p) => p.life < p.max);
  }

  function outingStar(cx, x, y, r) {
    cx.beginPath();
    for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4, rr = i % 2 ? r * 0.35 : r; cx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); }
    cx.closePath();
    cx.fill();
  }
  function outingBurst(x, y, n, col, spd) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * 6.28, v = (0.4 + Math.random()) * spd;
      OW.parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 40, life: 0, max: 0.6 + Math.random() * 0.4, col, size: 2 + Math.random() * 3 });
    }
  }
  function outingFloat(x, y, text, col, big) { OW.parts.push({ x, y, vx: 0, vy: -55, life: 0, max: 1.1, col, text, size: big ? 30 : 24 }); }

  // 點擊（app.js 的總處理器轉過來）：回 true 表示是這一層的鈕
  async function outingClick(act, el) {
    switch (act) {
      case "outing-go": await outingGo(Number(el.dataset.n)); return true;
      case "outing-speed": OW.speed = OW.speed === 2 ? 1 : 2; outingSaveSpeed(OW.speed); outingFoot(); return true;
      case "outing-skip": OW.turbo = true; return true;
      case "outing-away": OW.away = true; outingHide(); return true;
      case "outing-close": outingShut(); OW.shown = 0; return true;
      case "outing-again": outingShut(); OW.shown = 0; S.wheelSel = "explore"; renderPage(); revealMoveCard(); return true;
      default: return false;
    }
  }

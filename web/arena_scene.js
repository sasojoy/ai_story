/* 天下大勢的網頁前端：一句話自創的絕招（Joy 2026-11-01「我是要可以讓玩家『自創』……例如他說『一劍寒光九萬里』
 * 或是『背後出現一座大佛擊出一掌』」）。說明見 app.js 檔頭。
 *
 * 伺服器給一份導演稿（tianxia/features/looks/scenes.py：{name, glow, beats:[{op, at, …}], arts}），這裡照稿畫：
 * 每一拍的時間、能做什麼都是表上定好的，這裡只負責怎麼畫。擂台上綁了這一招的那一門的戰法發動的那一回合（fight.bursts）
 * 演一整段（約 3.7 秒）；萬寶閣下單前寫一句就能先看（scenePreview）。法相、巨物（大佛、佛掌……）是管理者上傳的圖
 * （/api/looks/img/m<id>/art1、art2）；還沒有圖（預覽）就用程式畫的金色剪影頂著。
 */
"use strict";

const SCENE_LEN = 3700; // 一整段多長（毫秒）：稿的 length（3300）加上收尾
const SCENE_TONES = { "冷": "4,10,22", "暖": "16,10,4", "夜": "6,8,18", "紫": "14,6,22" };
const SC = { cache: {}, wait: {}, art: {} }; // 導演稿（照招式 id）、抓到一半的、法相巨物的圖

// 擂台上要演的那一招的稿（第一次用到才抓；抓不到就是 null，照舊疊光效）
function sceneFor(mid) {
  if (!mid || !/^m\d+$/.test(mid)) return null;
  if (mid in SC.cache) return SC.cache[mid];
  if (!SC.wait[mid] && typeof fetch === "function") {
    SC.wait[mid] = true;
    fetch(`/api/looks/scene/${mid}`, { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { SC.cache[mid] = d && d.scene ? d.scene : null; if (SC.cache[mid]) sceneArts(mid, SC.cache[mid]); })
      .catch(() => { SC.cache[mid] = null; });
  }
  return null;
}
function sceneArts(mid, sc) {
  for (const a of sc.arts || []) {
    const key = `${mid}/${a.slot}`;
    if (SC.art[key] || typeof Image !== "function") continue;
    const im = new Image();
    im.src = `/api/looks/img/${mid}/${a.slot}${window.LOOKS_VER ? `?v=${window.LOOKS_VER}` : ""}`;
    SC.art[key] = im;
  }
}
const sceneOk = (im) => im && im.complete && im.naturalWidth > 0;
const sceneSeg = (t, a, b) => Math.max(0, Math.min(1, (t - a) / (b - a)));
const sceneEase = (k) => 1 - Math.pow(1 - k, 3);
function sceneRgba(c, a) {
  const m = /^#([0-9a-f]{6})$/i.exec(c || "") ? c : "#ffd27a";
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(m.slice(i, i + 2), 16));
  return `rgba(${r},${g},${b},${a})`;
}
const sceneHas = (sc, op) => (sc.beats || []).find((b) => b.op === op) || null;
// 主攻打中的那一刻：對手從這時候開始受擊
function sceneImpact(sc) {
  if (sceneHas(sc, "巨物飛擊")) return 2250;
  if (sceneHas(sc, "飛劍")) return 1700;
  return 1750; // 光束
}

// 還沒有圖時的剪影：佛像、手掌，其他的寫那個字
function sceneBuddha(cx, x, y, s, a, glow) {
  cx.save(); cx.globalAlpha = a; cx.translate(x, y); cx.scale(s, s);
  cx.shadowColor = sceneRgba(glow, 0.9); cx.shadowBlur = 40;
  const g = cx.createLinearGradient(0, -230, 0, 40); g.addColorStop(0, "#ffe7a6"); g.addColorStop(1, "#b07a22");
  cx.fillStyle = g;
  cx.strokeStyle = sceneRgba(glow, 0.8); cx.lineWidth = 6; cx.beginPath(); cx.arc(0, -168, 72, 0, Math.PI * 2); cx.stroke();
  cx.beginPath(); cx.moveTo(-150, 40); cx.quadraticCurveTo(-150, -90, -60, -110); cx.lineTo(60, -110); cx.quadraticCurveTo(150, -90, 150, 40); cx.closePath(); cx.fill();
  cx.fillRect(-22, -130, 44, 26);
  cx.beginPath(); cx.ellipse(0, -172, 46, 54, 0, 0, Math.PI * 2); cx.fill();
  cx.beginPath(); cx.arc(0, -228, 20, 0, Math.PI * 2); cx.fill();
  cx.restore();
}
function scenePalm(cx, x, y, s, a, glow) {
  cx.save(); cx.globalAlpha = a; cx.translate(x, y); cx.scale(s, s);
  cx.shadowColor = sceneRgba(glow, 0.95); cx.shadowBlur = 30;
  cx.fillStyle = "#f0c46a";
  const rr = (x0, y0, w, h) => { cx.beginPath(); if (cx.roundRect) cx.roundRect(x0, y0, w, h, 8); else cx.rect(x0, y0, w, h); cx.fill(); };
  rr(-34, -30, 68, 70); rr(-34, -86, 15, 62); rr(-17, -98, 15, 74); rr(0, -94, 15, 70); rr(17, -80, 15, 56);
  cx.save(); cx.translate(-34, 6); cx.rotate(-0.8); rr(-8, -46, 16, 50); cx.restore();
  cx.restore();
}
function sceneGlyph(cx, x, y, size, a, glow, text) {
  cx.save(); cx.globalAlpha = a; cx.font = `900 ${size}px "Noto Serif TC", serif`; cx.textAlign = "center"; cx.textBaseline = "middle";
  cx.shadowColor = sceneRgba(glow, 0.95); cx.shadowBlur = 36; cx.fillStyle = "#ffe7a6"; cx.fillText(text, x, y); cx.restore();
}
// 法相、巨物：有圖畫圖（照高度縮），沒有就畫剪影
function sceneThing(cx, img, label, x, y, h, a, glow, kind) {
  if (sceneOk(img)) {
    const w = (img.naturalWidth * h) / img.naturalHeight;
    cx.save(); cx.globalAlpha = a; cx.shadowColor = sceneRgba(glow, 0.9); cx.shadowBlur = 30;
    cx.drawImage(img, x - w / 2, y - h, w, h); cx.restore();
    return;
  }
  if (kind === "法相" && /佛|菩薩|羅漢|金剛|明王/.test(label)) sceneBuddha(cx, x, y, h / 270, a, glow);
  else if (kind === "巨物" && /掌|拳|指|爪|印/.test(label)) scenePalm(cx, x, y - h / 2, h / 130, a, glow);
  else sceneGlyph(cx, x, y - h / 2, h * 0.8, a, glow, (label || "").slice(-1));
}

// 一整段：env 給畫布、出手的人與對手的位置、怎麼畫人與地面（arena_anim.js 的 ringFigure、場地）
// env = { cx, W, H, GY, dir（1 往右打、-1 往左打）, me: x, foe: x, ground(), body(who, sheet, i, lunge, filter), mid（招式 id，抓圖用）}
function scenePaint(env, sc, t) {
  const { cx, W, H, GY, dir } = env;
  const glow = sc.glow || "#ffd27a";
  const casterX = env.me, foeX = env.foe, tgt = [foeX, 205];
  const hit = sceneImpact(sc), end = sc.length || 3300;
  const figure = sceneHas(sc, "法相"), thrown = sceneHas(sc, "巨物飛擊"), swords = sceneHas(sc, "飛劍"), beam = sceneHas(sc, "光束");
  const mark = sceneHas(sc, "異狀"), fall = sceneHas(sc, "飄落"), quake = sceneHas(sc, "震地");
  const img = (slot) => (slot && env.mid ? SC.art[`${env.mid}/${slot}`] : null);
  // 震
  let shake = quake && t >= 200 && t < 900 ? 0.35 : 0;
  if (t >= hit && t < hit + 350) shake += 1.4 * (1 - sceneSeg(t, hit, hit + 350));
  if (t >= 2600 && t < 2850) shake += 1.2 * (1 - sceneSeg(t, 2600, 2850));
  cx.save();
  if (shake > 0) cx.translate(Math.sin(t * 0.11) * 8 * shake, Math.cos(t * 0.17) * 5 * shake);
  env.ground();
  const dark = sceneSeg(t, 0, 380) * (1 - sceneSeg(t, end, end + 400));
  const tone = SCENE_TONES[(sceneHas(sc, "暗場") || {}).tone] || SCENE_TONES["夜"];
  if (dark > 0) { cx.fillStyle = `rgba(${tone},${0.84 * dark})`; cx.fillRect(0, 0, W, H); }
  // 飄落
  const drift = fall ? sceneSeg(t, 700, 1100) * (1 - sceneSeg(t, end, end + 400)) : 0;
  if (drift > 0) {
    const col = { "雪": "230,245,255", "花": "255,170,200", "葉": "170,200,110", "火星": "255,170,80" }[fall.kind] || "230,245,255";
    const up = fall.kind === "火星" ? -1 : 1;
    cx.fillStyle = `rgba(${col},${0.8 * drift})`;
    for (let j = 0; j < 90; j++) {
      const x = (j * 137.5 + t * (0.02 + (j % 5) * 0.006)) % W, y = (((j * 71) % H + up * t * (0.04 + (j % 3) * 0.02)) % H + H) % H;
      cx.fillRect(x, y, fall.kind === "花" || fall.kind === "葉" ? 4 : 2, 2);
    }
  }
  // 法相：在出手的人背後升起
  const out = sceneSeg(t, 2700, 3300);
  if (figure) {
    const rise = sceneEase(sceneSeg(t, 350, 1100));
    if (rise > 0) sceneThing(cx, img(figure.art), figure.label, casterX - 20 * dir, GY + 40 + (1 - rise) * 160 - (sceneOk(img(figure.art)) ? 40 : 0), 300, 0.75 * rise * (1 - out), glow, "法相");
  }
  // 蓄勢的光
  const aura = sceneSeg(t, 250, 700) * (1 - sceneSeg(t, hit, hit + 300));
  if (aura > 0) {
    const g = cx.createRadialGradient(casterX, GY - 80, 4, casterX, GY - 80, 120);
    g.addColorStop(0, sceneRgba(glow, 0.55 * aura)); g.addColorStop(1, sceneRgba(glow, 0));
    cx.fillStyle = g; cx.fillRect(casterX - 140, GY - 210, 280, 230);
    cx.strokeStyle = sceneRgba(glow, 0.6 * aura); cx.lineWidth = 2;
    cx.beginPath(); cx.ellipse(casterX, GY + 2, 76 + 10 * Math.sin(t / 120), 12, 0, 0, Math.PI * 2); cx.stroke();
  }
  // 出手的人：舉起來停住，主攻放出去時劈下
  const release = thrown ? 1500 : beam ? 1300 : 2650;
  const meI = t < 250 ? 0 : t < release ? 1 : 3 + Math.floor(sceneSeg(t, release, release + 400) * 2.99);
  env.body("me", "atk", meI, t >= release && t < release + 500 ? Math.sin(sceneSeg(t, release, release + 500) * Math.PI) * 30 : 0, "");
  // 對手：打中了受擊，最後跪倒
  const frost = mark && mark.kind === "冰封" ? sceneSeg(t, 2050, 2300) * (1 - sceneSeg(t, 2600, 2700)) : 0;
  const tint = frost > 0 ? `saturate(${1 - 0.8 * frost}) brightness(${1 + 0.4 * frost}) hue-rotate(${170 * frost}deg)` : "";
  if (t >= 2600) env.body("foe", "hero_bare_kneel", Math.floor(sceneSeg(t, 2600, 3000) * 3.99), 0, "");
  else if (t >= hit) env.body("foe", "hero_bare_hit", Math.floor((t - hit) / 90) % 3, -10, tint);
  else env.body("foe", "hero_bare_idle", Math.floor(t / 230) % 4, 0, "");
  // 飛劍
  if (swords) sceneSwords(env, sc, swords, t, tgt, glow);
  // 光束：從出手那一帶一路貫出畫面
  if (beam && t >= 1300 && t < 2700) {
    const grow = sceneEase(sceneSeg(t, 1300, 1700)), fade = 1 - sceneSeg(t, 2200, 2700);
    const x0 = casterX + 60 * dir, reach = sceneEase(sceneSeg(t, 1650, 1950)) * (W + 400);
    const len = Math.max(40 * grow, reach), th = 3 + 20 * grow * fade;
    cx.save(); cx.shadowColor = sceneRgba(glow, 1); cx.shadowBlur = 30;
    cx.fillStyle = sceneRgba(glow, 0.95 * fade); cx.fillRect(dir > 0 ? x0 : x0 - len, 196 - th / 2, len, th);
    cx.fillStyle = `rgba(255,255,255,${fade})`; cx.fillRect(dir > 0 ? x0 : x0 - len, 196 - th / 6, len, th / 3);
    cx.restore();
  }
  // 巨物飛擊：從法相胸前（沒有法相就是出手的人）推出去，越飛越大
  if (thrown && t >= 1500 && t < 2500) {
    const k = sceneEase(sceneSeg(t, 1500, 2250)), sx = casterX + 40 * dir, sy = figure ? 130 : 160;
    const x = sx + (tgt[0] - sx) * k, y = sy + (tgt[1] - sy) * k, h = 90 + 120 * k, a = 1 - sceneSeg(t, 2300, 2500);
    for (let j = 1; j <= 3; j++) sceneThing(cx, img(thrown.art), thrown.label, x - j * 40 * k * dir, y + h / 2, h * (1 - j * 0.08), a * 0.18, glow, "巨物");
    sceneThing(cx, img(thrown.art), thrown.label, x, y + h / 2, h, a, glow, "巨物");
  }
  if (thrown && t >= 2250 && t < 3300) {
    const k = sceneSeg(t, 2250, 3300);
    cx.strokeStyle = sceneRgba(glow, 0.9 * (1 - k)); cx.lineWidth = 7 * (1 - k) + 1;
    cx.beginPath(); cx.arc(tgt[0], tgt[1], 20 + 260 * sceneEase(k), 0, Math.PI * 2); cx.stroke();
  }
  // 異狀
  if (frost > 0) {
    cx.strokeStyle = `rgba(220,245,255,${0.9 * frost})`; cx.lineWidth = 2;
    for (let j = 0; j < 14; j++) { const a = j * 0.9, r = 30 + (j % 4) * 14; cx.beginPath(); cx.moveTo(tgt[0], tgt[1] + 10); cx.lineTo(tgt[0] + Math.cos(a) * r, tgt[1] + 10 + Math.sin(a) * r * 1.2); cx.stroke(); }
  }
  if (mark && mark.kind === "雷擊" && t >= 2050 && t < 2600 && Math.floor(t / 70) % 2 === 0) {
    cx.strokeStyle = "rgba(230,215,255,0.95)"; cx.lineWidth = 3; cx.shadowColor = sceneRgba(glow, 1); cx.shadowBlur = 20;
    cx.beginPath(); let x = tgt[0] + ((t / 70) % 3 - 1) * 20, y = 0; cx.moveTo(x, y);
    while (y < tgt[1] + 40) { y += 26; x += ((y * 7) % 3 - 1) * 14; cx.lineTo(x, y); }
    cx.stroke(); cx.shadowBlur = 0;
  }
  if (mark && mark.kind === "火焚" && t >= 2050 && t < 2900) {
    const k = sceneSeg(t, 2050, 2900);
    for (let j = 0; j < 26; j++) {
      const y = tgt[1] + 60 - ((t * 0.12 + j * 23) % 110), x = tgt[0] + Math.sin(j * 2.1 + t / 90) * 26;
      cx.fillStyle = `rgba(255,${120 + (j % 4) * 30},60,${0.75 * (1 - k)})`; cx.beginPath(); cx.arc(x, y, 5 + (j % 3) * 2, 0, Math.PI * 2); cx.fill();
    }
  }
  if (mark && mark.kind === "冰封" && t >= 2600 && t < 3300) {
    const k = sceneSeg(t, 2600, 3300); cx.fillStyle = `rgba(220,245,255,${1 - k})`;
    for (let j = 0; j < 40; j++) { const a = j * 2.4, r = 10 + 200 * sceneEase(k) * ((j % 5) / 5 + 0.3); cx.fillRect(tgt[0] + Math.cos(a) * r, tgt[1] + Math.sin(a) * r * 0.7 + 60 * k * k, 6, 3); }
  }
  cx.restore();
  // 上下黑邊、招名、白光（不跟著震）
  const lb = sceneSeg(t, 0, 350) * (1 - sceneSeg(t, end + 100, end + 500)) * 30;
  if (lb > 0) { cx.fillStyle = "#000"; cx.fillRect(0, 0, W, lb); cx.fillRect(0, H - lb, W, lb); }
  const title = sceneHas(sc, "落款");
  if (title && sc.name) sceneTitle(cx, W, t, title.at, sc.name, glow);
  const flashAt = thrown ? 2250 : 2600;
  if (t >= flashAt && t < flashAt + 350) { cx.fillStyle = `rgba(255,248,230,${0.8 * (1 - sceneSeg(t, flashAt, flashAt + 350))})`; cx.fillRect(0, 0, W, H); }
}
function sceneTitle(cx, W, t, at, name, glow) {
  const a = sceneSeg(t, at, at + 200) * (1 - sceneSeg(t, at + 900, at + 1150));
  if (a <= 0) return;
  const pop = 1 + 0.5 * (1 - sceneEase(sceneSeg(t, at, at + 200)));
  cx.save(); cx.translate(W / 2 - 24, 70); cx.scale(pop, pop); cx.globalAlpha = a;
  cx.font = '900 56px "Noto Serif TC", serif'; cx.textAlign = "center"; cx.textBaseline = "middle";
  cx.shadowColor = sceneRgba(glow, 0.9); cx.shadowBlur = 24; cx.fillStyle = "#fff4dc"; cx.fillText(name, 0, 0);
  const w = cx.measureText(name).width; cx.shadowBlur = 0;
  cx.fillStyle = "#b8322a"; cx.fillRect(w / 2 + 10, -32, 42, 42);
  cx.fillStyle = "#fff4dc"; cx.font = '900 30px "Noto Serif TC", serif'; cx.fillText("絕", w / 2 + 31, -10);
  cx.restore();
}
// 飛劍：半空列陣（弧、輪、雨），一把一把射向對手
function sceneSwords(env, sc, b, t, tgt, glow) {
  const { cx, dir } = env, n = b.count || 48, gap = 900 / n, form = b.form || "弧";
  const home = (k) => {
    const u = n > 1 ? k / (n - 1) : 0.5, seed = ((k * 7919) % 97) / 97;
    if (form === "輪") { const a = u * Math.PI * 2 + (t - 700) / 900; return { x: tgt[0] + Math.cos(a) * 150, y: tgt[1] - 20 + Math.sin(a) * 85, seed }; }
    if (form === "雨") return { x: tgt[0] - 150 + u * 300 + (seed - 0.5) * 30, y: -30 - seed * 120 + sceneEase(sceneSeg(t, 900, 1500)) * 60, seed };
    const a = Math.PI * (1.08 + 0.84 * u), r = 190 + (k % 3) * 26;
    return { x: tgt[0] - 10 * dir + Math.cos(a) * r * dir, y: 150 + Math.sin(a) * r * 0.62, seed };
  };
  const sword = env.sword;
  for (let k = 0; k < n; k++) {
    const h = home(k), order = (k * 29) % n, go = 1650 + order * gap, fly = sceneSeg(t, go, go + 260);
    const appear = sceneSeg(t, 700 + order * (700 / n), 900 + order * (700 / n));
    if (appear <= 0) continue;
    const tx = tgt[0] + (h.seed - 0.5) * 40, ty = tgt[1] + (h.seed - 0.5) * 50;
    if (fly >= 1) { // 打中：火花
      const since = t - (go + 260);
      if (since < 260) {
        const q = since / 260; cx.strokeStyle = `rgba(255,240,200,${1 - q})`; cx.lineWidth = 1.6;
        for (let j = 0; j < 5; j++) { const a = h.seed * 6 + j * 1.25; cx.beginPath(); cx.moveTo(tx + Math.cos(a) * (2 + 10 * q), ty + Math.sin(a) * (2 + 10 * q)); cx.lineTo(tx + Math.cos(a) * (6 + 26 * q), ty + Math.sin(a) * (6 + 26 * q)); cx.stroke(); }
      }
      continue;
    }
    const turn = form === "雨" ? 1 : sceneEase(sceneSeg(t, 1250 + h.seed * 200, 1600));
    const toFoe = Math.atan2(ty - h.y, tx - h.x);
    const ang = form === "雨" ? Math.PI / 2 : -Math.PI / 2 * (1 - turn) + toFoe * turn;
    let x = h.x, y = h.y + Math.sin(t / 160 + h.seed * 6) * 3 - (1 - sceneEase(appear)) * 30;
    if (fly > 0) {
      const e = fly * fly; x = h.x + (tx - h.x) * e; y = h.y + (ty - h.y) * e;
      cx.strokeStyle = sceneRgba(glow, 0.55 * (1 - fly * 0.4)); cx.lineWidth = 2.4; cx.lineCap = "round";
      cx.beginPath(); cx.moveTo(x - Math.cos(ang) * 60 * fly, y - Math.sin(ang) * 60 * fly); cx.lineTo(x, y); cx.stroke();
    }
    if (!sceneOk(sword)) continue;
    const w = 70, hh = (w * sword.naturalHeight) / sword.naturalWidth;
    cx.save(); cx.globalAlpha = appear; cx.translate(x, y); cx.rotate(ang);
    cx.shadowColor = sceneRgba(glow, 0.95); cx.shadowBlur = fly > 0 ? 26 : 16;
    cx.drawImage(sword, -w * 0.6, -hh / 2, w, hh); cx.restore();
  }
}

// 萬寶閣下單前的預覽：寫一句、按「先看看」，伺服器回稿，在 #scene-preview 那一塊畫布上演（站在擂台上的是自己的樣子）
const SCP = { sc: null, t0: 0, raf: 0 };
function scenePreview(sc) {
  SCP.sc = sc; SCP.t0 = 0;
  if (typeof ringLoad === "function") ringLoad();
  if (!SCP.raf && typeof requestAnimationFrame === "function") SCP.raf = requestAnimationFrame(scenePreviewTick);
}
function scenePreviewTick(now) {
  SCP.raf = 0;
  const cv = typeof document !== "undefined" ? document.getElementById("scene-preview") : null;
  if (!cv || !SCP.sc) return;
  if (!SCP.t0) SCP.t0 = now;
  let t = now - SCP.t0;
  if (t > SCENE_LEN + 700) { SCP.t0 = now; t = 0; }
  sceneOnRing(cv.getContext("2d"), SCP.sc, t, "me", "");
  SCP.raf = requestAnimationFrame(scenePreviewTick);
}
// 在擂台的畫布上演（arena_anim.js 的場地與人）；who 是出招的那一邊
function sceneOnRing(cx, sc, t, who, mid) {
  const me = who === "me";
  const at = { me: RING_X[me ? 0 : 1], foe: RING_X[me ? 1 : 0] };
  const flipOf = { me: !me, foe: me };
  const side = { me: who, foe: me ? "foe" : "me" };
  cx.clearRect(0, 0, RING_W, RING_H);
  scenePaint({
    cx, W: RING_W, H: RING_H, GY: RING_GY, dir: me ? 1 : -1, me: at.me, foe: at.foe, mid, sword: RA.imgs && RA.imgs.weapon_sword,
    ground: () => ringGround(cx),
    body: (role, sheet, i, lunge, filter) => {
      const real = side[role], kind = RA.looks[real];
      const name = sheet === "atk" ? ringAtk(kind) : sheet;
      if (filter) { cx.save(); cx.filter = filter; }
      ringFigure(cx, name, i, at[role], flipOf[role], kind, lunge, RA.looks[`${real}_look`]);
      if (filter) cx.restore();
    },
  }, sc, t);
}

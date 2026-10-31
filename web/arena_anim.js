/* 天下大勢的網頁前端：擂台動畫（企劃者 2026-10-31「擂台也可以把走一趟的角色拿出來用，有攻擊跟受擊甚至是陣亡的動畫」）。說明見 app.js 檔頭。
 *
 * 只演、不算：每按一招，伺服器回來的擂台畫面（shop.fight）已經是這一回合打完的樣子。這裡跟上一回合比兩邊的氣血與氣勢，
 * 掉血多的那一邊受擊、另一邊出招；都沒掉血就是閃身（氣勢往哪邊倒，另一邊閃）。打完了（shop.result）在收場卡上演最後一幕：
 * 大勝的輸家倒地、險勝的輸家跪地、僵持兩邊各出一招收手、落敗的你氣血見底倒地不然跪地。
 * 圖（web/img/arena/）是 Joy 10/31 生的斗笠小子：人畫空手，兵器另外一件一件畫，照每一格手的位置與角度疊上去（設計稿乙案）。
 * 兵器種類照伺服器的 looks（models.WEAPON_KINDS：劍、刀、槍、棍、弓弩、拳腳；空字串＝空手），四種打法各一張出招圖。
 * 去背切格的腳本與每一格手的位置在專案檔案 design/擂台/。系統設定「減少動態」的人直接看最後的樣子。
 */
"use strict";

  const RING_IMG = "/static/img/arena/";
  const RING_BG = ["/static/img/outing/bg_town_far.webp", "/static/img/outing/bg_town_ground.webp"]; // 擂台搭在城裡：借走一趟城鎮那一套的遠景與地面
  // 每一張動作圖幾格（每格 220×220，腳底在 (100, 212)，同走一趟）
  const RING_SHEETS = {
    hero_bare_idle: 4, hero_bare_hit: 3, hero_bare_kneel: 4, hero_bare_dodge: 4, hero_bare_fall: 6,
    hero_atk_slash: 6, hero_atk_pole: 6, hero_atk_fist: 6, hero_atk_shoot: 6,
  };
  // 兵器種類 → [兵器圖, 打法]（揮砍：劍刀；長兵：槍棍；射：弩；拳腳：拳套與空手）
  const RING_ARMS = { "劍": ["sword", "slash"], "刀": ["saber", "slash"], "槍": ["spear", "pole"], "棍": ["staff", "pole"], "弓弩": ["crossbow", "shoot"], "拳腳": ["gauntlet", "fist"] };
  // 兵器圖：畫出來多長（格內單位）、握的那一點在圖上的位置（寬、高的比例）
  const RING_WEAPON = {
    sword: { len: 118, gx: 0.17, gy: 0.5 }, saber: { len: 112, gx: 0.18, gy: 0.5 }, spear: { len: 175, gx: 0.45, gy: 0.5 },
    staff: { len: 170, gx: 0.45, gy: 0.5 }, crossbow: { len: 80, gx: 0.47, gy: 0.42 }, gauntlet: { len: 22, gx: 0.5, gy: 0.5 },
  };
  // 每一格手的位置與兵器角度：[x, y, 角度（度，0 朝右、正數往下）, 兵器畫在身體前（1）或後（0）]。fall 第 3 格兵器脫手、4～6 格掉在地上
  const RING_HAND = {
    hero_bare_idle: [[132, 136, -45, 1], [132, 136, -45, 1], [153, 136, -45, 1], [134, 136, -45, 1]],
    hero_bare_hit: [[119, 120, -70, 1], [161, 119, -20, 1], [157, 134, 10, 1]],
    hero_bare_kneel: [[129, 152, 20, 1], [155, 150, 30, 1], [102, 165, 80, 1], [100, 162, 80, 1]],
    hero_bare_dodge: [[131, 136, -40, 1], [147, 105, -60, 1], [149, 107, -60, 1], [134, 136, -40, 1]],
    hero_bare_fall: [[142, 127, -30, 1], [157, 109, -60, 1], [175, 115, 70, 2], [150, 207, -3, 3], [150, 207, -3, 3], [150, 207, -3, 3]],
    hero_atk_slash: [[128, 145, -40, 1], [67, 95, -125, 0], [87, 98, -165, 0], [147, 133, -5, 1], [158, 133, 25, 1], [123, 147, -30, 1]],
    hero_atk_pole: [[131, 147, -15, 1], [120, 150, -10, 1], [162, 131, 0, 1], [148, 114, -35, 1], [160, 132, 10, 1], [124, 147, -15, 1]],
    hero_atk_fist: [[139, 129, 0, 1], [144, 150, 0, 1], [157, 130, 0, 1], [148, 114, 0, 1], [146, 122, 0, 1], [124, 147, 0, 1]],
    hero_atk_shoot: [[131, 147, 10, 1], [69, 92, -20, 0], [161, 124, 0, 1], [153, 124, -8, 1], [165, 132, 5, 1], [124, 147, 10, 1]],
  };
  const RING_W = 720, RING_H = 320, RING_GY = 292, RING_X = [252, 468], RING_CELL = 220, RING_AX = 100, RING_BY = 212, RING_SCALE = 1.05;

  // 這一塊自己的狀態（不放進 S：每一格動畫都會改，不該讓整頁重畫）
  const RA = { imgs: null, prev: null, q: [], cur: null, raf: 0, looks: { me: "", foe: "" }, hold: null, finaleFor: null };

  function ringLoad() {
    if (RA.imgs) return;
    RA.imgs = {};
    const add = (key, src) => { const im = new Image(); im.src = src; RA.imgs[key] = im; };
    for (const name of Object.keys(RING_SHEETS)) add(name, `${RING_IMG}${name}.webp`);
    for (const w of Object.keys(RING_WEAPON)) add(`weapon_${w}`, `${RING_IMG}weapon_${w}.webp`);
    RING_BG.forEach((src, i) => add(`bg${i}`, src));
  }
  const ringReady = (im) => im && im.complete && im.naturalWidth > 0;
  const ringArms = (kind) => RING_ARMS[kind] || [null, "fist"];
  const ringAtk = (kind) => `hero_atk_${ringArms(kind)[1]}`;
  const ringStill = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // 一個人的一格：身體，加上手上那一件（劍在身前就再把拳頭那一小圈蓋回去，看起來是握著）
  function ringFigure(cx, sheet, i, x, flip, kind, lunge) {
    const img = RA.imgs[sheet];
    if (!ringReady(img)) return;
    const n = RING_SHEETS[sheet];
    i = Math.max(0, Math.min(n - 1, i));
    const hand = (RING_HAND[sheet] || [])[i];
    const wname = ringArms(kind)[0], wimg = wname ? RA.imgs[`weapon_${wname}`] : null, spec = wname ? RING_WEAPON[wname] : null;
    cx.save();
    cx.translate(x + (flip ? -lunge : lunge), RING_GY);
    if (flip) cx.scale(-1, 1);
    cx.scale(RING_SCALE, RING_SCALE);
    cx.translate(-RING_AX, -RING_BY);
    const body = () => cx.drawImage(img, i * RING_CELL, 0, RING_CELL, RING_CELL, 0, 0, RING_CELL, RING_CELL);
    const arm = () => {
      if (!hand || !ringReady(wimg)) return;
      const s = spec.len / wimg.naturalWidth, w = wimg.naturalWidth * s, h = wimg.naturalHeight * s;
      cx.save();
      cx.translate(hand[0], hand[1]);
      cx.rotate((hand[2] * Math.PI) / 180);
      cx.drawImage(wimg, -w * spec.gx, -h * spec.gy, w, h);
      cx.restore();
    };
    const gauntlet = wname === "gauntlet";
    if (!hand || !wimg) body();
    else if (hand[3] === 3) { if (!gauntlet) arm(); body(); } // 掉在地上（拳套戴在手上，不掉）
    else if (hand[3] === 2) { body(); if (!gauntlet) arm(); } // 脫手飛出去
    else if (hand[3] === 0) { arm(); body(); }
    else {
      body();
      arm();
      if (!gauntlet) { cx.save(); cx.beginPath(); cx.arc(hand[0], hand[1], 9, 0, Math.PI * 2); cx.clip(); body(); cx.restore(); }
    }
    cx.restore();
  }

  // 一幕：兩個人各自的動作 {sheet, at（第幾毫秒開始）, dur, keep（演完停在最後一格）}；之前是站著，之後回到站著（keep 的除外）
  const ringIdle = () => ({ sheet: "hero_bare_idle", loop: true });
  const ringAct = (sheet, at, dur, keep = false) => ({ sheet, at, dur, keep });
  function ringStrike(who, hurt) { // who 出手、另一邊受擊（hurt）或閃開
    const other = who === "me" ? "foe" : "me", look = RA.looks[who];
    const beat = { dur: 900 };
    beat[who] = ringAct(ringAtk(look), 0, 560);
    beat[other] = ringAct(hurt ? "hero_bare_hit" : "hero_bare_dodge", 300, hurt ? 380 : 440);
    beat.lunge = who;
    return beat;
  }
  // 這一回合跟上一回合比：誰掉了血
  function ringExchange(a, b) {
    const dMe = a.me - b.me, dFoe = a.foe - b.foe, tol = 0.5;
    if (dMe > tol && dFoe > tol) return dMe > dFoe ? [ringStrike("me", true), ringStrike("foe", true)] : [ringStrike("foe", true), ringStrike("me", true)];
    if (dFoe > tol) return [ringStrike("me", true)];
    if (dMe > tol) return [ringStrike("foe", true)];
    if (b.edge > a.edge) return [ringStrike("me", false)];
    if (b.edge < a.edge) return [ringStrike("foe", false)];
    return [];
  }
  // 收場：照結果演最後一幕，倒地、跪地的那一邊停在最後一格
  function ringFinale(tier, low) {
    if (tier === "僵持") return [ringStrike("me", false), ringStrike("foe", false)];
    const won = tier === "大勝" || tier === "險勝", who = won ? "me" : "foe", loser = won ? "foe" : "me";
    const down = won ? tier === "大勝" : low;
    const beat = { dur: 1500, lunge: who };
    beat[who] = ringAct(ringAtk(RA.looks[who]), 0, 560);
    beat[loser] = ringAct(down ? "hero_bare_fall" : "hero_bare_kneel", 300, down ? 900 : 640, true);
    return [beat];
  }

  // 每次畫好畫面（render、renderShop）之後叫：看是不是有新的一回合或剛收場，排要演的幕
  function ringSync() {
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "arena" || typeof requestAnimationFrame !== "function" || !document.getElementById("ring-stage")) { ringStop(); return; }
    ringLoad();
    const f = shop.fight, r = shop.result && shop.result.id !== S.arenaSeen ? shop.result : null;
    if (f) {
      RA.looks = f.looks || { me: "", foe: "" };
      const now = { id: f.id, round: f.round, me: f.me.hp, foe: f.foe_hp.hp, cap: f.me.cap, edge: f.edge };
      const p = RA.prev;
      if (p && p.id === now.id && now.round > p.round) RA.q.push(...ringExchange(p, now));
      else if (!p || p.id !== now.id) { RA.q = []; RA.cur = null; RA.hold = null; }
      RA.prev = now;
    } else if (r && RA.finaleFor !== r.id) {
      RA.looks = r.looks || RA.looks;
      RA.finaleFor = r.id;
      const p = RA.prev && RA.prev.id === r.id ? RA.prev : null;
      RA.q = ringFinale(r.tier, !p || p.me <= p.cap * 0.25);
      RA.cur = null;
      RA.hold = null;
    }
    if (ringStill()) { // 減少動態：不演，直接停在最後的樣子
      while (RA.q.length) ringSettle(RA.q.shift());
      RA.cur = null;
    }
    if (!RA.raf) RA.raf = requestAnimationFrame(ringTick);
  }
  function ringStop() { if (RA.raf && typeof cancelAnimationFrame === "function") cancelAnimationFrame(RA.raf); RA.raf = 0; }
  function ringSettle(beat) { // 一幕演完：倒地、跪地的停在最後一格
    for (const side of ["me", "foe"]) {
      const a = beat[side];
      if (a && a.keep) { RA.hold = RA.hold || {}; RA.hold[side] = { sheet: a.sheet, i: RING_SHEETS[a.sheet] - 1 }; }
    }
  }

  function ringTick(now) {
    RA.raf = 0;
    const cv = document.getElementById("ring-stage");
    if (!cv) return;
    const cx = cv.getContext("2d");
    if (!RA.cur && RA.q.length) RA.cur = { beat: RA.q.shift(), t0: now };
    let el = 0;
    if (RA.cur) {
      el = now - RA.cur.t0;
      if (el >= RA.cur.beat.dur) { ringSettle(RA.cur.beat); RA.cur = RA.q.length ? { beat: RA.q.shift(), t0: now } : null; el = 0; }
    }
    ringPaint(cx, now, el);
    RA.raf = requestAnimationFrame(ringTick);
  }

  function ringPaint(cx, now, el) {
    cx.clearRect(0, 0, RING_W, RING_H);
    const far = RA.imgs.bg0, ground = RA.imgs.bg1;
    if (ringReady(far)) cx.drawImage(far, 0, 0, far.naturalWidth, far.naturalHeight, -60, -40, (far.naturalWidth * (RING_H + 40)) / far.naturalHeight, RING_H + 40);
    if (ringReady(ground)) { const gh = 110, gw = (ground.naturalWidth * gh) / ground.naturalHeight; for (let x = 0; x < RING_W; x += gw) cx.drawImage(ground, x, RING_H - gh, gw, gh); }
    // 擂台：一塊木台
    cx.fillStyle = "rgba(96, 62, 34, 0.92)";
    cx.fillRect(110, RING_GY - 4, RING_W - 220, 14);
    cx.fillStyle = "rgba(60, 36, 18, 0.9)";
    cx.fillRect(110, RING_GY + 10, RING_W - 220, 18);
    const beat = RA.cur ? RA.cur.beat : null;
    const sides = [["me", RING_X[0], false], ["foe", RING_X[1], true]];
    // 出手的那一個畫在後面（蓋在上面）
    if (beat && beat.lunge === "me") sides.reverse();
    for (const [side, x, flip] of sides) {
      let sheet = "hero_bare_idle", i = Math.floor(now / 230) % 4, lunge = 0;
      const a = beat && beat[side];
      if (a && el >= a.at && el < a.at + a.dur) {
        const k = (el - a.at) / a.dur;
        sheet = a.sheet;
        i = Math.floor(k * RING_SHEETS[sheet]);
        if (beat.lunge === side) lunge = Math.sin(k * Math.PI) * 44;
        else if (sheet === "hero_bare_hit") lunge = -Math.sin(k * Math.PI) * 18;
      } else if (a && a.keep && el >= a.at + a.dur) {
        sheet = a.sheet;
        i = RING_SHEETS[sheet] - 1;
      } else if (RA.hold && RA.hold[side]) {
        sheet = RA.hold[side].sheet;
        i = RA.hold[side].i;
      }
      ringFigure(cx, sheet, i, x, flip, RA.looks[side], lunge);
    }
  }

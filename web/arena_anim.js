/* 天下大勢的網頁前端：擂台動畫（企劃者 2026-10-31「擂台也可以把走一趟的角色拿出來用，有攻擊跟受擊甚至是陣亡的動畫」）。說明見 app.js 檔頭。
 *
 * 只演、不算：每按一招，伺服器回來的擂台畫面（shop.fight）已經是這一回合打完的樣子。兩邊出了哪一招（fight.picks）照招演：
 * 強攻衝上去劈、固守原地架住、奇襲先閃再補一下（Joy 2026-10-31）；只有被剋的那一邊受擊，出一樣的兩邊都受擊（Joy 11/1）。
 * 招式動畫（買來的光效）只在綁了招式的那一門的戰法發動的那一回合疊（fight.bursts），絕招發動的那一下對手受擊、畫面一震（Joy 11/1）。
 * 不知道出了哪一招（放手一搏、舊的一場）照舊：掉血多的那一邊受擊、另一邊出招；都沒掉血就是閃身（氣勢往哪邊倒，另一邊閃）。打完了（shop.result）在收場卡上演最後一幕：
 * 大勝的輸家倒地、險勝的輸家跪地、僵持兩邊各出一招收手、落敗的你氣血見底倒地不然跪地。
 * 圖（web/img/arena/）是 Joy 10/31 生的斗笠小子：人畫空手，兵器另外一件一件畫，照每一格手的位置與角度疊上去（設計稿乙案）。
 * 兵器種類照伺服器的 looks（models.WEAPON_KINDS：劍、刀、槍、棍、弓弩、拳腳；空字串＝空手），四種打法各一張出招圖。
 * 去背切格的腳本與每一格手的位置在專案檔案 design/擂台/。系統設定「減少動態」的人直接看最後的樣子。
 */
"use strict";

  const RING_IMG = "/static/img/arena/";
  const RING_LOOKS = "/static/img/looks/"; // 擂台形象（content/looks.json）：web/img/looks/<id>/ 九張，檔名同預設的斗笠小子
  const RING_BG = ["/static/img/outing/bg_town_far.webp", "/static/img/outing/bg_town_ground.webp"]; // 擂台搭在城裡：借走一趟城鎮那一套的遠景與地面
  // 每一張動作圖幾格（每格 220×220，腳底在 (100, 212)，同走一趟）
  const RING_SHEETS = {
    hero_bare_idle: 4, hero_bare_hit: 3, hero_bare_kneel: 4, hero_bare_dodge: 4, hero_bare_fall: 6, hero_bare_block: 4,
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
    hero_bare_block: [[128, 149, -40, 1], [141, 107, -70, 1], [150, 105, -72, 1], [130, 110, -70, 1]], // 格擋：兵器豎在身前架住
    hero_bare_fall: [[142, 127, -30, 1], [157, 109, -60, 1], [175, 115, 70, 2], [150, 207, -3, 3], [150, 207, -3, 3], [150, 207, -3, 3]],
    hero_atk_slash: [[128, 145, -40, 1], [67, 95, -125, 0], [87, 98, -165, 0], [147, 133, -5, 1], [158, 133, 25, 1], [123, 147, -30, 1]],
    hero_atk_pole: [[131, 147, -15, 1], [120, 150, -10, 1], [162, 131, 0, 1], [148, 114, -35, 1], [160, 132, 10, 1], [124, 147, -15, 1]],
    hero_atk_fist: [[139, 129, 0, 1], [144, 150, 0, 1], [157, 130, 0, 1], [148, 114, 0, 1], [146, 122, 0, 1], [124, 147, 0, 1]],
    hero_atk_shoot: [[131, 147, 10, 1], [69, 92, -20, 0], [161, 124, 0, 1], [153, 124, -8, 1], [165, 132, 5, 1], [124, 147, 10, 1]],
  };
  const RING_W = 720, RING_H = 320, RING_GY = 292, RING_X = [252, 468], RING_CELL = 220, RING_AX = 100, RING_BY = 212, RING_SCALE = 1.05;

  // 這一塊自己的狀態（不放進 S：每一格動畫都會改，不該讓整頁重畫）
  const RA = { imgs: null, hands: {}, prev: null, q: [], cur: null, raf: 0, looks: { me: "", foe: "", me_look: "", foe_look: "", me_fx: "", foe_fx: "" }, hold: null, finaleFor: null };

  function ringLoad() {
    if (RA.imgs) return;
    RA.imgs = {};
    const add = (key, src) => { const im = new Image(); im.src = src; RA.imgs[key] = im; };
    for (const name of Object.keys(RING_SHEETS)) add(name, `${RING_IMG}${name}.webp`);
    RA.add = add;
    for (const w of Object.keys(RING_WEAPON)) add(`weapon_${w}`, `${RING_IMG}weapon_${w}.webp`);
    RING_BG.forEach((src, i) => add(`bg${i}`, src));
  }
  const ringReady = (im) => im && im.complete && im.naturalWidth > 0;
  // 兩邊的形象一確定就把十張抓齊（2026-11-02）：以前是第一次用到那一張才抓，抓好之前 ringBody 回傳預設圖，
  // 所以每換一個動作就閃一次斗笠小子（Joy「有時候動畫中間又會變成斗笠小子」）。帶 ?v= 之後十張都是新網址，更明顯。
  function ringWarm(looks) {
    for (const side of ["me", "foe"]) {
      const sk = skinParts(looks && looks[`${side}_look`]), look = sk.look;
      sk.gear.forEach(gearImg);
      if (!look) continue;
      ringHands(look);
      for (const sheet of Object.keys(RING_SHEETS)) ringBody(look, sheet);
    }
  }
  // ── 疊圖飾品（功能包 looks；Joy 2026-11-02 選「疊圖飾品」）──
  // 「皮」是形象 id，戴了飾品再接「~頭.臉.腰」（tianxia/features/looks/rules.py 的 skin）。飾品的 id 以位置開頭（head_、face_、waist_），
  // 圖 /static/img/looks/<id>/acc.webp 的正中央對準那個位置。位置每一張動作圖、每一格現算（gearMarks），所以任何一套形象都戴得上
  // 畫的順序：腰在最底、頭在最上
  const GEAR_ORDER = ["waist", "face", "head"];
  const GEAR = { imgs: {}, marks: {} };
  function skinParts(skin) {
    const [look = "", rest = ""] = String(skin || "").split("~");
    const gear = rest.split(".").filter((id) => /^(head|face|waist)_[a-z0-9_]+$/.test(id));
    gear.sort((a, b) => GEAR_ORDER.indexOf(a.split("_")[0]) - GEAR_ORDER.indexOf(b.split("_")[0]));
    return { look, gear };
  }
  function gearImg(id) {
    if (!GEAR.imgs[id] && typeof Image === "function") { const im = new Image(); im.src = `/static/img/looks/${id}/acc.webp`; GEAR.imgs[id] = im; }
    return GEAR.imgs[id];
  }
  // 一格裡頭、腰在哪，身體轉了幾度（弧度；0 是站直）：先把細的東西（手、腳、兵器）侵蝕掉，只剩頭和身子。
  // 寬比高大 1.4 倍的是躺下的：照主軸轉，頭在大的那一頭（Q 版頭大）。頭是頭頂往下 30% 那一段的中心，腰是 55～65% 那一段
  // （scratchpad 先拿四套形象、四張動作量過：紅點落在臉上、藍點落在腰帶上，躺下的那幾格也對）
  function gearFrame(px, W, H, x0, cw) {
    const r = 5, k2 = (2 * r + 1) * (2 * r + 1), S = new Int32Array((cw + 1) * (H + 1));
    for (let y = 0; y < H; y++) {
      let row = 0;
      for (let x = 0; x < cw; x++) {
        row += px[(y * W + x0 + x) * 4 + 3] > 32 ? 1 : 0;
        S[(y + 1) * (cw + 1) + x + 1] = S[y * (cw + 1) + x + 1] + row;
      }
    }
    const pts = [], raw = [];
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < cw; x++) {
        if (px[(y * W + x0 + x) * 4 + 3] <= 32) continue;
        raw.push(x, y);
        if (x < r || y < r || x + r >= cw || y + r >= H) continue;
        const a = (y - r) * (cw + 1) + (x - r), b = (y + r + 1) * (cw + 1) + (x + r + 1);
        if (S[b] - S[(y + r + 1) * (cw + 1) + (x - r)] - S[(y - r) * (cw + 1) + (x + r + 1)] + S[a] === k2) pts.push(x, y);
      }
    }
    const p = pts.length >= 100 ? pts : raw;
    const n = p.length / 2;
    if (n < 20) return null;
    let x1 = Infinity, x2 = -Infinity, y1 = Infinity, y2 = -Infinity, mx = 0, my = 0;
    for (let j = 0; j < p.length; j += 2) { x1 = Math.min(x1, p[j]); x2 = Math.max(x2, p[j]); y1 = Math.min(y1, p[j + 1]); y2 = Math.max(y2, p[j + 1]); mx += p[j]; my += p[j + 1]; }
    mx /= n; my /= n;
    let vx = 0, vy = -1;
    if (x2 - x1 + 1 > 1.4 * (y2 - y1 + 1)) {
      let sxx = 0, syy = 0, sxy = 0;
      for (let j = 0; j < p.length; j += 2) { const dx = p[j] - mx, dy = p[j + 1] - my; sxx += dx * dx; syy += dy * dy; sxy += dx * dy; }
      const th = 0.5 * Math.atan2(2 * sxy, sxx - syy);
      vx = Math.cos(th); vy = Math.sin(th);
      let lo = Infinity, hi = -Infinity;
      for (let j = 0; j < p.length; j += 2) { const t = (p[j] - mx) * vx + (p[j + 1] - my) * vy; lo = Math.min(lo, t); hi = Math.max(hi, t); }
      let a = 0, b = 0;
      for (let j = 0; j < p.length; j += 2) { const t = (p[j] - mx) * vx + (p[j + 1] - my) * vy; if (t > hi - 0.35 * (hi - lo)) a++; if (t < lo + 0.35 * (hi - lo)) b++; }
      if (b > a) { vx = -vx; vy = -vy; }
    }
    let lo = Infinity, hi = -Infinity;
    for (let j = 0; j < p.length; j += 2) { const t = p[j] * vx + p[j + 1] * vy; lo = Math.min(lo, t); hi = Math.max(hi, t); }
    const L = hi - lo, head = [0, 0, 0], waist = [0, 0, 0];
    for (let j = 0; j < p.length; j += 2) {
      const t = p[j] * vx + p[j + 1] * vy;
      if (t > hi - 0.3 * L) { head[0] += p[j]; head[1] += p[j + 1]; head[2]++; }
      if (t < hi - 0.55 * L && t > hi - 0.65 * L) { waist[0] += p[j]; waist[1] += p[j + 1]; waist[2]++; }
    }
    const at = (s) => (s[2] ? [s[0] / s[2], s[1] / s[2]] : null);
    const h = at(head);
    return { head: h, waist: at(waist) || h, ang: Math.atan2(vx, -vy) };
  }
  function gearMarks(img, frames) {
    const key = `${img.src}#${frames}`;
    if (key in GEAR.marks) return GEAR.marks[key];
    if (typeof document === "undefined" || !img.complete || !img.naturalWidth) return null;
    let out = [];
    try {
      const W = img.naturalWidth, H = img.naturalHeight, cw = Math.round(W / frames);
      const c = document.createElement("canvas");
      c.width = W; c.height = H;
      const g = c.getContext("2d", { willReadFrequently: true });
      g.drawImage(img, 0, 0);
      const px = g.getImageData(0, 0, W, H).data;
      for (let k = 0; k < frames; k++) out.push(gearFrame(px, W, H, k * cw, cw));
    } catch (e) { out = []; } // 讀不到像素（不同來源的圖）就不疊
    GEAR.marks[key] = out;
    return out;
  }
  // 在「一格」的座標裡（呼叫的人已經把原點移到那一格的左上角、照那一格的大小）疊上戴著的飾品
  function gearDraw(cx, img, frames, i, gear) {
    if (!gear || !gear.length || !img) return;
    const marks = gearMarks(img, frames), m = marks && marks[i];
    if (!m || !m.head) return;
    for (const id of gear) {
      const im = gearImg(id);
      if (!im || !im.complete || !im.naturalWidth) continue;
      const at = id.startsWith("waist_") ? m.waist : m.head;
      cx.save();
      cx.translate(at[0], at[1]);
      cx.rotate(m.ang);
      cx.drawImage(im, -im.naturalWidth / 2, -im.naturalHeight / 2);
      cx.restore();
    }
  }

  // 自建的圖換了（refit、重畫、退回重來）網址就換：舊快取不會擋住新圖（main.looks_ver）
  const looksVer = () => (window.LOOKS_VER ? `?v=${window.LOOKS_VER}` : "");
  // 這一套形象自己的手位表（hands.json；tianxia/features/looks/cutting.py 的 hand_row 算的）：
  // RING_HAND 是照斗笠小子量的，換一套形象手就不在同一個地方，兵器會懸在空中（Joy 2026-11-02）。
  // 抓得到就用它的位置，角度與層次照舊讀 RING_HAND；沒有（舊的一套、還沒抓到）就整個照 RING_HAND。
  function ringHands(look) {
    if (!look || !/^[a-z0-9_]+$/.test(look)) return null;
    if (!(look in RA.hands)) {
      RA.hands[look] = null;  // 先佔位：只抓一次
      const url = /^u\d+$/.test(look) ? `/api/looks/img/${look}/hands${looksVer()}` : `${RING_LOOKS}${look}/hands.json`;
      if (typeof fetch === "function") {
        fetch(url).then((r) => (r.ok ? r.json() : null)).then((t) => { if (t) RA.hands[look] = t; }).catch(() => {});
      }
    }
    return RA.hands[look];
  }
  function ringHand(look, sheet, i) {
    const base = (RING_HAND[sheet] || [])[i];
    const own = (ringHands(look) || {})[sheet];
    const pt = own && own[i];
    return pt && base ? [pt[0], pt[1], base[2], base[3]] : base;
  }
  // 這一套形象的這一張（第一次用到才抓；還沒抓好或抓不到就先畫斗笠小子）
  function ringBody(look, sheet) {
    if (!look || !/^[a-z0-9_]+$/.test(look)) return RA.imgs[sheet];
    const key = `${look}/${sheet}`;
    if (!RA.imgs[key]) RA.add(key, /^u\d+$/.test(look) ? `/api/looks/img/${look}/${sheet}${looksVer()}` : `${RING_LOOKS}${look}/${sheet}.webp`); // 自建的由伺服器送
    return ringReady(RA.imgs[key]) ? RA.imgs[key] : RA.imgs[sheet];
  }
  // 招式動畫（m<數字>，由伺服器送）：六格一張的光效，出招那幾格疊在出手的人身上（沒抓好就不疊）
  function ringFxImg(fx) {
    if (!fx || !/^m\d+$/.test(fx)) return null;
    const key = `fx/${fx}`;
    if (!RA.imgs[key]) RA.add(key, `/api/looks/img/${fx}/fx${looksVer()}`);
    return ringReady(RA.imgs[key]) ? RA.imgs[key] : null;
  }
  function ringFx(cx, fx, k, x, flip, lunge) {
    const img = ringFxImg(fx);
    if (!img) return;
    const i = Math.max(0, Math.min(5, Math.floor(k * 6)));
    cx.save();
    cx.translate(x + (flip ? -lunge : lunge), RING_GY);
    if (flip) cx.scale(-1, 1);
    cx.scale(RING_SCALE, RING_SCALE);
    cx.translate(-RING_AX, -RING_BY);
    // 光效畫得比人大一圈（以出手那一帶 FX_AT 為中心放大 FX_BIG 倍），蓋得到對手身上
    cx.translate(FX_AT[0], FX_AT[1]);
    cx.scale(FX_BIG, FX_BIG);
    cx.translate(-FX_AT[0], -FX_AT[1]);
    cx.drawImage(img, i * RING_CELL, 0, RING_CELL, RING_CELL, 0, 0, RING_CELL, RING_CELL);
    cx.restore();
  }
  const FX_AT = [130, 128], FX_BIG = 1.5;
  // 打中的那一下（出手那一張的 k 在 0.45～0.75）：帶招式光效的那一邊打中時畫面一震、閃一下白光（Joy 2026-11-01「更華麗的絕招」）
  const ringImpact = (k) => (k >= 0.45 && k <= 0.75 ? Math.sin(((k - 0.45) / 0.3) * Math.PI) : 0);
  const ringArms = (kind) => RING_ARMS[kind] || [null, "fist"];
  const ringAtk = (kind) => `hero_atk_${ringArms(kind)[1]}`;
  const ringStill = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // 一個人的一格：身體，加上手上那一件（劍在身前就再把拳頭那一小圈蓋回去，看起來是握著）
  function ringFigure(cx, sheet, i, x, flip, kind, lunge, skin) {
    const sk = skinParts(skin), look = sk.look; // 戴了飾品的皮：形象~飾品
    const img = ringBody(look, sheet);
    if (!ringReady(img)) return;
    const n = RING_SHEETS[sheet];
    i = Math.max(0, Math.min(n - 1, i));
    const hand = ringHand(look, sheet, i);
    const wname = ringArms(kind)[0], wimg = wname ? RA.imgs[`weapon_${wname}`] : null, spec = wname ? RING_WEAPON[wname] : null;
    cx.save();
    cx.translate(x + (flip ? -lunge : lunge), RING_GY);
    if (flip) cx.scale(-1, 1);
    cx.scale(RING_SCALE, RING_SCALE);
    cx.translate(-RING_AX, -RING_BY);
    const body = () => { cx.drawImage(img, i * RING_CELL, 0, RING_CELL, RING_CELL, 0, 0, RING_CELL, RING_CELL); gearDraw(cx, img, n, i, sk.gear); };
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

  // 一幕：兩個人各自的一串動作 [{sheet, at（第幾毫秒開始）, dur, keep（演完停在最後一格）, lunge（往前衝幾點，負的是往後退）}]；
  // 同一刻有兩個在演，後開始的那一個算（受擊蓋掉自己還沒演完的招）。之前、之後是站著（keep 的除外）
  const ringIdle = () => ({ sheet: "hero_bare_idle", loop: true });
  const ringAct = (sheet, at, dur, keep = false, lunge = 0, fx = false) => ({ sheet, at, dur, keep, lunge, fx });
  const RING_HIT = (at) => ringAct("hero_bare_hit", at, 380, false, -18);
  function ringStrike(who, hurt, burst = false) { // 不知道出了哪一招（舊的一場、放手一搏）：who 出手、另一邊受擊（hurt）或閃開
    const other = who === "me" ? "foe" : "me";
    const beat = { dur: 900 };
    beat[who] = [ringAct(ringAtk(RA.looks[who]), 0, 560, false, 44, burst)];
    beat[other] = [hurt ? RING_HIT(300) : ringAct("hero_bare_dodge", 300, 440)];
    return beat;
  }
  // 照出的招演（Joy 2026-10-31「強攻固守奇襲應該對應不同的動作」）：強攻大步衝上去整套劈下；固守原地架住（打中他的是架開之後回的那一下）；
  // 奇襲先側身閃開、再貼近補一下快的。誰挨打照誰剋誰（ringPicked），出手那一下打到的時候挨打的那一邊受擊
  // burst：這一回合綁了招式的那一門的戰法發動了（伺服器的 bursts），出手那一下疊光效；固守也架開之後回一下
  function ringPlan(who, pick, deals, burst = false) {
    const atk = ringAtk(RA.looks[who]);
    if (pick === "強攻") return { acts: [ringAct(atk, 0, 640, false, 64, burst)], hit: 330 };
    if (pick === "奇襲") return { acts: [ringAct("hero_bare_dodge", 0, 360, false, -14), ringAct(atk, 360, 440, false, 52, burst)], hit: 590 };
    const back = deals || burst;
    const guard = ringAct("hero_bare_block", 0, back ? 520 : 760, false, -4); // 固守
    return back ? { acts: [guard, ringAct(atk, 520, 420, false, 34, burst)], hit: 720 } : { acts: [guard], hit: -1 };
  }
  // 誰剋誰（同伺服器的 duel 規則：固守剋強攻、強攻剋奇襲、奇襲剋固守）
  const RING_BEATS = { "固守": "強攻", "強攻": "奇襲", "奇襲": "固守" };
  // 絕招發動的那一邊打中的那一下對手也受擊（絕招不落空）
  function ringPicked(a, b, pick, burst = [0, 0]) { // 只有被剋的那一邊受擊；出一樣的兩邊都受擊（Joy 2026-11-01）——照招，不看這一回合誰掉了血
    const same = pick[0] === pick[1];
    const fx = { me: !!burst[0], foe: !!burst[1] };
    const hurt = { me: same || RING_BEATS[pick[1]] === pick[0] || fx.foe, foe: same || RING_BEATS[pick[0]] === pick[1] || fx.me };
    const plan = { me: ringPlan("me", pick[0], hurt.foe, fx.me), foe: ringPlan("foe", pick[1], hurt.me, fx.foe) };
    const beat = { dur: 1250 };
    for (const [side, other] of [["me", "foe"], ["foe", "me"]]) {
      const hit = hurt[side] ? plan[other].hit : -1;
      const acts = plan[side].acts.filter((x) => hit < 0 || x.at < hit); // 挨打之後還沒出的那一下就不出了（奇襲閃到一半被劈中）
      if (hit >= 0) acts.push(RING_HIT(hit));
      beat[side] = acts;
    }
    return [beat];
  }
  // 這一回合跟上一回合比：知道兩邊出了哪一招就照招演，不然照誰掉了血
  // 一句話自創的絕招（arena_scene.js）：發動的那一邊有導演稿就整段照稿演，取代這一回合
  function ringScenes(burst) {
    if (typeof sceneFor !== "function") return [];
    const out = [];
    ["me", "foe"].forEach((who, k) => {
      const mid = RA.looks[`${who}_fx`], sc = burst && burst[k] ? sceneFor(mid) : null;
      if (sc) out.push({ dur: SCENE_LEN, scene: sc, who, mid });
    });
    return out;
  }
  function ringExchange(a, b, pick, burst) {
    const scenes = ringScenes(burst);
    if (scenes.length) return scenes;
    const fx = [!!(burst && burst[0]), !!(burst && burst[1])];
    if (pick && RING_PICKS.has(pick[0]) && RING_PICKS.has(pick[1])) return ringPicked(a, b, pick, fx);
    const dMe = a.me - b.me, dFoe = a.foe - b.foe, tol = 0.5;
    if (dMe > tol && dFoe > tol) return dMe > dFoe ? [ringStrike("me", true, fx[0]), ringStrike("foe", true, fx[1])] : [ringStrike("foe", true, fx[1]), ringStrike("me", true, fx[0])];
    if (dFoe > tol || fx[0]) return [ringStrike("me", true, fx[0])];
    if (dMe > tol || fx[1]) return [ringStrike("foe", true, fx[1])];
    if (b.edge > a.edge) return [ringStrike("me", false)];
    if (b.edge < a.edge) return [ringStrike("foe", false)];
    return [];
  }
  const RING_PICKS = new Set(["強攻", "固守", "奇襲"]);
  // 收場：照結果演最後一幕，倒地、跪地的那一邊停在最後一格；贏的那一邊照最後一回合出的招出手
  function ringFinale(tier, low, pick, burst) {
    if (tier === "僵持") return [...ringScenes(burst), ringStrike("me", false), ringStrike("foe", false)];
    const won = tier === "大勝" || tier === "險勝", who = won ? "me" : "foe", loser = won ? "foe" : "me";
    const down = won ? tier === "大勝" : low;
    const mine = pick && RING_PICKS.has(pick[won ? 0 : 1]) ? pick[won ? 0 : 1] : "強攻";
    const scenes = ringScenes(burst);
    const plan = ringPlan(who, mine, true, !scenes.length && !!(burst && burst[won ? 0 : 1]));
    const beat = { dur: Math.max(1500, plan.hit + 1100) };
    beat[who] = plan.acts;
    beat[loser] = [ringAct(down ? "hero_bare_fall" : "hero_bare_kneel", plan.hit, down ? 900 : 640, true)];
    return [...scenes, beat];
  }

  // 每次畫好畫面（render、renderShop）之後叫：看是不是有新的一回合或剛收場，排要演的幕
  function ringSync() {
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "arena" || typeof requestAnimationFrame !== "function" || !document.getElementById("ring-stage")) { ringStop(); return; }
    ringLoad();
    const f = shop.fight, r = shop.result && shop.result.id !== S.arenaSeen ? shop.result : null;
    if (f) {
      RA.looks = f.looks || { me: "", foe: "", me_look: "", foe_look: "" };
      ringWarm(RA.looks);
      if (typeof sceneFor === "function") { sceneFor(RA.looks.me_fx); sceneFor(RA.looks.foe_fx); } // 先抓好導演稿，發動那一回合才演得出來
      const now = { id: f.id, round: f.round, me: f.me.hp, foe: f.foe_hp.hp, cap: f.me.cap, edge: f.edge };
      const p = RA.prev;
      if (p && p.id === now.id && now.round > p.round) RA.q.push(...ringExchange(p, now, (f.picks || [])[now.round - 2], (f.bursts || [])[now.round - 2]));
      else if (!p || p.id !== now.id) { RA.q = []; RA.cur = null; RA.hold = null; }
      RA.prev = now;
    } else if (r && RA.finaleFor !== r.id) {
      RA.looks = r.looks || RA.looks;
      ringWarm(RA.looks);
      RA.finaleFor = r.id;
      const p = RA.prev && RA.prev.id === r.id ? RA.prev : null;
      const last = (r.picks || []).length - 1;
      RA.q = ringFinale(r.tier, !p || p.me <= p.cap * 0.25, (r.picks || [])[last], (r.bursts || [])[last]);
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
      for (const a of [].concat(beat[side] || [])) {
        if (a.keep) { RA.hold = RA.hold || {}; RA.hold[side] = { sheet: a.sheet, i: RING_SHEETS[a.sheet] - 1 }; }
      }
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

  // 場地：城裡的遠景與地面，加上一塊木台（絕招那一段也畫這一塊，arena_scene.js）
  function ringGround(cx) {
    const far = RA.imgs.bg0, ground = RA.imgs.bg1;
    if (ringReady(far)) cx.drawImage(far, 0, 0, far.naturalWidth, far.naturalHeight, -60, -40, (far.naturalWidth * (RING_H + 40)) / far.naturalHeight, RING_H + 40);
    if (ringReady(ground)) { const gh = 110, gw = (ground.naturalWidth * gh) / ground.naturalHeight; for (let x = 0; x < RING_W; x += gw) cx.drawImage(ground, x, RING_H - gh, gw, gh); }
    cx.fillStyle = "rgba(96, 62, 34, 0.92)";
    cx.fillRect(110, RING_GY - 4, RING_W - 220, 14);
    cx.fillStyle = "rgba(60, 36, 18, 0.9)";
    cx.fillRect(110, RING_GY + 10, RING_W - 220, 18);
  }

  function ringPaint(cx, now, el) {
    const beat = RA.cur ? RA.cur.beat : null;
    if (beat && beat.scene && typeof sceneOnRing === "function") { sceneOnRing(cx, beat.scene, el, beat.who, beat.mid); return; }
    cx.clearRect(0, 0, RING_W, RING_H);
    const active = (side) => { // 這一刻在演的那一個（同一刻兩個在演，後開始的算）；演完了、keep 的停在最後一格
      let on = null, kept = null;
      for (const a of [].concat((beat && beat[side]) || [])) {
        if (el >= a.at && el < a.at + a.dur && (!on || a.at >= on.at)) on = a;
        else if (a.keep && el >= a.at + a.dur) kept = a;
      }
      return on ? { a: on, k: (el - on.at) / on.dur } : kept ? { a: kept, k: 1 } : null;
    };
    const now2 = { me: active("me"), foe: active("foe") };
    let jolt = 0; // 帶光效打中的那一下有多重
    for (const side of ["me", "foe"]) {
      const g = now2[side];
      if (g && g.k < 1 && g.a.fx && ringFxImg(RA.looks[`${side}_fx`])) jolt = Math.max(jolt, ringImpact(g.k));
    }
    cx.save();
    if (jolt > 0) cx.translate(Math.sin(now * 0.09) * 7 * jolt, Math.cos(now * 0.13) * 4 * jolt);
    ringGround(cx);
    const sides = [["me", RING_X[0], false], ["foe", RING_X[1], true]];
    // 出手的那一個畫在後面（蓋在上面）
    if (now2.me && now2.me.a.sheet.startsWith("hero_atk_")) sides.reverse();
    for (const [side, x, flip] of sides) {
      let sheet = "hero_bare_idle", i = Math.floor(now / 230) % 4, lunge = 0, fxAt = -1;
      const got = now2[side];
      if (got) {
        const { a, k } = got;
        sheet = a.sheet;
        i = Math.min(RING_SHEETS[sheet] - 1, Math.floor(k * RING_SHEETS[sheet]));
        if (k < 1) lunge = Math.sin(k * Math.PI) * (a.lunge || 0);
        if (a.fx && k < 1) fxAt = k; // 光效只在絕招發動的那一下疊（Joy 2026-11-01「我以為是招式發動的時候才會有」）
      } else if (RA.hold && RA.hold[side]) {
        sheet = RA.hold[side].sheet;
        i = RA.hold[side].i;
      }
      ringFigure(cx, sheet, i, x, flip, RA.looks[side], lunge, RA.looks[`${side}_look`]);
      if (fxAt >= 0) ringFx(cx, RA.looks[`${side}_fx`], fxAt, x, flip, lunge);
    }
    cx.restore();
    if (jolt > 0) { // 閃一下白光
      cx.fillStyle = `rgba(255, 246, 225, ${(0.38 * jolt).toFixed(3)})`;
      cx.fillRect(0, 0, RING_W, RING_H);
    }
  }

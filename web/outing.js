/* 天下大勢的網頁前端：走一趟（探索一次走一、三、五段；企劃者 2026-10-29～30，引擎 tianxia/outing.py）。說明見 app.js 檔頭。
 *
 * 伺服器一次算到「下一件要選的事」為止，沿路每一段放在 main.outing.trip.beats；這裡只把已經算好的結果演出來：
 * 斗笠小童在野地四層背景上跑（越近的層捲得越快），到了那一段照類別演動作（撿、打、停步），演完寫一行。
 * 要選的事（事件、有所感、頭目）：畫面停住，事情與選項直接畫在這張卡底下，就在這裡選（Joy 10/30：不要「去看看」那一步）；
 * 選完了（trip.can_go）寫一行結果、自動接著走。要寫字或畫圖的選項（隨口應對、有所感畫形、取名……）那個框在江湖頁：
 * 按了這一層先收起、捲到那個框，送出後再打開。
 * 演完一整趟給結算卡。動畫可以 2×、可以略過；系統設定「減少動態」的人直接快轉。圖是 Joy 10/30 生的（web/img/outing/）。
 */
"use strict";

  const OUTING_IMG = "/static/img/outing/";
  // 每一張動作圖幾格（每格 220×220，腳底在 (100, 212)；去背切格的腳本在專案檔案 design/走一趟/sprites.py）
  const OUTING_SHEETS = {
    hero_idle: 4, hero_run: 8, hero_pickup: 6, hero_lift: 3, hero_slash: 6, hero_hit: 3, hero_kneel: 4, hero_meditate: 4, hero_push: 4,
    foe_idle_attack: 8, foe_hit_fall: 6,
  };
  // 對手的樣子（伺服器的 beat.foe：huang 黃巾、guan 官兵、retainer 豪強家丁、bandit 綠林盜匪、beast 猛獸）。
  // 有圖的那幾種寫進這裡（檔名 foe_<樣子>_idle_attack、foe_<樣子>_hit_fall，格數同黃巾；Joy 10/30 生的）；沒圖的、黃巾都用 foe_idle_attack 那一套。
  // 黃巾那一套畫的是臉朝右（畫的時候翻過來），這四套畫的是臉朝左（不用翻）；猛獸一次只出一隻
  const OUTING_FOE_ART = ["guan", "bandit", "retainer", "beast"];
  for (const look of OUTING_FOE_ART) { OUTING_SHEETS[`foe_${look}_idle_attack`] = 8; OUTING_SHEETS[`foe_${look}_hit_fall`] = 6; }
  const outingFoeSheet = (look, base) => (OUTING_FOE_ART.includes(look) ? `foe_${look}_${base}` : `foe_${base}`);
  // 背景四層（由遠到近）與各自捲的速度：遠景最慢、前景比角色快、蓋在角色前面。檔名 bg_<地點種類>_<層>，
  // 地點種類是伺服器的 trip.scene（探索那六張表：town 城、temple 寺、ford 渡、wild 野、hill 山、camp 營；Joy 10/30 六套都畫了），認不得的用野
  const OUTING_SCENES = ["town", "temple", "ford", "wild", "hill", "camp"];
  const OUTING_LAYERS = [["far", 0.1, -30, 400], ["mid", 0.4, 50, 260], ["ground", 1, 210, 150]];
  const OUTING_FRONT = ["front", 1.6, 240, 150];
  const outingBg = (layer) => {
    const t = outingTrip(), scene = t && OUTING_SCENES.includes(t.scene) ? t.scene : "wild";
    return outingImg(`bg_${scene}_${layer}`);
  };
  const OUTING_W = 720, OUTING_H = 360, OUTING_GY = 300, OUTING_HX = 190;
  const OUTING_CELL = 220, OUTING_AX = 100, OUTING_BY = 212;
  const OUTING_KIND = { material: "料", encounter: "戰", event: "事", insight: "悟", trace: "見" };
  const OUTING_SPEED_KEY = "outing-speed";
  // 畫面上的字（待 joy 潤）
  const OUTING_WAIT = "路上碰到要選的事。";
  const OUTING_AFTER = "果";
  const OUTING_CLOSE = "收起";
  const OUTING_AGAIN = "再走一趟";
  const OUTING_TIRED = "體力不夠再走 {n} 段，挑短一點的。";
  const OUTING_SKIP = "略過";
  const OUTING_SET_OFF = "出發";
  const OUTING_SAY_HEAD = "在這裡留一句";
  const OUTING_SAY_OWN = "自己寫";
  const OUTING_SAY_INK = "用一張題壁墨（手上 {n} 張）";
  const OUTING_SAY_BUY = "去萬寶閣買題壁墨";
  const OUTING_SAID = "你留下：「{text}」";
  const OUTING_HERE = "此地還有";
  const OUTING_STELE = "路碑";
  const OUTING_STELE_N = "{n} 人留過";
  const OUTING_STELE_ALL = "此處留過的話";
  const OUTING_INK_SEAL = "墨";
  const OUTING_INK_SEAL_LABEL = "題壁墨";

  // 這一層自己的狀態（不放進 S：每一格動畫都會改，不該讓整頁重畫）
  const OW = { imgs: null, open: false, away: false, shown: 0, played: 0, tasks: [], cur: null, raf: 0, last: 0, scroll: 0, props: [], parts: [],
    hero: { pose: "idle", k: 0, t: 0, runP: 0, kx: 0, red: 0, bubble: "", glow: 0, gold: false }, turbo: false, speed: 1, going: false };

  // 重新整理之後接得回來（全面自檢 U-13）：這兩樣只有這一頁知道，記在瀏覽器裡（存不了就跟以前一樣，重新整理會走丟）
  // - 收起過的那一趟（trip.n）：沒收起就重新整理的，結算卡（含「在這裡留一句」）再打開一次；收起了、再走一趟了就不再跳
  // - 為了畫形、寫字收起來的那一步（第幾趟、走到第幾行、哪一個選項）：重新整理回到同一步，直接再叫出畫布／輸入框，不再問一次
  const OUTING_CLOSED_KEY = "outing-closed", OUTING_AWAY_KEY = "outing-away";
  function outingStore(key, v) { try { if (v == null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(v)); } catch (e) { /* 存不了就算了 */ } }
  function outingRecall(key) { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { return null; } }

  function outingSpeed() { try { return Number(localStorage.getItem(OUTING_SPEED_KEY)) === 2 ? 2 : 1; } catch (e) { return 1; } }
  function outingSaveSpeed(v) { try { localStorage.setItem(OUTING_SPEED_KEY, String(v)); } catch (e) { /* 存不了就這一頁有效 */ } }

  function outingImg(name) {
    OW.imgs = OW.imgs || {};
    if (!OW.imgs[name]) {
      const img = new Image();
      img.src = `${OUTING_IMG}${name}.webp`;
      OW.imgs[name] = img;
    }
    return OW.imgs[name];
  }
  // 動作圖一開就全載；背景只載這一處那一套（outingBg 第一次畫到時才載）
  function outingImages() {
    for (const name of Object.keys(OUTING_SHEETS)) outingImg(name);
    for (const [layer] of [...OUTING_LAYERS, OUTING_FRONT]) outingBg(layer);
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

  // 每次拿到新的畫面（setMain 之後）：停在要選的事上時刷新卡上的選項；選完了（can_go）寫一行結果、自己接著走
  function outingSync() {
    const trip = S.main && S.main.outing && S.main.outing.trip;
    if (!trip) return;
    // 重新整理頁面（或換了分頁）時那一趟還停在要選的事上：直接打開這一層、選項畫在卡上（沿路那幾行不重演）
    if (!trip.end && !OW.open && !OW.away && OW.shown === 0) {
      OW.shown = trip.beats.length; OW.played = trip.done;
      const away = outingRecall(OUTING_AWAY_KEY);
      if (outingInputOpen()) OW.away = true;
      else if (away && away.n === trip.n && away.at === trip.beats.length && outingNeedsPage(away.id)) {
        OW.away = true; // 畫形、寫字寫到一半重新整理：同一步，直接叫回畫布／輸入框
        Promise.resolve(choose(null, away.id)).then(outingRevealInput);
      } else outingOpen();
      return;
    }
    // 走完了、結算卡還沒收起就重新整理：再打開結算卡（留一句的入口在上面），沿路那幾行直接寫回去不重演
    if (trip.end && !OW.open && !OW.away && OW.shown === 0) {
      if (outingRecall(OUTING_CLOSED_KEY) !== trip.n) { OW.shown = trip.beats.length; OW.played = trip.done; outingOpen(); }
      return;
    }
    if (OW.going || S.busy) return;
    // 為了寫字、畫圖收起來的：框還開著就等；送出了又停在下一件要選的事上（有所感之後取名……）就打開、畫在卡上
    if (OW.away && !trip.end && !trip.can_go) {
      if (!outingInputOpen()) { OW.away = false; outingStore(OUTING_AWAY_KEY, null); outingOpen(); }
      return;
    }
    if (!OW.away && !OW.open) return;
    if (OW.open && (OW.cur || OW.tasks.length)) return; // 還在演
    if (OW.waitKey && (trip.end || trip.can_go)) outingAfter();
    if (trip.end) { OW.away = false; outingOpen(); return; }
    if (!trip.can_go) { outingFoot(); return; }
    OW.going = true;
    OW.away = false;
    outingGo(0).finally(() => { OW.going = false; });
  }

  // 要在江湖頁寫字或畫圖的選項（那個框只畫在江湖頁上）。隨口應對不在裡面：輸入框直接畫在這張卡上（outingChoiceHtml）
  function outingNeedsPage(id) {
    return id === SENSE_DRAW || SAY_OPTIONS.includes(id) || id.startsWith(PERSUADE_PREFIX) || id === OWN_NAME_ID || id === GATHER_SAY_ID;
  }
  function outingInputOpen() { return !!(S.sensing || S.answering || S.saying || S.persuading || S.godNaming || S.gatherSaying); }
  const OUTING_INPUTS = "#sense-pad, #answer-form, #say-form, #persuade-form, #own-name-form, #gather-say-form";

  // 選完了：「剛剛」那一則（事件的結果）的頭一句寫進沿路紀錄，接著走
  function outingAfter() {
    OW.waitKey = null;
    // 「剛剛」那一則的每一行（.tx-line），時刻與小標不要；跟沿路已經寫過的那一行一樣的不再寫
    const tmp = document.createElement("div");
    tmp.innerHTML = S.main.now || "";
    const seen = new Set([...document.querySelectorAll("#outing-pop .outing-line")].map((x) => x.textContent));
    const lines = [...tmp.querySelectorAll(".tx-line")].map((x) => x.textContent.trim()).filter((t) => t && ![...seen].some((x) => x.includes(t)));
    const now = (lines.length ? lines.join(" ") : tmp.textContent).replace(/\s+/g, " ").trim();
    const text = now.length > 80 ? `${now.slice(0, 80)}……` : now;
    const box = document.getElementById("outing-pop");
    if (!text || !box) return;
    const row = document.createElement("p");
    row.className = "outing-line after";
    row.innerHTML = `<span class="k">${OUTING_AFTER}</span><span>${esc(text)}</span>`;
    const log = box.querySelector(".outing-log");
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  // 停下來要選的事：江湖頁場景卡上的那段話（伺服器的 m.scene）＋選項，畫在走一趟這張卡上
  function outingChoiceHtml(m, answering) {
    const label = (o) => (typeof optLabelHtml === "function" ? optLabelHtml(o) : `<span>${esc(o.label)}</span>`);
    const opts = (m.options || []).filter((o) => o.id !== "act:on_road");
    return `<div class="outing-choice">${m.scene ? `<div class="outing-ev">${m.scene}</div>` : `<p>${OUTING_WAIT}</p>`}
      <div class="options">${opts.map((o, i) => answering && o.id === FREE_TEXT_OPTION && o.enabled ? `
        <form class="free answer" id="outing-answer"><input class="input" name="text" maxlength="20" placeholder="${esc(o.label)}（20字內）" aria-label="${esc(o.label)}"><button class="btn primary small" type="submit">說出口</button></form>` : `<button class="btn" data-act="outing-choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span class="k">${i + 1}</span>${label(o)}</button>`).join("")}</div></div>`;
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
        <p class="outing-head"><b class="outing-place"></b><span class="outing-step"></span></p>
        <div class="outing-scene"><canvas class="outing-cv" width="${OUTING_W}" height="${OUTING_H}" aria-label="走一趟"></canvas>
          <button class="outing-stele" data-act="outing-stele" hidden></button><div class="outing-stele-all" hidden></div></div>
        <div class="outing-foot"></div>
        <div class="outing-log" aria-live="polite"></div></div>`;
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

  // 要寫字、畫圖的選項：這一層先藏起來（沿路那幾行留著），送出後再打開；動畫停掉省電
  function outingHide() {
    OW.open = false;
    const box = document.getElementById("outing-pop");
    if (box) box.hidden = true;
    if (OW.raf) cancelAnimationFrame(OW.raf);
    OW.raf = 0;
  }

  // 要寫字、畫圖的選項：這一層收起之後把那個框捲到眼前
  function outingRevealInput() {
    const el = document.querySelector(OUTING_INPUTS);
    if (!el) return;
    const calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ block: "center", behavior: calm ? "auto" : "smooth" });
  }

  function outingShut() {
    OW.open = false;
    OW.steleOpen = false;
    OW.tasks = [];
    OW.cur = null;
    OW.turbo = false;
    const box = document.getElementById("outing-pop");
    if (box) box.remove();
    if (OW.raf) cancelAnimationFrame(OW.raf);
    OW.raf = 0;
  }

  // 畫面右上那塊路碑（Joy 10/30）：碑上一句（最後一則題壁墨寫的，沒有就是最多人留的預設句），點開看這一處全部的留言
  // 題壁墨寫的那一句要一眼看得出來（Joy 10/30）：碑換成朱漆描金、角上一枚「墨」字印；點開的清單裡題壁墨的排前面、整條描金
  function outingSteleHtml(st) {
    const by = st.author ? `——${esc(st.author)}` : st.n > 1 ? esc(OUTING_STELE_N.replace("{n}", st.n)) : "";
    const seal = st.ink ? `<em class="ink-seal" aria-label="${OUTING_INK_SEAL_LABEL}">${OUTING_INK_SEAL}</em>` : "";
    return `${seal}<small>${OUTING_STELE}</small><b>「${esc(st.text)}」</b>${by ? `<i>${by}</i>` : ""}`;
  }
  function outingSteleAllHtml(st) {
    const rows = [...st.all.filter((x) => x.ink), ...st.all.filter((x) => !x.ink)];
    return `<p class="outing-stele-head"><b>${OUTING_STELE_ALL}</b><button data-act="outing-stele" aria-label="收起">×</button></p>${rows.map((x) => x.ink
      ? `<p class="ink"><em class="ink-seal" aria-label="${OUTING_INK_SEAL_LABEL}">${OUTING_INK_SEAL}</em><span>「${esc(x.text)}」<small>——${esc(x.author)}</small></span></p>`
      : `<p>「${esc(x.text)}」<small>——${esc(x.author)}</small></p>`).join("")}`;
  }
  function outingStele() {
    const box = document.getElementById("outing-pop");
    const trip = outingTrip();
    if (!box || !trip) return;
    // 路牌走到最後（結算卡出來，卡片的 done）才看得到，一路上不掛著（Joy 10/30）；伺服器一次算完整趟，trip.end 在動畫還在演時就有了
    const st = box.querySelector(".outing-card").classList.contains("done") ? trip.stele : null;
    const sign = box.querySelector(".outing-stele"), all = box.querySelector(".outing-stele-all");
    sign.classList.toggle("inked", !!(st && st.ink));
    sign.hidden = !st;
    all.hidden = !st || !OW.steleOpen;
    if (!st) { OW.steleOpen = false; return; }
    const html = outingSteleHtml(st);
    if (sign.innerHTML !== html) sign.innerHTML = html;
    sign.setAttribute("aria-expanded", String(!!OW.steleOpen));
    if (OW.steleOpen) all.innerHTML = outingSteleAllHtml(st);
  }

  // 底下那一排：走著是速度與略過；停在要選的事上是那件事與選項（outingChoiceHtml）；走完是結算卡
  function outingFoot() {
    const box = document.getElementById("outing-pop");
    const trip = outingTrip();
    if (!box || !trip) return;
    const at = Math.min(Math.max(OW.played, 1), trip.total);
    box.querySelector(".outing-step").innerHTML = `第 ${at}／${trip.total} 段${Array.from({ length: trip.total }, (_, j) => `<i class="d${j < OW.played ? " on" : ""}"></i>`).join("")}`;
    const foot = box.querySelector(".outing-foot");
    const walking = OW.cur || OW.tasks.length;
    const card = box.querySelector(".outing-card");
    card.classList.toggle("choosing", !walking && !trip.end);
    card.classList.toggle("done", !walking && !!trip.end); // 結算卡長（留一句展開、遊記長）：卡片底下那一塊自己捲
    outingStele();
    if (!walking && trip.end) foot.dataset.key = "";
    if (walking) {
      foot.dataset.key = "";
      foot.innerHTML = `<div class="outing-ctl"><button class="btn" data-act="outing-speed">速度 ${OW.speed}×</button>
        <button class="btn" data-act="outing-skip">${OUTING_SKIP}</button></div>`;
    } else if (!trip.end) {
      // 輪詢每幾秒重畫一次：選項沒變就不動（捲到一半、按到一半的不被打斷）
      const key = JSON.stringify([S.main.scene, (S.main.options || []).map((o) => [o.id, o.label, o.enabled])]);
      if (OW.waitKey !== key) OW.answering = false; // 換了一件事：輸入框收起
      OW.waitKey = key;
      const drawn = `${key}|${OW.answering ? 1 : 0}`;
      if (foot.dataset.key !== drawn) { foot.dataset.key = drawn; foot.innerHTML = outingChoiceHtml(S.main, OW.answering); foot.scrollTop = 0; }
    } else {
      foot.innerHTML = outingResultHtml(trip);
      outingDiary(trip);
    }
  }

  // 遊記：結算卡先放模板那一段，請模型寫（鎖外，伺服器 outing_tale）；寫到了淡入換掉。一趟只請一次
  async function outingDiary(trip) {
    const key = `${trip.place}|${trip.beats.length}|${trip.done}`;
    if (trip.diary_done || OW.diaryAsked === key) return;
    OW.diaryAsked = key;
    try {
      const r = await api("/api/do/outing_tale", {});
      if (r && r.main) {
        applyMain(r.main);
        const now = outingTrip();
        const p = document.querySelector("#outing-pop .outing-diary");
        if (now && p && now.diary && now.diary !== p.textContent) { p.textContent = now.diary; p.classList.add("fresh"); }
      }
    } catch (e) { /* 叫不動就留著模板那一段 */ }
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
      ${trip.diary ? `<p class="outing-diary">${esc(trip.diary)}</p>` : ""}
      ${trip.feat_note ? `<p class="outing-feat">${esc(trip.feat_note)}</p>` : ""}
      ${outingSayHtml(trip)}${outingPeopleHtml(trip)}
      <div class="outing-ctl"><button class="btn" data-act="outing-close">${OUTING_CLOSE}</button>
      <button class="btn primary" data-act="outing-again">${OUTING_AGAIN}</button></div></div>`;
  }

  // 結算卡的留言格（企劃者 2026-10-29～30）：預設句免費一按就留；自己寫的用一張題壁墨（沒有就給去萬寶閣的鈕）；一趟一句
  function outingSayHtml(trip) {
    if (trip.said) return `<p class="outing-said">${esc(OUTING_SAID.replace("{text}", trip.said))}</p>`;
    if (!trip.can_say) return "";
    const presets = (trip.presets || []).map((t, i) => `<button class="oc say" data-act="outing-say" data-i="${i}">${esc(t)}</button>`).join("");
    const ink = trip.ink | 0;
    const own = ink > 0
      ? `<div class="outing-own"><input id="outing-own" maxlength="${trip.say_max | 0}" placeholder="${esc(OUTING_SAY_OWN)}（${trip.say_max | 0} 字內）">
          <button class="btn small" data-act="outing-say-own">${esc(OUTING_SAY_INK.replace("{n}", ink))}</button></div>`
      : trip.ink_item ? `<button class="btn small ghost" data-act="outing-mall" data-id="${esc(trip.ink_item)}">${OUTING_SAY_BUY}</button>` : "";
    return `<details class="outing-say"><summary>${OUTING_SAY_HEAD}</summary><p class="outing-chips">${presets}</p>${own}</details>`;
  }

  // 結算卡的「此地還有」：點名字開玩家卡（打招呼、邀結伴照玩家卡那幾顆）
  function outingPeopleHtml(trip) {
    const people = trip.people || [];
    if (!people.length) return "";
    return `<p class="outing-here">${OUTING_HERE}${people.slice(0, 6).map((n) => `<button class="peer-name" data-act="outing-peer" data-name="${esc(n)}">${esc(n)}</button>`).join("")}</p>`;
  }

  async function outingSay(body) {
    await busy(async () => {
      const r = await api("/api/do/outing_say", body);
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
      outingFoot();
    });
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
    const trip = outingTrip();
    row.className = `outing-line${b.rare ? " rare" : ""}${lost ? " bad" : ""}${b.kind === "trace" ? " trace" : ""}`;
    const erase = b.ref && trip && trip.admin ? `<button class="outing-erase" data-act="outing-erase" data-id="${b.ref | 0}" aria-label="抹掉這一句">×</button>` : "";
    row.innerHTML = `<span class="k">${OUTING_KIND[b.kind] || "行"}</span><span>${esc(b.text)}${b.ledger ? outingLedgerHtml(b.ledger) : ""}</span>${erase}`;
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  // ── 動畫：一串任務（跑過去、做動作、寫一行），時間照速度乘；略過＝快轉到停下或走完 ──
  function outingQueue(trip) {
    while (OW.shown < trip.beats.length) {
      const i = OW.shown, b = trip.beats[i];
      const lost = trip.end === "lost" && i === trip.beats.length - 1;
      const seg = trip.beats.slice(0, i + 1).filter((x) => x.kind !== "trace").length; // 路上看到的那幾行不佔段數
      OW.tasks.push(outingCall(() => { OW.played = seg; OW.hero.bubble = ""; outingFoot(); }), ...outingBeatTasks(b, lost), { dur: 0, end: () => { outingLine(b, lost); outingFoot(); } });
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
      const look = b.foe || "";
      const foes = (look === "beast" ? [0] : [0, 1]).map((i) => ({ kind: "foe", look, x: OUTING_W + 40 + i * 80, flash: 0, fall: 0, fade: 0, dying: false, atk: 0 }));
      const two = foes[1] || foes[0]; // 只有一隻時，第二個出手的就是牠自己
      const hit = (f) => outingCall(() => { f.flash = 1; outingBurst(f.x, OUTING_GY - 100, 10, "#8a6a48", 140); });
      const atk = (f) => [{ dur: 0.4, update(t) { f.atk = Math.min(1, t / 0.4); f.lunge = -30 * Math.sin(f.atk * Math.PI); }, end() { f.atk = 0; f.lunge = 0; } },
        outingCall(() => { H.red = 1; H.kx = -26; outingBurst(OUTING_HX + 10, OUTING_GY - 100, 10, "#e0665a", 120); }), outingPose("hurt", 0.45)];
      const out = [outingCall(() => OW.props.push(...foes)), outingRun(foes[0], 150), outingPose("stance", 0.3)];
      if (b.won) {
        out.push(outingPose("slash", 0.5), hit(foes[0]), outingCall(() => { if (two !== foes[0]) foes[0].dying = true; }), { dur: 0.15 }, ...atk(two),
          outingPose("stance", 0.2), outingPose("slash", 0.5), hit(two), outingCall(() => { two.dying = true; }), { dur: 0.6 }, outingPose("idle", 0.2));
      } else if (lost) {
        out.push(outingPose("slash", 0.5), hit(foes[0]), ...atk(two), ...atk(foes[0]), outingPose("kneel", 0.8), { dur: 0.4, start() { H.pose = "kneel"; H.k = 1; } });
      } else { // 平手：互換一招，對手退走
        out.push(outingPose("slash", 0.5), hit(foes[0]), ...atk(two), { dur: 0.6, update(t, d) { foes.forEach((f) => { f.x += 260 * d; }); } });
      }
      out.push(outingCall(() => { OW.props = OW.props.filter((p) => !foes.includes(p)); }));
      return out;
    }
    if (b.kind === "trace") { // 路上看到的：有留言的石頭從右邊捲過來，或遠處山坡上一個小人揮手（不停步）
      const t = b.ref ? { kind: "stone", x: OUTING_W + 30 } : { kind: "far", x: OUTING_W - 120, par: 0.4, t0: performance.now() };
      return [outingCall(() => OW.props.push(t)), outingRun(b.ref ? t : null, b.ref ? 10 : 1.2), outingCall(() => { OW.props = OW.props.filter((p) => p !== t || p.kind === "far"); })];
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
    cx.translate(x, opt.y == null ? OUTING_GY : opt.y);
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
    for (const [layer, par, y, h] of OUTING_LAYERS) outingTile(cx, outingBg(layer), par, y, h);
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
      } else if (p.kind === "stone") { // 刻了字的石頭
        cx.fillStyle = "#8d8577";
        cx.beginPath();
        cx.ellipse(p.x, OUTING_GY - 22, 30, 26, 0, Math.PI, 0);
        cx.lineTo(p.x + 30, OUTING_GY);
        cx.lineTo(p.x - 30, OUTING_GY);
        cx.fill();
        cx.fillStyle = "#4a443c";
        for (let k = 0; k < 3; k++) cx.fillRect(p.x - 12 + k * 9, OUTING_GY - 36, 3, 22);
      } else if (p.kind === "far") { // 遠處山坡上的人：小小的、慢慢晃
        const a = Math.min(1, (now - p.t0) / 400);
        outingSprite(cx, "hero_idle", Math.floor(now / 220), p.x, { scale: 0.32, alpha: 0.85 * a, y: OUTING_GY - 120, flip: true });
      } else if (p.kind === "foe") {
        const x = p.x + (p.lunge || 0), opt = { flip: !OUTING_FOE_ART.includes(p.look), scale: 0.85 };
        const fall = outingFoeSheet(p.look, "hit_fall"), idle = outingFoeSheet(p.look, "idle_attack");
        if (p.dying) outingSprite(cx, fall, 1 + Math.min(4, Math.floor(p.fall * 5)), x, { ...opt, alpha: 1 - p.fade });
        else if (p.flash > 0) outingSprite(cx, fall, 0, x, { ...opt, tint: "#fff", tintA: p.flash * 0.8 });
        else if (p.atk > 0) outingSprite(cx, idle, 4 + Math.min(3, Math.floor(p.atk * 4)), x, opt);
        else outingSprite(cx, idle, Math.floor(now / 180 + p.x) % 4, x, opt);
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
    const [flayer, par, y, h] = OUTING_FRONT;
    cx.globalAlpha = 0.95;
    outingTile(cx, outingBg(flayer), par, y, h);
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
      case "outing-choose": {
        const id = el.dataset.id;
        if (id === FREE_TEXT_OPTION) {
          OW.answering = true;
          outingFoot();
          const input = document.querySelector("#outing-answer .input");
          if (input) input.focus();
          return true;
        }
        if (outingNeedsPage(id)) {
          const trip = outingTrip();
          if (trip) outingStore(OUTING_AWAY_KEY, { n: trip.n, at: trip.beats.length, id });
          OW.away = true; outingHide(); await choose(el, id); outingRevealInput(); return true;
        }
        await choose(el, id);
        return true;
      }
      case "outing-close": { const trip = outingTrip(); if (trip && trip.end) outingStore(OUTING_CLOSED_KEY, trip.n); outingShut(); OW.shown = 0; return true; }
      case "outing-again": { // 照這一趟的段數直接再走一趟（Joy 10/30）；體力不夠才回到段數選單
        const trip = outingTrip(), o = S.main.outing;
        const n = trip ? trip.total : 0, pick = o && o.picker.find((x) => x.n === n);
        if (trip) outingStore(OUTING_CLOSED_KEY, trip.n);
        outingShut();
        OW.shown = 0;
        if (pick && pick.ok) { await outingGo(n); return true; }
        if (n) toast(OUTING_TIRED.replace("{n}", n));
        S.wheelSel = "explore"; renderPage(); revealMoveCard();
        return true;
      }
      case "outing-say": await outingSay({ preset: Number(el.dataset.i) }); return true;
      case "outing-stele": OW.steleOpen = !OW.steleOpen; outingStele(); return true;
      case "outing-say-own": {
        const box = document.getElementById("outing-own");
        const text = box ? box.value.trim() : "";
        if (text) await outingSay({ text });
        return true;
      }
      case "outing-mall": outingShut(); OW.shown = 0; await openMall(); mallPick(el.dataset.id); return true;
      case "outing-peer": outingShut(); OW.shown = 0; await openPeer(el.dataset.name); return true;
      case "outing-erase":
        await busy(async () => { const r = await api("/api/do/outing_erase", { id: Number(el.dataset.id) }); applyMain(r.main); el.closest(".outing-line").remove(); });
        return true;
      default: return false;
    }
  }

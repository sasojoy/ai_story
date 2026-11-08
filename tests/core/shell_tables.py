"""殼不再長（test_shell_stays_thin.py）的名單：第 106 批量的現況，排序。只擋多出來的，搬走不用改這裡；多一筆要企劃者或 Joy 點頭、PR 寫原話。"""
from __future__ import annotations

# ── server.py 的 app.*（屬性, 第一個參數）；帳號的路由之後要動：改這裡 ──
SHELL_APP_CALLS = frozenset({
    ("exception_handler", "GameError"),
    ("get", "/"),
    ("get", "/api/board_card"),
    ("get", "/api/boards"),
    ("get", "/api/events"),
    ("get", "/api/main"),
    ("get", "/api/me"),
    ("get", "/api/menxia"),
    ("get", "/api/patch_notes"),
    ("get", "/api/prologue"),
    ("get", "/api/queue"),
    ("get", "/api/reports"),
    ("get", "/journal.css"),
    ("get", "/manifest.webmanifest"),
    ("include_router", "_router"),
    ("middleware", "http"),
    ("mount", "/static"),
    ("post", "/api/answer"),
    ("post", "/api/character"),
    ("post", "/api/choose"),
    ("post", "/api/do/{op}"),
    ("post", "/api/login"),
    ("post", "/api/logout"),
    ("post", "/api/menxia/{op}"),
    ("post", "/api/password"),
    ("post", "/api/register"),
    ("post", "/api/say"),
})

# Game 的方法（class 本體的 def，加 MAP_LAYERS：本體直接寫的名字一樣算）
GAME_METHODS = frozenset("""
MAP_LAYERS __init__ _act _action_costs _action_title _admin_refusal _admin_target _advance_player_local _apply _art_name
_battle_gear _battle_marks _battle_neili_cap _battle_power _battle_rewards _battle_road _battle_role _battle_scores _battle_troops
_branches _carry _checked_fight _choice_label _choose _conquest_side _cost_option _day_of _day_stamp _deed_fame _deed_points
_deliver_big_events _drill_gains _drills_with _drop_stale_references _event_battle _event_progress _event_text _everyday_options
_famed_news _fight_gone _fight_squad _fight_with _figures_here _file_battle _flavor_sink _free_text_of _goals _guide _heal_msgs
_heal_option _hide _hp_facts _idle _journal_guide _judged _kin _load_kin _log _lose_silver _mall_owner _menxia_entry _narrate
_note_guide _note_solved _outcome _own_scene_text _pending_options _pill_card_bonus _pill_day _play_rounds _player_hp
_player_hp_and_cap _preparing _present _push_progress _push_room _quick_client _raid_key _real_minutes _reconcile_season
_record_exp _record_faction _renown_after _reset_player_for_new_season _resisted_lines _save_kin _save_season _save_target
_season_prep _seize _shaped _shop_after _shop_live _shop_open _shop_say _side _solved_secrets _spar_mirror _spar_power
_squad_encounter _stamina_play_options _stamp_join _story_squad _style_note _sync_core _take_toll _tale_clue _terrain_note _tier3
_top_up_pills _wallet _week_unlock_tick _without_timetable _write _xinde action_notes add_gamble_narration advance answer_event
apply_flavor battle_card battle_card_id battle_detail battle_extra_html battle_list big_battle_ids bulletin choose chronicle_text
daily_push_cap econ_day event_free_text_prompt event_option_view event_tier faction_counts_text feature_status fight_request
for_world free_text_request heal heal_button is_admin is_big is_idle journal_html journal_top_html latest_battle_id
latest_entry_html location_text mark_seen new notice now_entry_html now_front odds options own_turn_checks paused_minutes
phase_memo pick_growth pill_cap pill_now pills_left_today place_minutes place_state_view publish push_trend reset_model_budget
rumor_layers rumors_text scene_art scene_text season_prep_view season_result season_scale set_anonymous set_gender shop_view
shows_battle_card stamp status_data status_text sync take_flavor_jobs take_stamina_pill trends_text wallet week_unlock_names
world_tick xinshen_purse xinshen_spend xinshen_view
""".split())

# Game.__init__ 的 self 屬性
GAME_INIT_ATTRS = frozenset("""
_draft _fight _flavor_jobs _last_wear _model_budget _preparing_memo advanced_real client content last_gamble move_mode narration
now odds_memo own_request own_turn rng state touched world
""".split())

# web/app.js 的 case（點擊 switch 與 switch (op)；同一行寫兩個 case 的都算）
APP_JS_CASES = frozenset("""
alloc-toggle allocate ask-no ask-yes bind_art board board-card board-card-close choose chuangong cultivate dismantle do drill-full
duty-close duty-open extra-more feed front-more fronts-help gate gender-go gender-pick growth growth-cancel growth-custom
growth-save growth-step hear-more here-all here-all-close hero-attrs join leave line-more logout melt melt_insight name_divine
news now-more opt-why own-more peek pill practice prep-growth prep-pick promo-sound recap renown-dot renown-open renown-sanren
renown-toggle report report-list rounds-more rv-scene scene-more sheet sheet-close shop-ask shop-leave slot stam-help switch tab
toggle-more unslot wheel wield wk wk-hide wk-next
""".split())

# web/app.js 比的 form.id
APP_JS_FORM_IDS = frozenset("""
answer-form arena-free create-form free-form gate-form outing-answer pw-form
""".split())

# web/app.js 比的 ev.target.id
APP_JS_TARGET_IDS = frozenset("""
adult anon hints-off mt-motto
""".split())

# web/app.js 的頂層名字（scripts/test_for.py 的 _JS_TOP）
APP_JS_TOP = frozenset("""
ACTION_TIMEOUT_MS ART_LOOK_STEPS BEAT_TIMEOUT_MS BOARD_CARDS CN_NUM DUE_TEXT ECHO_MS FREE_TEXT_OPTION GEAR_ICONS HERO_FIGURES
HERO_GEAR_NAMES LAYER_SEL MENXIA_SHOWN NEWS NEWS_PARTS PHONE POLL_MS PREP_TAGS PROMO_POSTER QUALITY_SEAL RECONNECT_MS SAY_HINTS
SAY_OPTION SAY_OPTIONS SELF_NEWS SENT_WAITING SHOP_ATTR SLOW_HINT_MS SLOW_POLL_MS SLOW_WAITING STANCE_NAMES STILL_WAITING TABS
TIMEOUT_TEXT TSEAL UNSENT_TEXT WAIT_HINT_MS WAIT_LINES afterPage answer api applyMain ask askGo boardArtHtml boardCardHtml
boardGearHtml boardsHtml bookRows busy calWords choose closeAsk closeEvents cnNum connectEvents createShort cueTimer dayCount
decorateHearsay doMain dueText enter esc events expHtml failText figSvg fitBars formMsg fxText gatePatchHtml genderRow goTab
growthEditHtml growthHtml guideSig hearToggle inkRipple lastAction lastBeat lastConnect lastPoll lilianHtml loadBoards loadMap
loadMenxia loadPatchNotes loadReports lockedAt lvHtml meltNum mx mxPlace newsPart newsSegHtml onPhoneChange onPushSelf onPushWorld
openBoardCard ordersDaily pageKey pageNews paintNewsDot patchLines pct placeTop pointerHeld poll pollInFlight pollTick
prepGrowthHtml prepHtml prepShihaiHtml pressed pro prologueKey promoCalm promoHtml promoSound pushDown putShopSpot rangerHtml
redrawHeld redrawPage reduceMotion refreshPage releasePointer render renderCreate renderGate renderKeepingSheet renderKeepingShop
renderPage renderShop renderTop renownDraw renownStripHtml ringWord rnPathClass rnTitleSpans rumorLayersHtml sayingId scoreHtml
seal sealTitle sealWatched selfNews sendingLine setMain setOffline setVar sheetHtml sheetWheel shopDo shopHtml shopMx shopNoteHtml
shopPolled shopSpot shown statUsesHtml syncScrollLock tabsHtml tenCells tickDue toast toastTimer toggleMore topHtml trendsTopHtml
tsealHtml typing waitLineFor watchQueue whoNameHtml wk7 wkName wkWord worldTimer
""".split())

# web/main.js 的頂層名字（同上）
MAIN_JS_TOP = frozenset("""
ACT_ART ACT_CELLS BATTLE_MOVE_LABEL CH_DO CH_LIVE CH_NEXT CH_NO DEAL_RE DRILL_FULL DUTY_GO DUTY_HEAD DUTY_NOTE EV_COST EV_ICON
EXPLORE_PREFIX EXPLORE_SUB FAME_GAP FIG_ACT FRONT_ENDS GATHER_BRANCH GATHER_ID GATHER_SAY_ID HERE_ALL HERE_ART HERE_HEAD HERE_ROW
HIRE LEDGER_AFTER LEDGER_NB MOVE_ICON NB_AFTER NB_MAX NOTICE_MENU NOW_LINE NOW_TAG NOW_WHEN ODDS_TONE OUTING_SUB PEOPLE_HEAD
PRACTICE_ID PRACTICE_NO_FOE PRACTICE_SUB REVEAL_GAP REVEAL_TOP ROUNDS_MARK ROUND_BITS SAY_AFTER SHORT_SUB SOCIAL_NO_ONE
SORTIE_CELL SORTIE_FULL_SUB SORTIE_LEFT SORTIE_LONG_SUB SORTIE_USED STORY TALE_MARK TALKED_OUT TIER_WORDS TRAIT_LEAD WK_BAR_GAP
WK_GO WK_HIDE WK_HIDE_STORE WK_HOWTO WK_IDLE WK_MAP WK_MORE WK_NEXT WK_SHEET WK_STEP WK_TUG WK_WHY actionBar armsLine attrNoteHtml
chapterCardHtml compactRound dealHtml dutyCardHtml dutyNow dutyParts dutySheetHtml evIconHtml evLabelHtml evOf fightCard firstText
fitFirstRound foldTraitItems foldTraitText frontEnds frontKey frontOpen frontReportHtml frontsBlock frontsHtml frontsTap gotoAttrs
hereAllHtml hereArt hereFold hereRowHtml hereSort idleMenu ink inkCell inkName jhHintsHtml keepGainsWhole ledgerText nbChunks
nbHtml nowBlock nowGains nowMore nowOneHtml nowTagTone nowToggle optLabelHtml optParts pageJianghu peekWeek peopleRowHtml
plainText reportLink resultHtml revampOn revealMoveCard revealShift roundsFold roundsMore sayHtml sceneArtHtml sceneUnderArt
splitChips stanceBars stancesHtml tierClass tierTag trailMoves uiV2 warHelp weekCardHtml whyHtml withGains withReportLink
wkBoxHtml wkDay wkHidden wkHideOne wkKey wkNext wkRepaint wkSheetHtml wkSidesHtml wkSplit wkStepOf wkSteps wkTap wkTugHtml
""".split())

# web/style.css 的 class
STYLE_CSS_CLASSES = frozenset("""
acard act-bar act-explore act-ink act-move act-notes act-row acts ad-alert ad-big ad-bigs ad-body ad-danger ad-danger-hd ad-entry
ad-found ad-head ad-hint ad-hold ad-holds ad-note ad-now ad-now-top ad-result ad-result-title ad-row ad-sec ad-sec-note
ad-sec-title ad-shell ad-tabs ad-tag ad-tile ad-tiles ad-trend ad-trends ad-wait ad-when alloc annal annal-kind annal-meta
annal-quote annal-reply annal-text annals annals-head answer arms-line art-body art-card art-result art-tactic ask ask-bg
ask-layer attr-note back bad bar battle-card battle-fold battle-mvp battle-shut bcard-sheet big bk-cover bk-slip bk-slip-ink
bk-thread bk-txt board board-book board-go board-list board-mine board-name board-note board-open board-owner board-rank board-row
board-tabs board-text book-back book-bar book-bar-title book-cover book-hills book-icon book-layer book-moon book-season book-sub
book-title boot brand brewing btn bulletin bulletin-item busy buy-pill card cast-side ch-at ch-card ch-foot ch-go ch-head ch-in
ch-next ch-no ch-sway ch-title chaos chaos-band chaos-tag cheer chip chips ck-card clamp clue clues cmp cur danger dark dc-chip
dc-chips dc-first dc-head dc-line dc-seal divine done dot down duty-card duty-note duty-sheet empty ev ev-fight ev-say ev-worry
even far fchip fchips field fig figure fit-art fit-box fit-clip fit-extra fit-fold fit-hide fit-min fit-short fit-space fit-tight
fit-title fits flash flip fold fold-body forging form-msg free free-note front front-bar front-ends front-head fronts fronts-help
full furnace-wrap g-bar g-cap g-flag g-head g-mcol g-mcols g-me g-merit g-mid g-mside g-mtitle g-now g-r g-rounds g-side g-tick
g-trail g-zone gate gate-patch gauge gear gear-bind gear-empty gear-ro gear-tactic gender-row ghost glow glyph-big glyph-from
glyph-mini go gold good grip growth-edit growth-foot growth-left growth-step guan guide guide-done guide-head guide-line
guide-next guide-scene guide-text guide-x has-art has-promo have hd heavy here here-row here-seal hi hint hit holding horse-thumb
hot howto hp hr-head hr-seals hs-n hs-name hs-tile huaben-banner huaben-cast huaben-index huaben-link huaben-meta huaben-page
huaben-said huang ico icon-btn ingot inj ink ink-drop ink-icon ink-img ink-note input ins insight jh-alloc jh-hint jh-hints k
label layer-open lbl leaf leaf-foot leaf-head leaf-hint leaf-recipe leaf-sign leaf-state leaf-text leaves legend lib lib-filter
lib-more libr lilian line linkish list lit log look-thumbs lvline m-gap mall-btn manual-entry mc-tags mdetail me melt-filter
melt-gap melt-go melt-hint melt-mode melt-tools melt-weak mine mini mlist mmore mood-fallen mood-famine mood-rebuild mood-war more
more-ico more-stats move-mode mpick mrow msg muted mval mvp-btns mvp-card mvp-cheer mvp-head mvp-hit mvp-pop mvp-result mvp-ribbon
mvp-side mvp-stage mvp-text mvp-who mx-note n naming nb near news-sub next no now now-line now-more now-one now-stamp now-text
now-text-one num odds off offline ok on onb-dim one open opt-note options order-head order-text own page paper patch-card
patch-old pc-ch pc-face pc-t peak peek-dot peer people-row person pick pill-btn pk-btns pk-txt podium pr-chips prep-card prep-go
prep-head prep-keep prep-layer prep-lead prep-note prep-opt prep-opts prep-split prep-steps primary promo promo-sound pts
pts-label push-err push-help push-kinds push-test-note q1 q2 q3 q4 qi qseal r-full r-short r2 r3 ready recap red report-big
report-detail report-group report-link report-top result result-event result-rank result-ranks result-text reward right rn-chip
rn-chips rn-dots rn-fame rn-hint rn-kou rn-lbl rn-more rn-note rn-peer-help rn-row rn-sanren rn-src rn-strip rn-tag rn-two rn-xia
road road-hint road-links road-tasks road-ways rounds rounds-head rounds-more rounds-tale row rv rv-now rv-scene rwhy say scene
scene-art score seal seal-act-go seal-act-line seal-bg seal-card seal-duel seal-ink seal-rim seg self-stats self-sub sending
sending-line sense sense-acts sense-canvas sense-hint sense-note sense-notes sense-pad sex-pick sex-tile sf-bar sf-chip sf-chips
sf-fill sf-gain sf-head sf-lost sf-name sf-num sf-row sf-text sfront sheet sheet-bg shell shine show side side-guan side-haoqiang
side-huang sides sides-card sides-first sides-note skip-prologue small snug solved split stack stam stam-help stance stance-how
stance-rule stances-line stat-uses static still sub summons-go summons-strip t-move t-name t-note tab tab-mall tabs tabs-inner
tags talk task tell ten them tick tie tier-3 tier-tag tight time tl-bubble tl-day tl-empty tl-gain tl-head tl-line tl-list tl-more
tl-sheet tl-tabs tl-title toggle top top-row tr-lv tr-meter train train-go train-why trait tseal tt-head tt-list tt-real tt-row
tt-state turn tx-chgs tx-extra tx-glyph tx-heading tx-hearsay tx-line tx-now tx-tight tx-when txt up used vitals vn-act vn-acts
vn-bg vn-box vn-chips vn-fig vn-foot vn-layer vn-leave vn-menu vn-paper vn-plate vn-say vn-x w-flames w-furnace w-furnace-lab
w-hub w-hub-rim w-rim w-seam w-shake w-slot w-slot-name w-slot-sub w-spin w-yang w-yin war war-help warn wbtns wheel where
where-at where-gap who who-ava who-col who-exp who-name who-ranger who-renown who-renown-line who-seg who-title why winfo wk-bar
wk-box wk-card wk-chev wk-detail wk-foot wk-gain wk-gap wk-go wk-head wk-howto wk-join wk-join-btn wk-lab wk-lead wk-locked wk-mid
wk-more wk-morebar wk-next wk-nextev wk-note wk-panel wk-quest wk-rules wk-seg wk-sheet wk-sheet-th wk-sides wk-strip wk-stripbar
wk-sub wk-tap wk-th wk-title wk-top wk-track wk-tug wk-tug-row wk-x worn wrap wrow you zj-layer
""".split())

# PlayerState 不標 QUIET 的欄位（心神五欄在裡面：閘門後 PM 標 QUIET，只擋多的，測試不用動）
PLAYER_PLAIN_FIELDS = frozenset("""
affinities ally ambush annals annals_mark anonymous arena arena_crowd_note arena_crowd_seen arena_day arena_last arena_today armor
armor_warned art_levels art_mastery art_quality art_slots arts arts_migrated ascension battle_results_seen bot bounties_done
bounty_pick bribed busy_until checkin_days checkin_picks cheers clue_items contrib contrib_weeks convoy create_rerolls
created_count creating defected dialogue_history divine_solved donate_day donated_today donations drill_day drills_today duel
duel_last duel_tally edge_warned enlist_end enlist_since enlist_step escort_pick event_rounds events_seen explore_seq faction
feasting feasts_paid figure_dented figure_rare_drops figure_wins flags follower_drill followers forge_counts forge_manual fortune
fragments fs_asked fs_asking fs_cooldown_until fs_counters fs_done furnace_day furnace_ready gender gender_chosen gift_day
gifts_today guarded_until_real guide_done guide_outro guide_skipped hearsay hearsay_keys heirloom held_gear hidden_until
hint_queue hints_off hints_seen history_start holding_bonus hunger_warned insight_fx insight_strength insights joined_at journey
last_offered_dialogue leg_actions legend_bought legend_fails legend_items legend_silver_bought letter_day letter_seq letters
location manual mark_days materials member mentor_day mentor_ready mingtie mingtie_box mingtie_day mingtie_hidden mingtie_made
mingtie_sent mount name naming newbie_done newbie_marks onboarding opp_clues opp_counts opp_done opp_fronts opp_items opp_pieces
opp_settled opp_tried own_insights own_serial parley_backing parley_days parley_debts parley_escort parley_owed parley_records
parley_road_leg parley_terms parted_done past_notes patron pending_ally pending_companion pending_defect pending_faction
picking_arena picking_audience picking_bounty picking_dadian picking_donate picking_market picking_smith picking_tavern pill_day
pills_today pills_topped_to plans_paid pushed qualified rack ranger_deeds ranger_evil ranger_good rank rank2_days
rank_action_weeks rank_hinted recent_sights relationship_notes renames_told renown_seen renown_told resting_since
road_rewards_today runic_pieces seal_seen season_number seclusion_done seclusion_start sect seen_events seen_real sense_misses
sense_serial sensing shop_clue shop_hold shop_line shop_line_seed showdowns showdowns_restored silver_donate_day silver_donated
smith_draft smith_page smith_rule smith_rules_told snubbed_until sortie_day sortie_horses sortie_treasures sorties_today stamina
stamina_pills stat_points stats summons summons_stall surveyed tagalong talk_memos talk_prev talks_today taunt_muted tavern_asks
tavern_guard_until tavern_heard tavern_known tavern_notes tavern_shield_until tavern_treat_day tavern_watches team tier3_drops
tier4_challenge_drops tier4_upgrades tier4_wins title_book top_merits treasure treasure_drops treasure_weeks
turns_since_consolidation tutorial_step upgrade_day upgrade_seq upgrades_today used_dialogue_options visited weapon weapon_serial
week_unlocked_at whispers xinde_cultivations xinshen_card xinshen_card_day xinshen_free xinshen_free_day
""".split())

# WorldState 不標 QUIET 的欄位
WORLD_PLAIN_FIELDS = frozenset("""
act act_reached active_pushers aid_tally ambushes arena arena_closed arena_day arena_pairs arena_seq armaments bounties bounty_day
bounty_seq bounty_week cal_offset cal_offset_history chronicle clashed clashes conquest conquest_on discuss_tally divine_lineup
echoes ended ending_id ending_text ending_title event_bonus event_mods feast_seq feasts figure_guards figures final_rankings
final_trends fired_thresholds flag_times flags forge_divine_per_kind forge_split_clues general_gifts gift_tally guard_credits
hooked_day hooked_week invites jianfa_on length_days life_turn lock_losers locks mandate mandate_result marks orders
pending_battle plots precise_actions promoted_today raided raids rallies renown_scale revealed rumors schedule seal_acts season21
season_one seat_ledger seats secret_sets showdown_opened_at showdowns_cancelled showdowns_opened showdowns_waiting signature_arms
sim_accum spar_tally storyline supply tavern_chatter tavern_hit_seq tavern_hits tavern_treats tavern_walls tavern_whispers
territory tianji time timeline trend_accum trends whereabouts xingshi xingshi_mark xingshi_ticket yuedan yuedan_week
""".split())

# 放行讀電腦時鐘的檔（fnmatch，比 tianxia/ 底下的相對路徑；不含 tests）。其他檔一處都不准：引擎不讀電腦時鐘（CLAUDE.md 原則）
CLOCK_OK = (
    "tianxia/accounts.py",  # 注入的 clock，預設 time.time
    "tianxia/bot_runner.py",  # 注入的 clock
    "tianxia/database.py",  # 等寫入權的期限
    "tianxia/features/*/routes.py",  # 路由是殼：拿現在時間傳進 Game（now 參數）、量模型的時間預算
    "tianxia/features/looks/studio_local.py",  # 本機生圖等待的期限，不在遊戲裡
    "tianxia/features/notify/webpush.py",  # 推送的時間戳（now 沒傳時）
)

# content/ 頂層的檔與資料夾
CONTENT_TOP = frozenset("""
art.json attributes.json attributes_v2.json banned_names.json banned_words.json characters.json check_voice.json combat_lines.json
config.json craft_names.json events figure_intros.json figures.json followers.json front_lines.json insights.json itineraries.json
locations.json map.json mark_rules.json materials.json orders.json patch_notes.json preset_recipes.json profiles relations.json
scenario.json secret_recipes.json shop_lines.json skills.json squads.json storylines.json timetable.json trait_lines.json
traits.json
""".split())

# content/events/ 的檔
CONTENT_EVENTS = frozenset("""
chapter_main.json general.json jizhou.json kou.json luoyang.json marks.json nanyang.json places.json ranger.json renown.json
stealth.json tales.json tiers.json treasure.json trend.json youzhou.json
""".split())

# tianxia/content.py 的 validate 讀的 c.<欄位>
VALIDATE_READS = frozenset("""
_only_pack banned_names battles characters config craft_names events figures foreshadows gear insight_scenes insights locations
mandate_timetable map mark_rules materials opening preset_recipes road_sights scenario sects skills squads timetable tutorial
""".split())

# ── 不用登入就打得到的路由（方法, 路徑）→ 理由：沒 cookie 打一次、不是 401 的都算。多一條要寫理由 ──
NO_LOGIN_ROUTES = {
    # 真的公開
    ("GET", "/"): "登入頁與遊戲殼頁，資料都在 /api",
    ("GET", "/admin"): "管理頁的殼頁，資料都在 /api/admin*（test_admin_routes 鎖著）",
    ("GET", "/journal.css"): "分享頁的樣式",
    ("GET", "/sw.js"): "手機通知的 service worker，瀏覽器不帶登入來拿",
    ("GET", "/manifest.webmanifest"): "安裝到手機主畫面用的",
    ("GET", "/api/patch_notes"): "登入頁底下的近期改版",
    ("GET", "/api/me"): "問自己登入了沒，沒登入回空的",
    ("POST", "/api/login"): "登入本身",
    ("POST", "/api/register"): "註冊本身",
    ("POST", "/api/logout"): "沒登入登出也是 200",
    ("GET", "/zhuan/{code}"): "公開的傳：分享代碼，唯讀",
    ("GET", "/zhanji/{code}"): "公開的戰記：分享代碼，唯讀",
    ("GET", "/api/looks/img/{look}/{sheet}"): "形象圖，<img> 不帶登入、只回圖",
    # 先於登入擋掉：沒登入也不是 401，但碰不到資料
    ("POST", "/api/mall/rename"): "先驗名號（空名 400），給了名號才問登入",
    ("GET", "/api/push"): "_web_push：沒開推送 404，開了要登入",
    ("POST", "/api/push/prefs"): "_web_push：同上",
    ("POST", "/api/push/test"): "_web_push：同上",
    ("POST", "/api/push/subscribe"): "_web_push：同上",
    ("POST", "/api/push/unsubscribe"): "_web_push：同上",
    ("POST", "/api/menxia/{op}"): "不認得的 op 404，認得的要登入",
    ("GET", "/api/events"): "HUB 是 None（沒開推送）就 404，連登入都不問",
    # identity（帳號與客服第 201 批；設計第七節）
    ("GET", "/api/identity/gate"): "登入頁要先知道哪幾條路開著；關著 404，只回設定裡公開的字（哪幾條路、客服信箱、Turnstile 網站金鑰），不看 cookie",
    # identity（帳號與客服第 203 批；設計 4.2、4.6）
    ("POST", "/api/identity/code/send"): "還沒登入才要用驗證碼登入；關著或這條路不在 ways 404；先過伺服器端 Turnstile，再過旁檔的一號、每日、來源、全服池節流，回應不透露有沒有帳號",
    ("POST", "/api/identity/code/verify"): "同上：驗碼本身就是登入；關著 404；單綁 tx_code cookie、錯 5 次作廢、5 分鐘過期，查無帳號只寫待處理不開帳號",
    # support（帳號與客服第 212 批；計畫「J 波落地時 PM 加的」第 1 條：關著一律 404、gate 先於登入與參數解析）
    ("POST", "/api/support/ticket"): "Config.support.enabled 關著 404，連登入都不問（同 /api/events）；開著沒登入 401（test_support_gate.py 守）",
    ("GET", "/api/support/mine"): "support：同上",
    ("POST", "/api/support/reply"): "support：同上",
    ("GET", "/api/support/queue"): "support：同上（開著還要是客服名單上的帳號，不是 404）",
    ("GET", "/api/support/ticket/{tid}"): "support：同上",
    ("POST", "/api/support/answer"): "support：同上",
    ("POST", "/api/support/close"): "support：同上",
    ("POST", "/api/support/lookup"): "support：同上",
}

# ── 開關關著，路由還是不回 404 的（方法, 路徑）→ 理由：現況，不改程式 ──
ROUTE_GATE_EXCEPTIONS = {
    ("GET", "/sw.js"): "notify：檔案本身，推送關著也拿得到；開關看 Config.web_push.enabled，由 _web_push 擋 /api/push 那五條",
    ("GET", "/api/annals"): "zhuan：見聞的行狀看 annals.on，不看 zhuan_end（Feature.enabled 沒有掛鉤吃這個開關）",
    ("GET", "/api/zhuan"): "zhuan：傳本身看 annals.on，zhuan_end 只管季末論功與多的選項；填的 season 1 不對丟 GameError 400，開著也一樣",
    ("POST", "/api/zhuan/write"): "zhuan：同上，寫不了丟 GameError 400，開著也一樣",
    ("POST", "/api/zhuan/share"): "zhuan：同上，分享不了丟 GameError 400，開著也一樣",
    ("POST", "/api/smith_line"): "smithy：店面打造頁問這一爐會怎樣，不算行動、不存檔，路由不問開關",
}

# ── 有路由、Feature.enabled 恆 True（沒有開關可關）的包 → 理由 ──
ROUTES_NO_SWITCH = {
    "guide": "教學說明，每一季都有",
    "companions": "人物與對話紀錄，每一季都有",
    "sense": "有所感沒有總開關（有沒有場景看內容）",
    "craft": "煉製頁每一季都有（自創有沒有開看 Config.arts.create_xinde）",
    "territory_acts": "形勢頁，有沒有地盤看 territory.on",
    "peers": "玩家卡與名帖，每一季都有",
    "travel": "一律開著：選單不走 Feature.options",
    "map": "輿圖每一季都有",
    "tale": "戰記沒有開關（start_tales 一定開）",
    "admin": "沒有開關；管理者認的是 Game.is_admin",
}

# AdminTool 用 no_gate 的工具（FEATURE_ADMIN_ACTIONS 裡 gate 是 features_core.no_gate）
ADMIN_NO_GATE = frozenset("""
cancel_battle clear_lock end_season fast_forward fire give_fragment give_opportunity issue_orders jump_next mingtie_remove
mingtie_restore next_season open_season outing_erase pause_clock push_trend resolve_event resume_clock revive_figure rotate_seats
schedule seal_assign seal_cancel seal_duel seal_emerge seal_fix seal_mandate seal_sink_check seal_stir set_trend start_battle
start_showdown summon
""".split())

# 包裡准賦值的 shell.<名字>（狀態放殼的模組變數，測試從 server.<名字> 讀）。新狀態放包自己的模組
SHELL_ASSIGNED = frozenset("""
NOTICE_THREAD TALES TALES_CLIENT TALES_THREAD TALE_RUNNING WEB_PUSH
""".split())

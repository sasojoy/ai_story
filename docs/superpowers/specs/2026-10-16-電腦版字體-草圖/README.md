# 電腦版字體（草圖）

企劃者 10/16 在電腦瀏覽器上看懸賞榜：「寬度是夠了～但字體這部分在電腦遊覽器上顯示看起來很吃力」。照規矩先出對比圖讓企劃者挑，程式沒改。

- 本機預覽（type.localhost:7899，週末設定、暫存資料庫），一個官軍角色在下曲陽、第 2 週，懸賞榜上 12 張告示（第 1、2 週兩批），身上有拳套、皮甲、一匹馬、700 兩、幾樣素材。
- 1920×1080、瀏覽器 100%、淺色。三版的 CSS 是在頁面上注入的（檔案附在這裡：`甲版.css`、`乙版.css`、`丙版.css`），**全部包在 `@media (min-width: 641px)`，手機一條都不動**。
- `X-頁.png` 是完整截圖；`對照-頁.png` 是四版同一頁並排，每一格是正中間 900px、原尺寸（沒有縮小），看到的字就是電腦上的大小。

## 三版改了什麼

- **現在**：店面照 FB-225 的 640px 一欄。告示的標籤 9.5px、標題 13px、期限 9.5px、內文 10.5px；點開的紙 12.5px、紙的標題 16px、期限 11.5px；掌櫃那一句 13px。江湖頁本來就是 15px。
- **甲：只放大店面那一層的字 ×1.3**，欄寬 640 不變。`web/style.css` 店面那一段（三間店、擂台、素材頁與軍需帳）每一條寫了字級的規則都 ×1.3（四捨五入到 0.5px，116 條），另外店面裡吃 body 15px、通用 `.btn` 15px、`.muted` 13px、`.label` 12px 的一起放大，機率條高 18 → 23.5px。江湖頁、修練頁、底部分頁不動。
- **乙：甲＋那一欄放寬到 760px**。字同甲；店面的底色、招牌那一列、掌櫃話、分頁、放大的紙照 760 對齊，捲的內容 736px；為了不再犯 FB-225（店面跟遊戲那一欄不一樣寬），`.shell`、`.tabs-inner` 也放到 760，所以江湖頁也變寬（江湖頁的字沒放大）。
- **丙：電腦上整頁照比例放大 1.3 倍**（`html { zoom: 1.3 }`）：店面、江湖頁、修練頁、底部分頁、狀態列全部一起大，640 的欄看起來是 832px。標籤 9.5 → 12.35px、標題 13 → 16.9px、江湖頁 15 → 19.5px。

## 甲與乙主要的字（從幾 px 到幾 px）

| 哪裡 | 選擇器 | 屬性 | 現在 | 甲、乙 |
|---|---|---|---|---|
| 告示與紙的標籤 | `.shop-board .note .tag, .shop-board .paper .tag` | font-size | 9.5px | 12.5px |
| 告示標題 | `.shop-board .note b` | font | 600 13px var(--serif) | 600 17px var(--serif) |
| 告示的期限、重賞 | `.shop-board .note small` | font-size | 9.5px | 12.5px |
| 告示內文 | `.shop-board .note` | font | 10.5px/1.4 var(--sans) | 13.5px/1.4 var(--sans) |
| 點開的紙 | `.shop-board .board-sheet .paper` | font-size | 12.5px | 16px |
| 紙的標題 | `.shop-board .paper h4` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| 紙上的期限、原因 | `.shop-board .paper .due, .shop-board .paper .why` | font-size | 11.5px | 15px |
| 掌櫃那一句 | `.shop-line` | font | 13px/1.6 var(--serif) | 17px/1.6 var(--serif) |
| 招牌 | `.shop-sign` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| 店內分頁 | `.shop-tab` | font | 13px var(--sans) | 17px var(--sans) |
| 鐵匠鋪架上的貨卡 | `.shop-item` | font | 12px/1.45 var(--sans) | 15.5px/1.45 var(--sans) |
| 貨卡的名字 | `.shop-item b` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| 手上揭著的那一格 | `.shop-board .slot` | font | 11px var(--sans) | 14.5px var(--sans) |
| 「你手上揭著的」那一行 | `.shop-board .held-row` | font-size | 12px | 15.5px |
| 店裡的鈕 | `.shop-layer .btn` | font-size | 15px（.btn） | 19.5px |

<details><summary>甲、乙全部 116 條</summary>

| 選擇器 | 屬性 | 現在 | 甲、乙 |
|---|---|---|---|
| `.shop-back` | font | 600 15px var(--sans) | 600 19.5px var(--sans) |
| `.shop-sign` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| `.shop-silver` | font | 600 13px var(--sans) | 600 17px var(--sans) |
| `.shop-line` | font | 13px/1.6 var(--serif) | 17px/1.6 var(--serif) |
| `.shop-page` | font | 13px var(--sans) | 17px var(--sans) |
| `.shop-tab` | font | 13px var(--sans) | 17px var(--sans) |
| `.shop-item` | font | 12px/1.45 var(--sans) | 15.5px/1.45 var(--sans) |
| `.shop-item b` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| `.shop-worn b` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| `.shop-wear` | font-size | 12px | 15.5px |
| `.tempers` | font-size | 12px | 15.5px |
| `.shop-big b` | font | 600 18px var(--serif) | 600 23.5px var(--serif) |
| `.shop-big small` | font-size | 12px | 15.5px |
| `.shop-note, .shop-empty, .shop-cap` | font-size | 12.5px | 16px |
| `.shop-warn` | font-size | 12.5px | 16px |
| `.shop-row .winfo` | font-size | 12px | 15.5px |
| `.shop-row .winfo b` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| `.naming .form-why` | font-size | 12px | 15.5px |
| `.shop-kinds .kind` | font | 14px var(--serif) | 18px var(--serif) |
| `.shop-kinds .kind sup` | font-size | 10px | 13px |
| `.pot-slot` | font | 12px var(--sans) | 15.5px var(--sans) |
| `.pot-slot b` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| `.pot-out` | font-size | 12.5px | 16px |
| `.pot-out b` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| `.pot-head` | font-size | 12.5px | 16px |
| `.pot-why` | font-size | 12px | 15.5px |
| `.shop-layer .odds` | font-size | 11px | 14.5px |
| `.shop-go` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| `.shop-layer .row-attr` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| `.shop-layer .cell` | font | 12px var(--serif) | 15.5px var(--serif) |
| `.shop-layer .cell .n` | font | 600 10px var(--sans) | 600 13px var(--sans) |
| `.cell small` | font | 10.5px var(--sans) | 13.5px var(--sans) |
| `.shop-layer .cell .why` | font | 10px var(--sans) | 13px var(--sans) |
| `.bundle` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| `.bundle small` | font | 12px var(--sans) | 15.5px var(--sans) |
| `.tapme` | font-size | 13px | 17px |
| `.forge-card .q` | font-size | 12px | 15.5px |
| `.forge-card h4` | font | 600 22px var(--serif) | 600 28.5px var(--serif) |
| `.forge-card .meta, .forge-card .fit` | font-size | 13px | 17px |
| `.forge-card .stat` | font | 600 15px var(--sans) | 600 19.5px var(--sans) |
| `.first-seal` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| `.shop-market .stall` | font | 10.5px var(--sans) | 13.5px var(--sans) |
| `.shop-market .stall .who` | font-size | 9.5px | 12.5px |
| `.shop-market .stall b` | font | 600 12px var(--serif) | 600 15.5px var(--serif) |
| `.shop-market .horse-card` | font-size | 12px | 15.5px |
| `.shop-market .horse-card h4` | font | 600 15px var(--serif) | 600 19.5px var(--serif) |
| `.shop-market .horse-card h4 small` | font | 11px var(--sans) | 14.5px var(--sans) |
| `.shop-market .horse-card .abil, .shop-market .horse-card .fed` | font-size | 11px | 14.5px |
| `.shop-market .horse-act small` | font-size | 11px | 14.5px |
| `.shop-board .held-row` | font-size | 12px | 15.5px |
| `.shop-board .slot` | font | 11px var(--sans) | 14.5px var(--sans) |
| `.shop-board .slot b` | font | 600 12px var(--serif) | 600 15.5px var(--serif) |
| `.shop-board .note` | font | 10.5px/1.4 var(--sans) | 13.5px/1.4 var(--sans) |
| `.shop-board .note .tag, .shop-board .paper .tag` | font-size | 9.5px | 12.5px |
| `.shop-board .note b` | font | 600 13px var(--serif) | 600 17px var(--serif) |
| `.shop-board .note small` | font-size | 9.5px | 12.5px |
| `.shop-board .stamp` | font | 600 11px var(--serif) | 600 14.5px var(--serif) |
| `.shop-board .note.held .stamp` | font-size | 10px | 13px |
| `.shop-board .board-sheet .paper` | font-size | 12.5px | 16px |
| `.shop-board .paper h4` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| `.shop-board .paper .due, .shop-board .paper .why` | font-size | 11.5px | 15px |
| `.shop-board .note.done .stamp` | font-size | 15px | 19.5px |
| `.shop-arena .ring-score b` | font | 700 34px var(--serif) | 700 44px var(--serif) |
| `.shop-arena .ring-score span` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| `.shop-arena .ring-meta` | font-size | 12.5px | 16px |
| `.shop-arena .ring-place` | font | 600 12px var(--sans) | 600 15.5px var(--sans) |
| `.shop-arena .ring-new` | font | 13px/1.6 var(--serif) | 17px/1.6 var(--serif) |
| `.shop-arena .ring-join small` | font-size | 11px | 14.5px |
| `.shop-arena .ring-note` | font-size | 11.5px | 15px |
| `.shop-arena .ring-h` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| `.shop-arena .ring-foe` | font-size | 12.5px | 16px |
| `.shop-arena .ring-foe .arts` | font-size | 11.5px | 15px |
| `.shop-arena .ring-foe .who b` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| `.shop-arena .ring-foe .rt` | font | 700 13px var(--sans) | 700 17px var(--sans) |
| `.shop-arena .ttl` | font-size | 11px | 14.5px |
| `.shop-arena .ring-foe .btn small` | font-size | 10.5px | 13.5px |
| `.shop-arena .ring-board .rk` | font | 700 13px var(--sans) | 700 17px var(--sans) |
| `.shop-arena .ring-board b` | font | 600 15px var(--serif) | 600 19.5px var(--serif) |
| `.shop-arena .ring-board .wl` | font-size | 11.5px | 15px |
| `.shop-arena .ring-round` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| `.shop-arena .ring-side b` | font | 600 15px var(--serif) | 600 19.5px var(--serif) |
| `.shop-arena .ring-side small` | font-size | 11px | 14.5px |
| `.shop-arena .vs` | font | 700 16px var(--serif) | 700 21px var(--serif) |
| `.shop-arena .ring-edge` | font-size | 12.5px | 16px |
| `.shop-arena .ring-arts, .shop-arena .ring-howto` | font-size | 12px | 15.5px |
| `.shop-arena .ring-tell` | font | 14px/1.6 var(--serif) | 18px/1.6 var(--serif) |
| `.shop-arena .ring-tell small` | font | 11px var(--sans) | 14.5px var(--sans) |
| `.shop-arena .ring-status` | font | 12px/1.5 var(--sans) | 15.5px/1.5 var(--sans) |
| `.shop-arena .ring-move b` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| `.shop-arena .ring-move small` | font-size | 11px | 14.5px |
| `.shop-arena .free-note` | font-size | 11.5px | 15px |
| `.shop-arena .ring-log` | font-size | 12px | 15.5px |
| `.shop-arena .ring-result` | font-size | 12.5px | 16px |
| `.shop-arena .ring-result h4` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| `.shop-arena .ring-result .stamp` | font | 600 16px var(--serif) | 600 21px var(--serif) |
| `.shop-layer .shop-done` | font | 13px/1.55 var(--serif) | 17px/1.55 var(--serif) |
| `.shop-layer .up-cell` | font | 12.5px var(--serif) | 16px var(--serif) |
| `.shop-layer .up-cell .from` | font-size | 12px | 15.5px |
| `.shop-layer .up-cell b` | font-size | 14px | 18px |
| `.shop-layer .up-cell small` | font | 10.5px var(--sans) | 13.5px var(--sans) |
| `.shop-layer .sell-row .nm b` | font | 600 14px var(--serif) | 600 18px var(--serif) |
| `.shop-layer .sell-row .nm small` | font | 11px var(--sans) | 14.5px var(--sans) |
| `.shop-layer .sell-row .btn` | font-size | 13px | 17px |
| `.shop-layer .arm-tile` | font-size | 12px | 15.5px |
| `.shop-layer .arm-tile b` | font | 600 18px var(--serif) | 600 23.5px var(--serif) |
| `.shop-layer .dn-room` | font-size | 12.5px | 16px |
| `.shop-layer .dn-pick` | font | 13px var(--serif) | 17px var(--serif) |
| `.shop-layer .dn-pick small` | font | 11px var(--sans) | 14.5px var(--sans) |
| `.shop-layer .dn-step .btn` | font-size | 15px | 19.5px |
| `.shop-layer .cell .pick` | font | 600 10.5px var(--sans) | 600 13.5px var(--sans) |
| `.shop-layer` | font-size | 15px（body） | 19.5px |
| `.shop-layer .btn` | font-size | 15px（.btn） | 19.5px |
| `.shop-layer .btn.small` | font-size | 14px（.btn.small） | 18px |
| `.shop-layer .muted` | font-size | 13px（.muted） | 17px |
| `.shop-layer .label` | font-size | 12px（.label） | 15.5px |
| `.shop-layer .odds` | height | 18px | 23.5px |

</details>

## 看了之後

- **最好讀：甲**。告示、紙、掌櫃話、貨卡都到 12.5～17px，告示兩欄、12 張照樣在第一屏放得下，紙在下緣也沒蓋到告示；改動只在店面那一段，江湖頁、輿圖一點都不動，風險最小。
- **乙**的字跟甲一樣，多出來的寬度讓告示寬一點、空一點，可是字沒有更好讀；江湖頁跟著變寬、字沒放大，一行變長反而比較難讀。另外設定抽屜（`.sheet`）與確認框（`.ask`）寫死 `max-width: 640px`，這一版沒跟著改，真的做要一起改。
- **丙**全部一起放大，最一致，江湖頁也比較好讀；代價是 1080 高的螢幕一屏看得到的東西少了（江湖頁「此地還能做」落到最底下），而且 `zoom` 會動到輿圖拖曳與縮放的座標換算（`getBoundingClientRect` 與滑鼠座標），選丙要另外驗輿圖。
- 沒看到破版：三版都沒有橫向捲軸，告示標題照舊最多兩行，紙的鈕沒有擠在一起。

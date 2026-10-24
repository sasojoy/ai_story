# 淡彩水墨試作（2026-10-24）

企劃者看了 `web/img/` 的向量第一版說「太簡陋、風格不一樣」，又說「你出一版正式圖給我看看」。這裡是程式能畫到的上限的試作，
兩張：`paint_yingru.py`（潁川汝南場景 1500×900）、`paint_luzhi.py`（盧植 1200×1600）。做法：毛筆形的墨塊（兩頭收尖）、
SVG 濾鏡做暈染（feDisplacementMap）、飛白（各向異性的 feTurbulence 當遮罩）、淡彩顆粒（模糊加噪點遮罩）、宣紙紋；暖色淡彩照
`web/promo-poster.jpg` 的調子。

    python3 scripts/art/paint/paint_yingru.py out.svg

還沒進 `web/img/`：企劃者點頭才照這一套出其餘的場景與事件圖；人物像這一套畫不好，要圖像模型。

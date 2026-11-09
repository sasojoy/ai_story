"""有所感包的內容驗證（第二輪第 100 批從核心 content.py 搬來，本體照搬）：content.validate 在原位經 features.check_at 叫（格在 core/features.py 的 CONTENT_SLOTS），先後不變；關著的包照驗。"""
from __future__ import annotations

import functools

from tianxia.core.content_base import check_line as _check_line
from tianxia.models import Content


def check_insight_scenes(c: Content, need) -> None:
    """有所感的場景（content/insight_scenes.json，悟意境設計 3.1、4.1）。沒有這個檔就不檢查（探索照舊直接悟）。
    - 每段三到四個做法、屬性各不相同；hints 要是它自己做法裡有的屬性；locations 要是存在的地點、tags 要至少對得上一個地點。
    - 用得到這段場景的每一個地點：至少一個做法是選得對的（做法屬性在這裡悟得到的意境裡），hints 也要指得到這裡悟得到的
      （寫了 hints 才查；通用場景可以不寫）——河邊的場景用在只悟得到火的地方，看懂場景的人反而選錯。
    - 探索悟得到意境的每一個地點（序章的草廬除外）都要有場景：不然那裡落在悟意境那一支時沒有卡可出。
    - 文字只能用繁體中文、不能寫數字或百分比（不攤成算，Q4）。"""
    from tianxia.insights import explore_gives, pool_attributes, scenes_for  # noqa: PLC0415  insights → state → models，延後免得循環

    scenes = c.insight_scenes
    if not scenes:
        return
    all_tags = {tag for loc in c.locations.values() for tag in loc.tags}

    check_text = functools.partial(_check_line, need)

    for scene in scenes.values():
        where = f"有所感 {scene.id}"
        attrs = [m.attribute for m in scene.methods]
        need(3 <= len(attrs) <= 4, f"{where}：做法要三到四個（現在 {len(attrs)} 個）")
        need(len(set(attrs)) == len(attrs), f"{where}：做法的屬性不能重複 {attrs}")
        need(set(scene.hints) <= set(attrs), f"{where}：hints {scene.hints} 要是它自己做法裡有的屬性")
        for loc_id in scene.locations:
            need(loc_id in c.locations, f"{where}：未知的地點 {loc_id}")
        for tag in scene.tags:
            need(tag in all_tags, f"{where}：沒有任何地點有標籤「{tag}」")
        for text, label in [(scene.title, "標題"), (scene.text.replace("{痕跡}", ""), "場景"), *((m.text, "做法") for m in scene.methods)]:
            check_text(f"{where}的{label}", text)
        need(not scene.prologue or not (scene.tags or scene.locations), f"{where}：序章的場景只給草廬用，不寫 tags、locations")
        need(scene.prologue or not scene.flags_add, f"{where}：flags_add 只給序章的場景用")
    if all(scene.prologue for scene in scenes.values()):
        return  # 只有序章草廬那一段：草廬外探索照舊直接悟，不要求每處都有場景
    hut = c.tutorial.location
    for loc in c.locations.values():
        if not explore_gives(loc, c) or loc.prologue_only or loc.id == hut:
            continue
        options = scenes_for(loc, c)
        need(bool(options), f"地點 {loc.id}：探索悟得到意境，卻沒有一段有所感的場景（insight_scenes.json 的 locations、tags 或通用場景）")
        pool = pool_attributes(loc, c)
        for scene in options:
            where = f"有所感 {scene.id}（用在 {loc.id}）"
            need(any(m.attribute in pool for m in scene.methods), f"{where}：沒有一個做法選得對（這裡悟得到的屬性 {sorted(pool)}）")
            need(not scene.hints or bool(set(scene.hints) & pool), f"{where}：線索 {scene.hints} 指不到這裡悟得到的 {sorted(pool)}")


def check_insight_strong(c: Content, need) -> None:
    """每個地點最濃的意境（意境提示設計第一節）：
    - 寫了的話，要是這個地點探索真的悟得到的；那一種意境要寫 strong_line（悟到時多的那一句）。
    - 開關開著時，探索悟得到意境的每一個地點（序章草廬除外）都要寫。
    - 有所感的場景要對得上：這裡用得到的每一段都要有最濃那一種屬性的做法；寫了線索的場景裡，至少一段指得到它
      （一段都沒寫線索的不查）——不然照著場景描寫選的人永遠選不到最濃的。
    正式內容的分布（每一種至少 5 處、五個大區都有）鎖在 tests/season/test_real_content.py。"""
    from tianxia.insights import explore_gives, scenes_for  # noqa: PLC0415  insights → state → models，延後免得循環

    hut = c.tutorial.location
    for loc in c.locations.values():
        where = f"地點 {loc.id}"
        gives = explore_gives(loc, c)
        if loc.insight_strong is None:
            need(not (c.config.insight_strong.enabled and gives and not loc.prologue_only and loc.id != hut),
                 f"{where}：意境提示開著，探索悟得到意境的地點都要寫 insight_strong")
            continue
        need(loc.insight_strong in gives, f"{where}：最濃的意境 {loc.insight_strong} 要是這裡悟得到的 {gives}")
        d = c.insights.get(loc.insight_strong)
        need(d is not None and bool(d.strong_line), f"{where}：最濃的意境 {loc.insight_strong} 要寫 strong_line（悟到時多的那一句）")
        if d is None or loc.insight_strong not in gives:
            continue
        scenes = scenes_for(loc, c)
        for scene in scenes:
            need(any(m.attribute == d.attribute for m in scene.methods),
                 f"有所感 {scene.id}（用在 {loc.id}）：沒有最濃那一種（{d.attribute}）的做法")
        hinted = [scene for scene in scenes if scene.hints]
        need(not hinted or any(d.attribute in scene.hints for scene in hinted),
             f"{where}：有所感的場景沒有一段線索指得到最濃的「{d.name}」（{d.attribute}）")

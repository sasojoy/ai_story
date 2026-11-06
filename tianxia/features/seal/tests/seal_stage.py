"""契約測試（tests/core/test_contract_features.py）把玉璽碎片擺進「有碎片、有登記」的局面：每擺好一種 yield 一個名字。

這一包沒有選項、選單、店面、狀態列的鍵（碎片卡與 seal: 前綴是第 28 批，還在 Game 上），跟前綴有關的三條對這一包是空的；擺出懷璽的局面是為了
讓「關著的包什麼都不給」在有登記、有抄本的時候也問一次。"""


def stages(game):
    yield "平常"
    from tianxia.features.seal import seal

    c = game.content
    if not seal.on(c):
        return
    name = game.state.player.name

    def _give(shared) -> None:  # 管理者指定的那一筆（登記記一筆 assign、補送寫成拿到）：一片在自己名下
        reg = seal.filled(shared.seal, c)
        shard = reg.shards[next(iter(c.seal))]
        shard.state, shard.holder, shard.since_season = "held", name, shared.season_number
        seal.log(reg, shared.season_number, "assign", shard=shard.id, holder=name)

    game.world.mutate(_give)
    game._deliver_seal_results()
    assert game.state.player.heirloom is not None
    yield "懷璽"

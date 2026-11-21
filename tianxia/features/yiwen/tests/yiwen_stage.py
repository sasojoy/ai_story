"""契約測試（tests/core/test_contract_features.py）把異聞擺進「有選項」的局面：每擺好一種 yield 一個名字。"""


def stages(game):
    yield "平常"
    from yiwen_kit import claim, turn_on  # noqa: PLC0415

    turn_on(game)
    claim(game, "fog_figure")  # 撞見了一則：選單接管（yiwen:open、yiwen:drop）
    yield "撞見"

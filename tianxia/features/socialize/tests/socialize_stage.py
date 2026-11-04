"""契約測試（tests/core/test_contract_features.py）把交友求見擺進「有選項」的局面：這一包不給選單（`menu` 沒接，求見名單的選項由 Game._everyday_options 的委派給，
位置算行為，計畫 1.4），`call:` 的選項只在求見名單開著時才有，平常那一種就夠；走一遍求見是這一包的煙霧測試。"""


def stages(game):
    yield "平常"

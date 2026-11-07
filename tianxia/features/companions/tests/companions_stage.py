"""契約測試（tests/core/test_contract_features.py）把人物情誼擺進「有選項」的局面：每擺好一種 yield 一個名字。

只擺「平常」：這一包的選項（託付那一顆）由 Game._everyday_options 的委派給、不經 options／menu 掛鉤（位置算行為，計畫 1.5），擺出託付的局面，
契約測試的「關著的包不給選項」不成立（原位不問 enabled；同決戰包）；走一遍託付的是這一包的煙霧測試與 test_errands。"""


def stages(game):
    yield "平常"

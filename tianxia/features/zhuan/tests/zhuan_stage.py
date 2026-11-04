"""契約測試（tests/core/test_contract_features.py）把列傳擺進「有選項」的局面：每擺好一種 yield 一個名字。
休季用票的鈕不是這一包的 options 掛鉤給的（Game._zhuan_options 在休季的行動列那一支，經一行委派叫包裡的 options），契約測試問不到，所以只有「平常」；
休季、手上有三張票那一局由 scripts/same_behavior.py 的 zhuan 軌與 test_biography 走。"""


def stages(game):
    yield "平常"

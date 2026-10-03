"""簡繁轉換（tianxia/zh.py）：煉製的名字會永久登記，所以這一層一定要確定性。"""
from unittest import mock

from tianxia import zh


def test_simplified_characters_become_traditional():
    assert zh.to_traditional("龙吟九霄") == "龍吟九霄"
    assert zh.to_traditional("孙坚说这话") == "孫堅說這話"


def test_traditional_text_is_left_alone():
    assert zh.to_traditional("裂江訣") == "裂江訣"


def test_characters_are_converted_without_swapping_phrases():
    """FB-014：s2twp 會照台灣用詞字典換詞，把古代語境裡的「的士卒」換成「計程車卒」。
    現在用 s2tw：只轉字（台灣正字），不換詞。"""
    assert zh.to_traditional("北军的士卒") == "北軍的士卒"
    assert zh.to_traditional("城中的士兵") == "城中的士兵"
    assert zh.to_traditional("他的士气") == "他的士氣"
    # 已經是繁體的原樣通過，不會被當成要換的詞
    assert zh.to_traditional("北軍的士卒") == "北軍的士卒"
    assert zh.to_traditional("城中的士兵") == "城中的士兵"
    # 同一個原因：台灣現代用語的換詞也不做（信息 != 資訊）
    assert zh.to_traditional("信息") == "信息"


def test_empty_text_is_fine():
    assert zh.to_traditional("") == ""


def test_japanese_variants_are_normalised():
    """實測真實模型煉製時回過「滯鉄心經」——「鉄」既不是簡體也不是繁體正字，OpenCC 的
    s2tw 原樣放過，而這個套件沒附 jp2t 字典，所以 zh.py 自己有一張異體字表。"""
    assert zh.to_traditional("滯鉄心經") == "滯鐵心經"
    assert zh.to_traditional("剣竜沢") == "劍龍澤"


def test_opencc_is_actually_available_here():
    """依賴真的裝起來了（requirements.txt 的 opencc-python-reimplemented）。"""
    assert zh.using_opencc() is True


def test_the_fallback_table_still_converts_the_common_cases():
    """OpenCC 不在時（import 失敗、字典讀不到）要退回手寫表，而不是讓簡體字流出去。"""
    with mock.patch.object(zh, "_CONVERTER", None), mock.patch.object(zh, "_TRIED", True):
        assert zh.using_opencc() is False
        assert zh.to_traditional("龙吟") == "龍吟"
        assert zh.to_traditional("滯鉄") == "滯鐵"  # 異體字表在兩條路徑上都會套用

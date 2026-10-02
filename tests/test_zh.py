"""簡繁轉換（tianxia/zh.py）：煉製的名字會永久登記，所以這一層一定要確定性。"""
from unittest import mock

from tianxia import zh


def test_simplified_characters_become_traditional():
    assert zh.to_traditional("龙吟九霄") == "龍吟九霄"
    assert zh.to_traditional("孙坚说这话") == "孫堅說這話"


def test_traditional_text_is_left_alone():
    assert zh.to_traditional("裂江訣") == "裂江訣"


def test_empty_text_is_fine():
    assert zh.to_traditional("") == ""


def test_japanese_variants_are_normalised():
    """實測真實模型煉製時回過「滯鉄心經」——「鉄」既不是簡體也不是繁體正字，OpenCC 的
    s2twp 原樣放過，而這個套件沒附 jp2t 字典，所以 zh.py 自己有一張異體字表。"""
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

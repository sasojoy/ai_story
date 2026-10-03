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


def test_text_that_is_already_traditional_passes_through_unchanged():
    """FB-018：OpenCC 的 s2t 系列把輸入一律當簡體，而「里、斗、了、准、夫、台」本身也是合法的
    繁體字，會被改錯（樓桑里→樓桑裡、米斗→米鬥、燈火通明了→燈火通明瞭、船夫→船伕）。
    模型多半直接寫繁體，所以繁體輸入必須原樣通過。"""
    for text in (
        "樓桑里",  # 涿郡地名，劉關張的對話很可能提到
        "米斗",
        "燈火通明了",
        "哪會准",
        "船夫",
        "台上",
        "北軍的士卒",
        "城中的士兵",
        "他的士氣",
        "信息",
        "太后",  # 后／系在簡體裡也常見，但 s2tw 的詞組字典認得這些繁體詞，不會改
        "皇后",
        "何太后",
        "鄉里",
        "系統",
        "采取",  # 采取：「采」旁邊沒有簡體字、也不在小名單裡，維持原字（已接受的取捨）
    ):
        assert zh.to_traditional(text) == text, text


def test_simplified_characters_still_convert_with_their_phrase_context():
    """只有真的簡體字才轉，而且仍然先整句轉一次：「头发」要是「頭髮」而不是「頭發」。"""
    assert zh.to_traditional("北军的士卒") == "北軍的士卒"
    assert zh.to_traditional("他的士气") == "他的士氣"
    assert zh.to_traditional("孙坚说这话题") == "孫堅說這話題"
    assert zh.to_traditional("头发") == "頭髮"


def test_mixed_text_converts_only_the_simplified_characters():
    """同一句裡簡體字照轉、繁體字不動。"""
    assert zh.to_traditional("樓桑里的军士说") == "樓桑里的軍士說"


def test_ambiguous_characters_next_to_a_simplified_character_follow_the_phrase_context():
    """(b1) 鄰字規則：「系、几、确、种、后」這類字繁簡都寫得出來。它前後只要有一個「只存在於簡體」的字，
    這個詞就是用簡體寫的，改信 s2tw 的詞組上下文。繁體的「系統」旁邊沒有簡體字，不受影響。"""
    assert zh.to_traditional("关系") == "關係"
    assert zh.to_traditional("几个") == "幾個"
    assert zh.to_traditional("确实") == "確實"
    assert zh.to_traditional("种类") == "種類"
    assert zh.to_traditional("系统") == "系統"
    assert zh.to_traditional("以后再说") == "以後再說"
    assert zh.to_traditional("他們的关系很好") == "他們的關係很好"
    assert zh.to_traditional("这里") == "這裡"  # 里本身繁簡皆可，但旁邊是简体的「这」
    assert zh.to_traditional("系統") == "系統"  # 統不是簡體字，所以不觸發


def test_characters_on_the_simplified_first_list_follow_s2tw_even_when_standing_alone():
    """(b2) 小名單：這些字在繁體文字裡幾乎不會單獨出現，所以旁邊沒有簡體字也交給 s2tw 的詞組字典決定
    （太后、皇后維持后，然后變然後）。"""
    assert zh.to_traditional("然后") == "然後"
    assert zh.to_traditional("好极了") == "好極了"
    assert zh.to_traditional("愿意") == "願意"
    assert zh.to_traditional("适合") == "適合"
    assert zh.to_traditional("价格") == "價格"
    assert zh.to_traditional("党") == "黨"
    assert zh.to_traditional("胜利") == "勝利"
    assert zh.to_traditional("丰富") == "豐富"
    assert zh.to_traditional("万一") == "萬一"
    assert zh.to_traditional("广告") == "廣告"
    assert zh.to_traditional("窗帘") == "窗簾"
    assert zh.to_traditional("苹果") == "蘋果"
    # 詞組字典認得的繁體詞不會被名單誤改
    assert zh.to_traditional("太后") == "太后"
    assert zh.to_traditional("皇后") == "皇后"
    assert zh.to_traditional("拮据") == "拮据"  # 拮据是繁體詞，据不能被改成據
    assert zh.to_traditional("夸父追日") == "夸父追日"
    assert zh.to_traditional("万俟") == "万俟"
    assert zh.to_traditional("茶几") == "茶几"


def test_the_simplified_first_list_only_holds_ambiguous_characters():
    """名單只放「候選含自己」的字：不然它根本沒作用（簡體字本來就會轉），多半是寫錯了。
    而繁體裡常見的字（里 斗 了 准 夫 台 系 采 于 干 余 面 松 谷 范 出 只 制 表，以及姜 征 扎 朴 周 云）
    不能放進去，否則繁體輸入又會被改。"""
    assert zh.using_opencc() is True
    ambiguous = _ambiguous_from_the_dictionary()
    assert sorted(ch for ch in zh.SIMPLIFIED_FIRST if ch not in ambiguous) == []
    common_in_traditional = set("里斗了准夫台系采于干余面松谷范出只制表姜征扎朴周云")
    assert sorted(common_in_traditional & set(zh.SIMPLIFIED_FIRST)) == []


def test_variant_normalisation_still_applies_to_traditional_input():
    """異體字表照留：「滯鉄心經」仍然變「滯鐵心經」，而「里」不受影響。"""
    assert zh.to_traditional("滯鉄心經") == "滯鐵心經"
    assert zh.to_traditional("鉄里") == "鐵里"


def _read_the_dictionary() -> tuple[set[str], set[str]]:
    """獨立於 zh.py 之外讀 OpenCC 的 STCharacters.txt。回傳（只存在於簡體的字, 繁簡皆可的字）：
    前者在表裡而且候選裡沒有它自己，後者在表裡而且候選裡有它自己。"""
    import os

    import opencc

    path = os.path.join(os.path.dirname(opencc.__file__), "dictionary", "STCharacters.txt")
    only: set[str] = set()
    ambiguous: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if not line:
                continue
            key, _, candidates = line.partition("\t")
            (ambiguous if key in candidates.split() else only).add(key)
    return only, ambiguous


def _simplified_only_from_the_dictionary() -> set[str]:
    return _read_the_dictionary()[0]


def _ambiguous_from_the_dictionary() -> set[str]:
    return _read_the_dictionary()[1]


def test_every_fallback_key_is_a_simplified_only_character():
    """退路表也照同一條規則：key 本身也是繁體字的項目（斗、岳、云、叶、万）要拿掉，
    否則 OpenCC 不在時「米斗」會變「米鬥」、「岳飛」會變「嶽飛」。"""
    assert zh.using_opencc() is True
    only = _simplified_only_from_the_dictionary()
    not_simplified_only = sorted(key for key in zh.FALLBACK if key not in only)
    assert not_simplified_only == []


def test_fallback_leaves_traditional_characters_alone_too():
    with mock.patch.object(zh, "_CONVERTER", None), mock.patch.object(zh, "_TRIED", True):
        assert zh.using_opencc() is False
        assert zh.to_traditional("米斗") == "米斗"
        assert zh.to_traditional("岳飛") == "岳飛"
        assert zh.to_traditional("云云") == "云云"
        assert zh.to_traditional("这") == "這"


def test_an_unreadable_dictionary_counts_as_opencc_unavailable():
    """讀不到 STCharacters.txt 就沒辦法判斷哪些字只存在於簡體，等於 OpenCC 不可用，走退路表。"""
    with (
        mock.patch.object(zh, "_CONVERTER", None),
        mock.patch.object(zh, "_TRIED", False),
        mock.patch.object(zh, "_TABLE", None),
        mock.patch.object(zh, "_TABLE_TRIED", False),
        mock.patch.object(zh, "_load_character_table", return_value=None),
    ):
        assert zh.using_opencc() is False
        assert zh.to_traditional("米斗") == "米斗"
        assert zh.to_traditional("这") == "這"


def test_a_length_changing_conversion_falls_back_to_per_character():
    """保險：s2tw 理論上不會改變長度；萬一改了，就不能逐位置合併，退回逐字轉換
    （只轉「只存在於簡體」的字，用候選的第一個）。"""

    class Stretching:
        def convert(self, text: str) -> str:
            return text + "多"

    with mock.patch.object(zh, "_CONVERTER", Stretching()), mock.patch.object(zh, "_TRIED", True):
        assert zh.to_traditional("米斗这军") == "米斗這軍"

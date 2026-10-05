"""簡繁轉換：把 LLM 產出的文字確定性地轉成繁體（台灣正字）。

**為什麼需要這個模組**：`companion_agent.py` 的 system prompt 已經寫了「全程使用繁體中文」，
實測只是部分改善，生成內容仍然會夾雜簡體字（實際看到過「孙坚」「这」「说」「话题」「闻言」）。
那是模型行為的限制，不是 prompt 寫法問題，所以要在**輸出端**做確定性的轉換。

煉製讓這件事從「難看」變成「不能接受」：煉出來的功法名字會**永久登記進全服的配方表**
（資料庫的 `skills` 與 `recipes` 表），第二個煉同一個配方的人看到的就是那個名字，而且事後改不掉。

用純 Python 的 `opencc-python-reimplemented`（`s2tw` 模式：只轉字、換成台灣正字，不換詞），
刻意不用官方 `opencc` 的 C++ binding——它帶編譯好的 DLL，而這台機器的 Windows 應用程式控制
已經封鎖過較新版 pandas 的 DLL（見 requirements.txt）。

**為什麼是 `s2tw` 而不是 `s2twp`（FB-014）**：`s2twp` 除了字，還會照台灣現代用語字典換詞
（的士→計程車、信息→資訊、軟件→軟體）。漢末的對話與戰況敘述裡「北軍的士卒」「城中的士兵」
「他的士氣」很常見，`s2twp` 會把它們換成「北軍計程車卒」「城中計程車兵」「他計程車氣」。
`s2tw` 不換詞，只轉字（孙坚说这话题→孫堅說這話題）。

**繁體輸入原樣通過，只有簡體字才轉（FB-018）**：OpenCC 的 s2t 系列把輸入一律當簡體，
而「里、斗、了、准、夫、台」這些字本身也是合法的繁體字，所以對本來就是繁體的字會改錯
（樓桑里→樓桑裡、米斗→米鬥、燈火通明了→燈火通明瞭、船夫→船伕）。模型多半直接寫繁體，
對話、戰況、煉製與點綴都會被改到。字分三種，依 OpenCC 的 `STCharacters.txt`
（每行「簡體字\t候選繁體字…」）判斷：
- **只存在於簡體**：在表裡，而且候選裡沒有它自己（这→這、军→軍、发→發 髮）。
- **繁簡皆可（ambiguous）**：在表裡，而且候選含自己（里→裏 里、斗→鬥 斗、了→了 瞭、几→幾 几）。
  它本身也是繁體字，但簡體文字裡也用它，光看一個字分不出來。
- 其餘：不在表裡，沒有簡體問題。

`to_traditional` 先用 `s2tw` 把整句轉一次（保留詞組的上下文：头发→頭髮而不是頭發、
太后／皇后仍是后），再逐位置合併，原文每個字依序判斷：
- (a) 只存在於簡體 → 採用轉完的字。
- (b) 繁簡皆可 → **只有**符合下列之一才採用轉完的字：
  - (b1) 鄰字規則：原文裡它前面或後面那個字是「只存在於簡體」的字。這個詞是用簡體寫的，
    所以信 s2tw 的詞組上下文（关系→關係、几个→幾個、确实→確實、种类→種類、以后再说→以後再說）。
    繁體的「系統」旁邊沒有簡體字，不受影響。
  - (b2) 它在 `SIMPLIFIED_FIRST` 這張小名單裡：這些字在繁體文字裡幾乎不會單獨出現，
    所以旁邊沒有簡體字也交給 s2tw 的詞組字典決定（然后→然後，但太后、皇后、拮据、夸父、万俟仍照詞組字典留原字）。
- (c) 其餘一律留原字（樓桑里、米斗、燈火通明了、船夫、台上、鄉里、哪會准）。

規則的取捨：繁簡皆可、又不在名單裡、旁邊也沒有簡體字的字（例如單獨的「里面」「采取」「干什么」的「干」）
會留原字——寧可少轉，不要把正確的繁體改錯。`FALLBACK` 退路表照字級規則：只放「只存在於簡體」的字。

**這個依賴壞掉不會讓遊戲壞掉**：import、建構失敗或字典檔讀不到時自動退回 `FALLBACK` 手寫對照表。
"""
from __future__ import annotations

import os
import re
from typing import NamedTuple

# OpenCC 不在時的退路：只蓋武俠文字裡最常見的簡體字。刻意不追求完整（完整的事交給 OpenCC），
# 目的是「就算依賴裝不起來，名字也不會以簡體字的樣子被永久登記」。
# 規則（FB-018）：key 必須是「只存在於簡體」的字。斗、岳、云、叶、万本身也是繁體字
# （米斗、岳飛、云云、叶韻、万俟），刀則轉了等於沒轉，所以都不放；測試會對照 STCharacters.txt 檢查。
FALLBACK = {
    "孙": "孫", "坚": "堅", "这": "這", "说": "說", "话": "話", "题": "題", "闻": "聞",
    "龙": "龍", "无": "無", "雾": "霧", "剑": "劍", "气": "氣", "内": "內",
    "风": "風", "电": "電", "铁": "鐵", "钢": "鋼", "银": "銀", "门": "門",
    "阴": "陰", "阳": "陽", "刚": "剛", "虚": "虛", "实": "實", "灵": "靈", "术": "術",
    "决": "決", "诀": "訣", "击": "擊", "杀": "殺", "战": "戰", "华": "華",
    "惊": "驚", "惧": "懼", "灭": "滅", "开": "開", "关": "關", "离": "離", "归": "歸",
    "乱": "亂", "义": "義", "兴": "興", "汉": "漢", "马": "馬", "鱼": "魚", "鸟": "鳥",
    "树": "樹", "泽": "澤", "渊": "淵", "镇": "鎮", "寿": "壽",
    "众": "眾", "师": "師", "传": "傳", "经": "經", "书": "書", "学": "學",
    "艺": "藝", "练": "練", "炼": "煉", "烧": "燒", "断": "斷", "续": "續", "变": "變",
    "转": "轉", "动": "動", "静": "靜", "随": "隨", "应": "應", "击": "擊", "势": "勢",
}

# 異體字（主要是日式新字體）：**OpenCC 的 s2tw（與 s2twp）不會轉這些**，因為它們既不是簡體
# 也不是繁體正字。實測用真實模型煉製時，`qwen2.5:14b` 回過「滯鉄心經」——「鉄」是日文的鐵，
# s2tw 原樣放過、`name_problem` 的「只能是中文字」也放過，於是會以異體字的樣子被永久登記。
# 這個套件沒有附 jp2t 字典（只有 s2tw/s2twp/t2tw 等），所以自己列一張常見的表。
VARIANTS = {
    "鉄": "鐵", "剣": "劍", "竜": "龍", "沢": "澤", "気": "氣", "広": "廣", "団": "團",
    "図": "圖", "帰": "歸", "県": "縣", "応": "應", "戦": "戰", "豊": "豐", "両": "兩",
    "満": "滿", "険": "險", "験": "驗", "圧": "壓", "勧": "勸", "観": "觀", "覚": "覺",
    "斉": "齊", "顔": "顏", "毎": "每", "巌": "巖", "総": "總", "経": "經", "絶": "絕",
    "続": "續", "図": "圖", "実": "實", "宝": "寶", "将": "將", "撃": "擊", "沪": "滬",
}

# (b2) 繁簡皆可、但在繁體文字裡幾乎不會單獨出現的字：旁邊沒有簡體字也交給 s2tw 決定（FB-018）。
# 加字的標準：它在現代台灣文字與三國題材裡的獨立繁體用法很少見；而且 s2tw 的詞組字典認得該字
# 的繁體詞（太后、皇后、拮据、夸父、万俟、丰姿、叶韻、南宮适、茶几、几案）。
# 繁體裡常見的字（里 斗 了 准 夫 台 系 采 于 干 余 面 松 谷 范 出 只 制 表，以及姜 征 扎 朴 周 云
# 這類人名、軍事用字）絕對不能放，否則繁體輸入又會被改。測試會檢查名單裡的字都確實繁簡皆可。
#   后几极愿适价党胜确种：簡體文字裡最常見的洩漏（然后、几个、极了、愿意、适合、价格、党、胜利、确实、种类）
#   厂广：廠、廣的簡體；繁體只剩部首名，工厂、广告、广东
#   据：據的簡體（据说、依据）；繁體只有拮据，詞組字典保護
#   挂：掛的簡體寫法；台灣正字是掛
#   夸：誇的簡體（夸张）；繁體只有夸父、夸克，詞組字典保護
#   叶：葉的簡體（叶子、树叶）；繁體只剩叶韻，詞組字典保護
#   万：萬的簡體（万一、一万）；繁體只有複姓万俟，詞組字典保護
#   丰：豐的簡體（丰富、丰收）；繁體只剩丰姿、丰神、丰采，詞組字典保護
#   蜡蝎虫苹柜帘腊荐：蠟、蠍、蟲、蘋、櫃、簾、臘、薦的簡體（蝎子、虫子、苹果、柜子、窗帘、腊月、推荐）；
#     台灣正字不用這些寫法
SIMPLIFIED_FIRST = frozenset("后几极愿适价党胜确种" "厂广据挂夸叶万丰" "蜡蝎虫苹柜帘腊荐")

# 模型偶爾把一個字吐成位元組碼（FB-075：長社火攻的回合敘事寫「旌旗仍<0xE5><0xB7><0x93>然屹立」）。
# 連續的一段當成一串 UTF-8 一起解；解不回字的位元組（缺了後半、或根本不是 UTF-8）直接拿掉。
BYTE_TOKENS = re.compile(r"(?:<0x[0-9A-Fa-f]{2}>)+")


def _decode_byte_tokens(text: str) -> str:
    def decode(match: re.Match[str]) -> str:
        hex_digits = match.group(0).replace("<0x", "").replace(">", "")
        return bytes.fromhex(hex_digits).decode("utf-8", errors="ignore")

    return BYTE_TOKENS.sub(decode, text)

_CONVERTER: object | None = None
_TRIED = False


class _CharTable(NamedTuple):
    """STCharacters.txt 的兩個切面（FB-018）。"""

    simplified_only: dict[str, str]  # 只存在於簡體的字 → 它的第一個繁體候選
    ambiguous: frozenset[str]  # 繁簡皆可的字：在表裡，而且候選含自己


# 第一次要用時才從 STCharacters.txt 建一次（跟 `_converter()` 一樣延後、快取）。
_TABLE: _CharTable | None = None
_TABLE_TRIED = False


def _load_character_table() -> _CharTable | None:
    """讀 OpenCC 的 STCharacters.txt。讀不到字典檔（沒安裝、路徑不對、格式不對）回 None。"""
    try:
        import opencc  # noqa: PLC0415  故意延後 import：這個依賴缺了也要能跑

        path = os.path.join(os.path.dirname(opencc.__file__), "dictionary", "STCharacters.txt")
        simplified_only: dict[str, str] = {}
        ambiguous: set[str] = set()
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\r\n")
                if not line:
                    continue
                key, _, rest = line.partition("\t")
                candidates = rest.split()
                if not key or not candidates:
                    continue
                if key in candidates:
                    ambiguous.add(key)
                else:
                    simplified_only[key] = candidates[0]
    except Exception:  # noqa: BLE001  任何原因都當成 OpenCC 不可用
        return None
    return _CharTable(simplified_only, frozenset(ambiguous)) if simplified_only else None


def _character_table() -> _CharTable | None:
    """字表，延後建構、快取；建不起來就永遠是 None。"""
    global _TABLE, _TABLE_TRIED
    if not _TABLE_TRIED:
        _TABLE_TRIED = True
        _TABLE = _load_character_table()
    return _TABLE


def _converter():
    """第一次要用時才建構（約 0.08 秒），建構失敗就永遠走 FALLBACK。
    字典檔讀不到、判斷不了哪些字只存在於簡體時，也一併視為 OpenCC 不可用。"""
    global _CONVERTER, _TRIED
    if not _TRIED:
        _TRIED = True
        try:
            import opencc  # noqa: PLC0415  故意延後 import：這個依賴缺了也要能跑

            converter = opencc.OpenCC("s2tw")  # 不用 s2twp，理由見模組 docstring（FB-014）
            _CONVERTER = converter if _character_table() is not None else None
        except Exception:  # noqa: BLE001  任何原因（沒安裝、DLL 被封鎖、字典讀不到）都退回手寫表
            _CONVERTER = None
    return _CONVERTER


def _merge(text: str, converted: str, table: _CharTable) -> str:
    """逐位置合併原文與 s2tw 轉完的結果（長度必須相同），規則見模組 docstring 的 (a)(b1)(b2)(c)。"""
    only = table.simplified_only
    last = len(text) - 1
    out: list[str] = []
    for i, (old, new) in enumerate(zip(text, converted)):
        if old in only:  # (a)
            out.append(new)
        elif old in table.ambiguous and (
            old in SIMPLIFIED_FIRST  # (b2)
            or (i > 0 and text[i - 1] in only)  # (b1) 前一個字是簡體字
            or (i < last and text[i + 1] in only)  # (b1) 後一個字是簡體字
        ):
            out.append(new)
        else:  # (c) 繁體字（含繁簡皆可、但沒有簡體跡象的字）原樣
            out.append(old)
    return "".join(out)


def to_traditional(text: str) -> str:
    """轉成繁體（台灣正字，不換詞），並把日式異體字一併正規化。
    已經是繁體的字原樣保留，只有簡體字才轉（FB-018，規則見模組 docstring）。
    模型吐出的位元組碼（「<0xE5><0xB7><0x8D>」）先解回字、解不回就拿掉（FB-075）：所有模型文字都經過這裡。"""
    if not text:
        return text
    text = _decode_byte_tokens(text)
    if not text:
        return text
    converter = _converter()
    table = _character_table() if converter is not None else None
    if converter is not None and table is not None:
        converted = converter.convert(text)  # 整句先轉一次，保留詞組的上下文（头发→頭髮）
        if len(converted) == len(text):
            text = _merge(text, converted, table)
        else:  # 保險：s2tw 理論上不會改變長度，改了就退回逐字轉換，只轉「只存在於簡體」的字
            text = "".join(table.simplified_only.get(ch, ch) for ch in text)
    else:
        text = "".join(FALLBACK.get(ch, ch) for ch in text)
    return "".join(VARIANTS.get(ch, ch) for ch in text)  # OpenCC 不處理異體字，見 VARIANTS


def using_opencc() -> bool:
    """目前是真的在用 OpenCC，還是退回手寫對照表（測試與診斷用）。"""
    return _converter() is not None

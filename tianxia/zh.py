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
對話、戰況、煉製與點綴都會被改到。規則：一個字**只存在於簡體**＝它在 OpenCC 的
`STCharacters.txt`（每行「簡體字\t候選繁體字…」）裡，而且候選裡沒有它自己
（这→這、军→軍、发→發 髮；而 里→裏 里、斗→鬥 斗 的候選含自己，表示它本身也是繁體字，不動）。
`to_traditional` 先用 `s2tw` 把整句轉一次（保留詞組的上下文：头发→頭髮而不是頭發），
再逐字合併：只有原字是「只存在於簡體」的才採用轉完的字，其餘留原字。
`FALLBACK` 退路表照同一條規則：key 本身也是繁體字的項目一律不放。

**這個依賴壞掉不會讓遊戲壞掉**：import、建構失敗或字典檔讀不到時自動退回 `FALLBACK` 手寫對照表。
"""
from __future__ import annotations

import os

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

_CONVERTER: object | None = None
_TRIED = False

# 「只存在於簡體」的字 → 它的第一個繁體候選（FB-018）；第一次要用時才從 STCharacters.txt 建一次。
_SIMPLIFIED_ONLY: dict[str, str] | None = None
_SIMPLIFIED_TRIED = False


def _load_simplified_only() -> dict[str, str] | None:
    """讀 OpenCC 的 STCharacters.txt：在表裡、而且候選裡沒有它自己的字才算「只存在於簡體」。
    讀不到字典檔（沒安裝、路徑不對、格式不對）回 None。"""
    try:
        import opencc  # noqa: PLC0415  故意延後 import：這個依賴缺了也要能跑

        path = os.path.join(os.path.dirname(opencc.__file__), "dictionary", "STCharacters.txt")
        table: dict[str, str] = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\r\n")
                if not line:
                    continue
                key, _, rest = line.partition("\t")
                candidates = rest.split()
                if key and candidates and key not in candidates:
                    table[key] = candidates[0]
    except Exception:  # noqa: BLE001  任何原因都當成 OpenCC 不可用
        return None
    return table or None


def _simplified_only() -> dict[str, str] | None:
    """「只存在於簡體」的字表，延後建構、快取；建不起來就永遠是 None。"""
    global _SIMPLIFIED_ONLY, _SIMPLIFIED_TRIED
    if not _SIMPLIFIED_TRIED:
        _SIMPLIFIED_TRIED = True
        _SIMPLIFIED_ONLY = _load_simplified_only()
    return _SIMPLIFIED_ONLY


def _converter():
    """第一次要用時才建構（約 0.08 秒），建構失敗就永遠走 FALLBACK。
    字典檔讀不到、判斷不了哪些字只存在於簡體時，也一併視為 OpenCC 不可用。"""
    global _CONVERTER, _TRIED
    if not _TRIED:
        _TRIED = True
        try:
            import opencc  # noqa: PLC0415  故意延後 import：這個依賴缺了也要能跑

            converter = opencc.OpenCC("s2tw")  # 不用 s2twp，理由見模組 docstring（FB-014）
            _CONVERTER = converter if _simplified_only() is not None else None
        except Exception:  # noqa: BLE001  任何原因（沒安裝、DLL 被封鎖、字典讀不到）都退回手寫表
            _CONVERTER = None
    return _CONVERTER


def to_traditional(text: str) -> str:
    """轉成繁體（台灣正字，不換詞），並把日式異體字一併正規化。
    已經是繁體的字原樣保留，只有「只存在於簡體」的字才轉（FB-018，見模組 docstring）。"""
    if not text:
        return text
    converter = _converter()
    only = _simplified_only() if converter is not None else None
    if converter is not None and only is not None:
        converted = converter.convert(text)  # 整句先轉一次，保留詞組的上下文（头发→頭髮）
        if len(converted) == len(text):
            # 逐位置合併：只有原字「只存在於簡體」才採用轉完的字，其餘（里、斗、了、准、夫…）留原字
            text = "".join(new if old in only else old for old, new in zip(text, converted))
        else:  # 保險：s2tw 理論上不會改變長度，改了就退回逐字轉換，用候選的第一個
            text = "".join(only.get(ch, ch) for ch in text)
    else:
        text = "".join(FALLBACK.get(ch, ch) for ch in text)
    return "".join(VARIANTS.get(ch, ch) for ch in text)  # OpenCC 不處理異體字，見 VARIANTS


def using_opencc() -> bool:
    """目前是真的在用 OpenCC，還是退回手寫對照表（測試與診斷用）。"""
    return _converter() is not None

import random
import re
from typing import Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from src.content_loader import load_json_or_default
from src.models import NPCProfile

DEFAULT_SCENE_TEMPLATES_PATH = "config/scene_templates.json"

# NPCProfile.character_tags / SceneTemplateEntry.required_tags 目前已知會用到的詞彙，
# 純粹是文件性參考清單，不是強制驗證用的 Enum——character_tags 仍是自由的 List[str]，
# 之後真的要新增詞彙直接打字串即可。這份清單存在的目的是避免同義詞氾濫（例如「巨乳」
# 跟「爆乳」意義重疊卻各用各的，導致模板比對不到），整理角色標籤/模板 required_tags
# 時優先從這裡挑選既有詞彙，真的沒有涵蓋到的概念再視情況擴充這份清單。
# 分類只是方便閱讀，資料層面就是一個扁平的 list，不分子欄位。
KNOWN_CHARACTER_TAGS = {
    "身材": ["巨乳", "貧乳", "蜂腰", "翹臀", "長腿", "嬌小", "豐滿", "纖瘦", "敏感體質"],
    "性格傾向": ["傲嬌", "病嬌", "無口", "天然", "腹黑", "母性", "強勢", "順從", "搖擺", "野性"],
    "身份/關係": ["處女", "人妻", "學生", "熟女"],
    "癖好取向": ["淫蕩", "痴女", "女奴", "母犬化", "純愛", "露出癖"],
    "行為/體位偏好": ["喜歡口交", "喜歡乳交", "喜歡背後式", "喜歡束縛", "喜歡露出"],
}

# 只認得 {name}/{player_name}（純字串替換）跟 {beat:xxx}（交給模型生成），
# 命名規則刻意跟 build_ending_prefix 等既有 f-string 組裝方式脫鉤，因為模板檔是資料
# 而不是程式碼，用簡單的 {token} 語法讓不寫 Python 的人（實際整理模板庫的人）也能照著寫。
_BEAT_PATTERN = re.compile(r"\{beat:[a-zA-Z0-9_]+\}")


class SceneTemplateVariant(BaseModel):
    text: str


class SceneTemplateEntry(BaseModel):
    """一個「動作」(act) 底下可以有多個 variants 供隨機挑選，避免同一個角色同一個 tag
    每次結局都長一模一樣。required_tags 是這個模板能不能套到某位 NPC 身上的唯一判準
    （比對 NPCProfile.character_tags，涵蓋身材/性格傾向/身份關係/癖好取向/行為偏好，
    不分子類別），跟這個 act 自己叫什麼名字無關——act 名稱只是 config/scene_templates.json
    裡給人看的分類標籤，不參與比對邏輯。

    這個類別身兼兩種用途：(1) ending_writer.py 的 climax 場景模板（原本的用法，
    整場結局挑一個模板套用），(2) src/intimate_mode.py 的性愛模式動作選單（每個
    entry 是選單裡的一個動作），後面新增的 4 個欄位只有 (2) 會用到，(1) 完全不受影響
    （ending_writer.py 呼叫 select_template 時不帶 ending_type，所以 applicable_endings
    不會被拿來篩選；check_tag/requires_check/is_finisher 也只有 intimate_mode.py 會讀）。"""
    required_tags: List[str] = Field(default_factory=list)
    label: Optional[str] = Field(
        default=None,
        description="性愛模式專用：選單按鈕上實際顯示的動作描述（例如「撫弄她的胸乳」），"
                     "留空時 fallback 用 act_name 本身當按鈕文字。act_name（config/"
                     "scene_templates.json 的 key）刻意保持穩定、給 required_tags 之外"
                     "還想用文字比對的地方引用；label 才是給玩家看的措辭，兩者職責分開，"
                     "改 label 不會動到 act_name 這個 identifier。"
    )
    applicable_endings: List[str] = Field(
        default_factory=list,
        description="性愛模式專用：限定這個動作只在 good（情投意合）或 bad（用強）路線"
                     "的選單裡出現；留空代表兩條路線都適用。刻意跟 required_tags 分開、"
                     "獨立運作的第二個篩選維度——required_tags 比對『她是誰』（身材/性格），"
                     "這個比對『這次走哪條路線』，不能用同一個機制取代，否則角色標籤又會"
                     "意外決定她能不能走某條結局路線"
    )
    check_tag: Optional[str] = Field(
        default=None,
        description="性愛模式專用：角色 character_tags 裡有這個標籤時，這個動作視為她"
                     "本來就喜歡/擅長，一定成功；沒有的話交給 intimate_mode.py 依好感度"
                     "算成功機率，成功後還有機率讓她習得這個標籤（永久寫回 character_tags）"
    )
    requires_check: bool = Field(
        default=False,
        description="性愛模式專用：是否要走成功/失敗判定；False 代表這個動作不涉及她的"
                     "意願風險（親吻/愛撫這類），選了就一定成立，不用判定也不需要 check_tag"
    )
    is_finisher: bool = Field(
        default=False,
        description="性愛模式專用：選到這個動作會結束整個性愛模式回合"
    )
    variants: List[SceneTemplateVariant] = Field(default_factory=list)


def load_scene_templates(path: str = DEFAULT_SCENE_TEMPLATES_PATH) -> Dict[str, SceneTemplateEntry]:
    """讀取模板庫。這份檔案內容本身很露骨（真人作品整理而來），刻意跟
    config/style_reference.txt 一樣不進版本控制（見 .gitignore）。找不到檔案（例如
    模板庫還沒整理好，或本機根本沒建這份檔案）時回傳空 dict，讓 find_matching_templates
    自然找不到任何符合的模板、優雅退回既有的自由生成流程，不會因為缺這份選用性檔案而
    整個掛掉。單一 act 解析失敗（格式寫錯）只跳過那一筆，不影響其他 act。"""
    raw = load_json_or_default(path, {})
    result: Dict[str, SceneTemplateEntry] = {}
    for act_name, entry in raw.items():
        try:
            result[act_name] = SceneTemplateEntry.model_validate(entry)
        except Exception:
            continue
    return result


def get_action_label(act_name: str, entry: SceneTemplateEntry) -> str:
    """性愛模式選單按鈕上該顯示的文字：entry.label 沒填就 fallback 用 act_name 本身。"""
    return entry.label or act_name


def find_matching_templates(
    profile: NPCProfile,
    templates: Dict[str, SceneTemplateEntry],
    ending_type: Optional[str] = None,
) -> List[Tuple[str, SceneTemplateEntry]]:
    """required_tags 必須是 profile.character_tags 的子集才算符合資格——這樣同一個模板
    可以被多個共用同一標籤的角色重複使用，不需要每個角色各寫一份。

    ending_type 預設 None，這時完全不套用 applicable_endings 篩選（ending_writer.py
    的 climax 場景挑選就是這樣呼叫——character_tags 描述的是這個角色「是誰」，跟她這次
    拿到的是 good 還是 bad 結局是兩件完全獨立的事，好壞結局本身由
    rules.py::evaluate_ending 依好感度分數判定，跟角色標籤無關，不該讓標籤篩選意外
    決定某條結局路線完全沒模板可用）。只有明確傳入 ending_type 時（目前只有
    intimate_mode.py 的動作選單會這樣做）才會額外要求 `not entry.applicable_endings
    or ending_type in entry.applicable_endings`——這是刻意跟 required_tags 分開的
    第二個獨立篩選維度，用在動作顆粒度夠細、明確需要區分『用強』/『情投意合』兩種
    動作語氣的場景，不會重蹈之前整場模板 mood 篩選讓角色沒東西可用的問題。"""
    npc_tags = set(profile.character_tags)
    matches = []
    for act_name, entry in templates.items():
        if not entry.variants:
            continue
        if not set(entry.required_tags) <= npc_tags:
            continue
        if ending_type is not None and entry.applicable_endings and ending_type not in entry.applicable_endings:
            continue
        matches.append((act_name, entry))
    return matches


def select_template(
    profile: NPCProfile,
    templates: Dict[str, SceneTemplateEntry],
    ending_type: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> Optional[Tuple[str, str]]:
    """從符合資格的模板中隨機挑一個 act、再從該 act 底下隨機挑一個 variant。
    沒有任何符合資格的模板時回傳 None，呼叫端 (ending_writer.py) 應該當成「這個角色
    這次沒有可用模板」，退回原本的自由生成路線。"""
    rng = rng or random
    matches = find_matching_templates(profile, templates, ending_type=ending_type)
    if not matches:
        return None
    act_name, entry = rng.choice(matches)
    variant = rng.choice(entry.variants)
    return act_name, variant.text


def substitute_names(text: str, profile: NPCProfile, player_name: str) -> str:
    disp_name = profile.display_name or profile.name
    return text.replace("{name}", disp_name).replace("{player_name}", player_name)


def has_beats(text: str) -> bool:
    return bool(_BEAT_PATTERN.search(text))


def fill_scene_template_beats(text: str, generate_beat: Callable[[str], str]) -> str:
    """依序處理文字裡的每一個 {beat:xxx} 插槽：呼叫 generate_beat(這個插槽之前、已經
    確定下來的完整文字) 取得填充內容，就地替換掉那個插槽再處理下一個。

    刻意一個一個插槽依序呼叫，而不是一次把所有插槽位置都告訴模型讓它一次生成完——這樣
    傳給 generate_beat 的「前綴」才會是這個插槽當下真正會看到的上文（前面的插槽已經
    填好，不是還留著 {beat:xxx} 這種佔位符）。這個保證兩條 backend 都需要：ollama 的
    「承接前文」指令語意、RWKV 的續寫語意，都要求前綴是乾淨、真正接得上的文字，否則
    生成出來的反應會對不上前面插槽實際填了什麼內容。

    generate_beat 允許回傳空字串（例如模型重試多次仍判定崩壞，見 ending_writer.py 的
    beat generator 實作）——這時該插槽直接消失，模板其餘的固定文字不受影響，是刻意的
    優雅降級：模板本身是人工寫好的完整劇情，插槽只是加分的角色個性化內容，不該因為
    這一小段生成失敗就讓整個模板作廢或重試整段。"""
    result = text
    while True:
        match = _BEAT_PATTERN.search(result)
        if not match:
            break
        prefix = result[:match.start()]
        filled = generate_beat(prefix).strip()
        result = result[:match.start()] + filled + result[match.end():]
    return result

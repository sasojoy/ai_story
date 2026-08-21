import random
from typing import Callable, Dict, List, Optional, Tuple

from src.models import NPCProfile
from src.scene_templates import (
    SceneTemplateEntry,
    fill_scene_template_beats,
    find_matching_templates,
    substitute_names,
)

# 好感度 -50~80 線性映射到 5%~95% 成功機率，只有 requires_check=True 且角色沒有
# check_tag 時才會用到（見 attempt_intimate_action）。兩端刻意不到 0%/100%，讓
# 沒有 tag 保底時永遠有機會成功、也永遠有失敗的風險，不會讓好感度極端值直接變成
# 「無論如何都會/不會成功」的死板判定。
_INTIMACY_MIN, _INTIMACY_MAX = -50, 80
_SUCCESS_PROB_MIN, _SUCCESS_PROB_MAX = 0.05, 0.95

# 判定成功但角色本來沒有 check_tag 時，額外把這個標籤永久教給她的機率。刻意調低
# （不是判定成功就一定學會），讓「她漸漸變得喜歡這件事」讀起來像是累積出來的轉變，
# 而不是第一次嘗試成功就定型。呼叫端 (web_ui.py 之後接上時) 需要在 tag_granted
# 非 None 時把角色存檔——這個函式只會就地修改傳入的 profile.character_tags，
# 不負責寫檔，跟專案裡其他純函式一致的職責劃分。
TAG_ACQUISITION_PROBABILITY = 0.3

# 判定失敗時的通用拒絕反應。刻意不要求模板庫替每個 requires_check 動作各寫一份失敗
# 版文案（會讓撰寫負擔直接翻倍）——失敗當下要傳達的情緒（害羞/抗拒/嗔怪）本來就
# 不需要跟哪個具體動作綁死，用一小組通用片段隨機挑一個即可，一樣支援 {name}/
# {player_name} 佔位符替換。
GENERIC_REFUSAL_VARIANTS = [
    "{name}臉頰驟然泛紅，猛地別開臉去，「不……不行……」聲音裡帶著自己都察覺得到的慌亂。",
    "{name}下意識地縮起身子，雙手交疊護在身前，眼神閃躲著不敢直視{player_name}。",
    "{name}輕輕搖了搖頭，嘴上這麼說著，身子卻還帶著一絲不易察覺的顫抖，顯然還沒能鼓起那個勇氣。",
]


def compute_success_probability(intimacy: int) -> float:
    """好感度線性映射到成功機率。只有 requires_check=True 且角色沒有 check_tag 的
    動作才會呼叫這個函式；有 check_tag 保底的動作一律直接判定成功，不看這個機率。"""
    span = _INTIMACY_MAX - _INTIMACY_MIN
    ratio = (intimacy - _INTIMACY_MIN) / span
    ratio = max(0.0, min(1.0, ratio))
    return _SUCCESS_PROB_MIN + ratio * (_SUCCESS_PROB_MAX - _SUCCESS_PROB_MIN)


def list_intimate_actions(
    profile: NPCProfile,
    templates: Dict[str, SceneTemplateEntry],
    ending_type: str,
) -> List[Tuple[str, SceneTemplateEntry]]:
    """性愛模式的動作選單：直接複用 scene_templates.py 既有的雙重篩選——required_tags
    （身材/性格比對，判斷這個動作對這個角色合不合理）+ applicable_endings（用強/
    情投意合路線，判斷這個動作這條路線該不該出現），不另外重造一套邏輯。"""
    return find_matching_templates(profile, templates, ending_type=ending_type)


class ActionResult:
    """一次動作判定的結果，純資料容器，方便呼叫端 (之後接上 web_ui.py 時) 決定畫面
    怎麼呈現，不在這裡耦合任何 UI 邏輯。"""

    def __init__(self, success: bool, tag_granted: Optional[str], narrative: str, is_finisher: bool):
        self.success = success
        self.tag_granted = tag_granted
        self.narrative = narrative
        self.is_finisher = is_finisher


def attempt_intimate_action(
    profile: NPCProfile,
    entry: SceneTemplateEntry,
    player_name: str,
    generate_beat: Callable[[str], str],
    rng: Optional[random.Random] = None,
) -> ActionResult:
    """判定一個動作是否成功，並生成對應的敘事文字。

    判定邏輯（使用者確認過的版本）：
    1. requires_check=False：不涉及她的意願風險（親吻/愛撫這類），直接視為成功，
       不做任何判定、不擲骰。
    2. requires_check=True 且她已經有 check_tag：視為她本來就喜歡/擅長，必定成功，
       同樣不擲骰（有 tag 保底時不該還讓機率有失敗的可能）。
    3. requires_check=True 但沒有 check_tag：依 compute_success_probability(目前
       好感度) 擲骰決定成功與否；成功的話再依 TAG_ACQUISITION_PROBABILITY 擲第二次
       骰，決定這次是否讓她永久習得這個 check_tag（直接就地寫回
       profile.character_tags，是否要存檔由呼叫端負責）。

    失敗時不從 entry.variants 挑選內容，改用 GENERIC_REFUSAL_VARIANTS 隨機挑一句
    通用拒絕反應。

    is_finisher 只有在這次判定成功時才會回報 True——選到一個要求型的收尾動作但被
    拒絕，性愛模式不該就此結束，玩家得換個方式或再試一次。"""
    rng = rng or random
    tag_granted: Optional[str] = None

    if not entry.requires_check:
        success = True
    elif entry.check_tag and entry.check_tag in profile.character_tags:
        success = True
    else:
        success = rng.random() < compute_success_probability(profile.intimacy)
        if success and entry.check_tag and entry.check_tag not in profile.character_tags:
            if rng.random() < TAG_ACQUISITION_PROBABILITY:
                profile.character_tags.append(entry.check_tag)
                tag_granted = entry.check_tag

    if success:
        variant = rng.choice(entry.variants)
        raw_text = substitute_names(variant.text, profile, player_name)
    else:
        raw_text = substitute_names(rng.choice(GENERIC_REFUSAL_VARIANTS), profile, player_name)

    narrative = fill_scene_template_beats(raw_text, generate_beat)
    return ActionResult(
        success=success,
        tag_granted=tag_granted,
        narrative=narrative,
        is_finisher=entry.is_finisher and success,
    )

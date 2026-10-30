"""必填欄位要寫進送出去的 schema（通則；2026-10-24 主機複驗的建議）。

pydantic 欄位有預設值時 `model_json_schema()` 不會把它列進 `required`，結構化輸出的語法於是允許模型整個略過那一欄：
10/19 書信每一封白跑第一趟、10/22 人物不說話（`narrative`）、10/24 NPC 智能 2.0 `ask` 漏填 14/30，三次同一個坑。
這裡掃 `tianxia/` 每一個 `chat_structured(...)` 呼叫點：`required_fields` 裡有 schema 沒列 required 的欄位，
就要開 `require_in_schema=True`。

`KNOWN` 是寫這條測試時還沒開的呼叫點，各附原因；**只准減不准加**：新的呼叫點照規矩開，
哪一處開了（或改掉了）就把它從清單拿掉，留著不用的條目這裡也會失敗。這些都在 `required_fields` 裡，
缺了會被 `_ensure_required_present` 攔下來重問一趟（白跑一趟，不是靜靜漏掉）；要開先在主機實測分數或字數不跟著移動。
"""

import ast
import importlib
import pathlib

import pytest
from pydantic import BaseModel

from tianxia import companion_agent, parley
from tianxia.ollama_client import _non_null, _require_in_schema

ROOT = pathlib.Path(__file__).resolve().parents[2] / "tianxia"

# (檔名, 回答類別) → 為什麼還沒開
KNOWN = {
    ("event_llm.py", "SuccessRateJudgment"): "隨口應對的評分：FB-223 守門測試連 kwargs 都要一字不差（丁批 QA 量到動它分數整體移動）",
    ("battle_instance.py", "SuccessRateJudgment"): "放手一搏的評分：同上一類，分數帶要主機重量才能動",
    ("battle_instance.py", "GambleScore"): "大場面放手一搏的評分：同上",
    ("features/feast/rules.py", "ToastScore"): "敬酒評分：同上（宴客搬進功能包 tianxia/features/feast/）",
    ("gather_llm.py", "reply_model"): "找素材的評分（create_model 動態組的類別，enum 照地點換）：同上",
    ("companion_agent.py", "DriftSynthesis"): "人物心境整理：背景執行、失敗不影響玩家，還沒實測",
    ("yuedan.py", "YuedanBatch"): "月旦評：背景執行、有固定段退路，還沒實測",
}


def _calls():
    """每一個 chat_structured 呼叫：(檔名, 行號, 回答類別的寫法, required_fields, require_in_schema, 模組)。"""
    # 功能包（tianxia/features/<包>/，開發規範手冊 3.2）也掃：檔名記相對 tianxia/ 的路徑、模組照點分的名字
    for path in sorted(ROOT.glob("*.py")) + sorted((ROOT / "features").glob("*/*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "chat_structured" and len(node.args) > 1):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            required = ast.literal_eval(kw["required_fields"]) if "required_fields" in kw else []
            forced = "require_in_schema" in kw and ast.literal_eval(kw["require_in_schema"]) is True
            rel = path.relative_to(ROOT)
            yield rel.as_posix(), node.lineno, ast.unparse(node.args[1]), required, forced, ".".join(rel.with_suffix("").parts)


def _model(module_name: str, expr: str):
    obj = importlib.import_module(f"tianxia.{module_name}")
    for part in expr.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj if isinstance(obj, type) and issubclass(obj, BaseModel) else None


def test_the_scan_finds_the_call_sites():
    names = {(f, m) for f, _, m, *_ in _calls()}
    assert ("companion_agent.py", "CompanionTurn") in names and ("letters.py", "LetterText") in names


def test_required_fields_are_written_into_the_schema_or_known():
    loose = set()
    for name, line, expr, required, forced, module in _calls():
        if not required or forced:
            continue
        model = _model(module, expr)
        listed = set(model.model_json_schema().get("required", [])) if model is not None else set()
        if model is None or any(f not in listed for f in required):
            loose.add((name, expr))
            assert (name, expr) in KNOWN, (
                f"{name}:{line} 的 {expr}：required_fields {required} 沒寫進送出去的 schema，"
                "加 require_in_schema=True（見本檔開頭）")
    assert not set(KNOWN) - loose, f"這幾處已經開了或改掉了，從 KNOWN 拿掉：{sorted(set(KNOWN) - loose)}"


# ── NPC 智能 2.0那幾輪：鍵要寫、也不准寫 null ────────────


@pytest.mark.parametrize("fields", [parley.ASK_FIELDS, parley.PLAN_FIELDS, parley.PLEA_FIELDS])
def test_parley_fields_are_required_and_never_null(fields):
    schema = _non_null(_require_in_schema(companion_agent.CompanionTurn.model_json_schema(), list(fields)), list(fields))
    assert set(fields) <= set(schema["required"])
    for f in fields:
        prop = schema["properties"][f]
        assert "null" not in str(prop.get("anyOf", "")) and prop.get("type") in ("string", "integer"), (f, prop)
        assert "default" not in prop

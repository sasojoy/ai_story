"""異聞兩個內容檔的驗證（設計 3.1、3.3；包的 checks.py）。"""
import copy

from tianxia.features.yiwen import checks, rules

from yiwen_kit import DATA


def _good() -> dict:
    return {"id": "odd_one", "title": "怪事一樁", "kinds": ["wild"], "hook": "路邊有樣東西在動⋯",
            "guesses": ["野狗", "小孩", "風"], "place_word": "路邊草叢", "thing_word": "東西", "frame": ""}


def test_openings_kinds_lengths_ids(content):
    base = checks.load(DATA)
    errors, _ = checks.check(content, base, rules.lines())
    assert errors == []
    figure = next(iter(content.characters.values())).name
    bad = [
        {**_good(), "id": "a1", "kinds": ["sea"]},  # 六個常數以外
        {**_good(), "id": "a2", "hook": "長" * 61},  # 超長
        {**_good(), "id": "a3"}, {**_good(), "id": "a3"},  # 重複 id
        {**_good(), "id": "a4", "hook": "路邊有三樣東西，共3件⋯"},  # 阿拉伯數字
        {**_good(), "id": "a5", "hook": f"{figure}站在路邊⋯"},  # 大勢人物的名字
    ]
    errors, _ = checks.check(content, base + bad, rules.lines())
    joined = "\n".join(errors)
    assert "a1" in joined and "kinds" in joined
    assert "a2" in joined and "超過" in joined
    assert "id 重複" in joined
    assert "a4" in joined and "阿拉伯數字" in joined
    assert "a5" in joined and figure in joined


def test_six_kinds_rule_only_at_thirty(content):
    """二十九句缺一種只警告；三十句缺一種硬擋。"""
    no_ford = [{**_good(), "id": f"k{i}", "kinds": [k]} for i, k in enumerate(["town", "temple", "wild", "hill", "camp"] * 6)]
    errors, warns = checks.check(content, no_ford[:29], rules.lines())
    assert errors == [] and any("渡" in w for w in warns)
    errors, warns = checks.check(content, no_ford[:30], rules.lines())
    assert any("渡" in e for e in errors)


def test_lines_groups_counts_and_slots(content):
    lines = rules.lines()
    errors, _ = checks.check(content, checks.load(DATA), lines)
    assert errors == []
    broken = copy.deepcopy(lines)
    broken["lead_in"] = broken["lead_in"][:2]  # 句數不夠
    broken["echo"] = ["你以為是{pik}。"] * 3  # 填空填不進去
    broken["close"] = ["說書的是假人。"] * 3  # 那三個詞
    errors, _ = checks.check(content, checks.load(DATA), broken)
    joined = "\n".join(errors)
    assert "lead_in" in joined and "至少" in joined
    assert "echo" in joined and "填空" in joined
    assert "close" in joined and "假人" in joined


def test_real_content_files_pass(content):
    """正式檔（五句樣例）照檔驗：只警告句數不夠，沒有硬擋。"""
    errors, warns = checks.check(content, checks.load(rules.FILES["openings"]), rules.lines())
    assert errors == [] and warns


def test_broken_end_is_checked(content):
    """第 264 批①：收尾替身句那一組少了報、填空只認 {pick}、{thing}。"""
    lines = copy.deepcopy(rules.lines())
    assert len(lines["broken_end"]) >= 3
    lines.pop("broken_end")
    errors, _ = checks.check(content, checks.load(DATA), lines)
    assert any("broken_end" in e and "至少 3 句" in e for e in errors)
    lines["broken_end"] = ["有人{pick}，{who}的事了了。"] * 3
    errors, _ = checks.check(content, checks.load(DATA), lines)
    assert any("broken_end" in e and "填空" in e for e in errors)

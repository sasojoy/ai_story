"""異聞模板句的填空（評審焦點 1）：玩家的字放進去之後不再掃，裡面的 {…} 照字面留著。"""
from tianxia.features.yiwen import rules


def test_player_words_with_braces_stay_literal():
    template = rules.lines()["zhupi"][0]
    got = rules.fill(template, who="{words}", words="一隻{who}的鵝{place}")
    assert "{words}" in got and "一隻{who}的鵝{place}" in got
    assert rules.fill("{a}{b}", a="{b}", b="乙") == "{b}乙"
    assert rules.fill("你以為是{pick}。", other="x") == "你以為是{pick}。"  # 沒給的鍵照字面

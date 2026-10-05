"""大場面請模型判讀戰局（武學與成長設計 8.3、計畫三 Task 2）：模型只給優勢與兩版過程，夾在 ±swing；
叫不動、太慢、回得不合格式一律回 None（呼叫端照平常的回合演出）。"""
from unittest import mock

from tianxia import fight_llm, naming
from tianxia.ollama_client import OllamaClient

REAL_CHAT_STRUCTURED = OllamaClient.chat_structured  # 匯入時抓：conftest 的 autouse 之後會換成「連不上」，要真的 client 的測試用它

REQUEST = fight_llm.FightRequest(
    option_id="act:train", squad_id="boss", location="lake", battle_seq=0, event=None,
    ours=["沈浪：武學【旋風腿】中品・屬快"], theirs="翻江龍（屬剛，難度 200）",
)


def _client(reply=None, error=None):
    client = mock.Mock()
    if error:
        client.chat_structured.side_effect = error
    else:
        client.chat_structured.return_value = reply
    return client


def test_the_advantage_is_clamped_to_the_swing():
    got = fight_llm.judge(_client(fight_llm.Judgment(advantage=40, winning="贏", losing="輸")), REQUEST, 15)
    assert got.advantage == 15 and (got.winning, got.losing) == ("贏", "輸")
    got = fight_llm.judge(_client(fight_llm.Judgment(advantage=-99, winning="贏", losing="輸")), REQUEST, 15)
    assert got.advantage == -15


def test_a_failed_call_gives_nothing():
    assert fight_llm.judge(_client(error=RuntimeError("連不上")), REQUEST, 15) is None
    assert fight_llm.judge(_client(reply=None), REQUEST, 15) is None
    assert fight_llm.judge(None, REQUEST, 15) is None


def test_an_advantage_that_is_not_a_number_counts_as_even():
    """Review Focus 4：優勢不是數字（繞過驗證的回答）就當 0，過程照用；模型不能直接決定勝負。"""
    for odd in ("很多", None, float("inf"), float("nan")):
        reply = fight_llm.Judgment.model_construct(advantage=odd, winning="贏", losing="輸")
        got = fight_llm.judge(_client(reply), REQUEST, 15)
        assert got is not None and got.advantage == 0 and (got.winning, got.losing) == ("贏", "輸"), odd


def test_the_accounts_come_back_traditional_one_paragraph_and_short():
    """過程轉成繁體（模型常夾簡體字）、換行收成一段（卡片上「過程」底下就是一段話）、每一版最多 TEXT_MAX 個字。"""
    reply = fight_llm.Judgment(advantage=5, winning="  这一招\n说时迟那时快  ", losing="落" * 500)
    got = fight_llm.judge(_client(reply), REQUEST, 15)
    assert got.winning == "這一招說時遲那時快" and len(got.losing) == fight_llm.TEXT_MAX


def test_a_long_account_is_cut_at_the_end_of_a_sentence():
    """太長的過程不從句子中間斷：退回 TEXT_MAX 以內最後一個「。！？」（後面緊跟的收尾引號一起留）；沒有句號才硬切。"""
    sentence = "敵勢如潮，你連退數步。"  # 11 字：18 句是 198 字，第 19 句會被 200 字切在中間
    got = fight_llm.judge(_client(fight_llm.Judgment(winning=sentence * 20, losing="他喝道：「再來！」" * 30)), REQUEST, 15)
    assert got.winning == sentence * 18
    assert got.losing.endswith("！」") and len(got.losing) <= fight_llm.TEXT_MAX and got.losing.count("「") == got.losing.count("」")
    short = fight_llm.judge(_client(fight_llm.Judgment(winning="一刀劈下", losing="退")), REQUEST, 15)
    assert (short.winning, short.losing) == ("一刀劈下", "退")  # 不長就不動（沒有句號也照留）


MARKDOWN_ACTIVE = "`*_#>[]|~<\\"  # 一段話裡會被 Markdown 當成語法的 ASCII 字元（中文敘事用不到）


def test_markdown_syntax_in_an_account_is_stripped_so_it_stays_one_plain_paragraph():
    """模型的字是不可信的輸入，卡片用 Markdown 轉成 HTML：連結、圖片會被畫出來（圖片是瀏覽器去抓外面的網址）、
    開頭的 ``` 會把後面的「結果」「獲得與損失」吞進程式碼區塊、開頭的 > 變引言（Final review Minor 1）。
    語法字元一律拿掉，只剩一段話；中文標點、全形括號與引號照留。"""
    hostile = [
        "```\n你一拳打出，對方連退三步。", "![圖](http://e.com/a.png)你出手如電。", "> 你退了一步，咬牙再上。",
        "[點我](http://e.com)你收劍而立。", "# 標題\n你搶上一步。", "你**橫掃**一腿，__對方__悶哼。", "| a | b |\n|---|---|\n你攻出一掌。",
        "~~~\n你翻身避開。", "<img src=x onerror=1>你側身一閃。", "\\[你\\]抱拳。",
    ]
    for text in hostile:
        got = fight_llm.judge(_client(fight_llm.Judgment(winning=text, losing=text)), REQUEST, 15)
        for account in (got.winning, got.losing):
            assert not any(ch in account for ch in MARKDOWN_ACTIVE) and account, (text, account)
    plain = "他喝道：「再來！」你冷笑一聲（不屑），拔劍相迎。"
    got = fight_llm.judge(_client(fight_llm.Judgment(winning=plain, losing=plain)), REQUEST, 15)
    assert got.winning == got.losing == plain  # 中文標點、全形括號與引號不動


def test_an_account_that_is_only_a_rule_line_cannot_turn_the_heading_above_into_a_heading():
    """整段只有 --- 或 === 的話，接在「**過程**」下一行會變成 Markdown 的標題底線；開頭的 -、+、= 也一併拿掉。"""
    for text in ("---", "===", "- - -", "+++", "-你出手"):
        got = fight_llm.judge(_client(fight_llm.Judgment(winning=text, losing=text)), REQUEST, 15)
        assert not got.winning.startswith(("-", "+", "=")), text
    assert fight_llm.judge(_client(fight_llm.Judgment(winning="---", losing="===")), REQUEST, 15).winning == ""


def _post_replying(content: str, sent: list):
    def post(url, json=None, timeout=None):
        sent.append(timeout)

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": content}}

        return Reply()

    return post


def test_an_even_judgment_is_kept_by_the_real_client(monkeypatch):
    """勢均力敵（advantage 0）是合法的判讀，不是「回答被截斷」：真的 chat_structured 只把必填欄位的空值當截斷，
    所以必填的只有兩版過程（計畫三 G2）——一趟就收，不重問、不丟掉。"""
    sent = []
    monkeypatch.setattr("requests.post", _post_replying('{"advantage": 0, "winning": "贏", "losing": "輸"}', sent))
    monkeypatch.setattr(OllamaClient, "chat_structured", REAL_CHAT_STRUCTURED)
    got = fight_llm.judge(OllamaClient(), REQUEST, 15)
    assert got == fight_llm.Judgment(advantage=0, winning="贏", losing="輸") and len(sent) == 1


def test_the_budget_is_split_across_both_posts_on_a_copy(monkeypatch):
    """鎖外這一次最多花 budget 秒（server.prepare_fight 從 big_fight_budget_seconds 扣掉 A 段等鎖的時間傳進來）：
    chat_structured 一次最多送兩趟（第一趟＋重問），所以一趟最多一半，用 client 的複本、原本那個不動
    （跟 naming.propose 同一套分法）。分不到 MIN_POST_SECONDS 就不叫了。"""
    seen = []

    def chat_structured(self, messages, response_model, **kwargs):
        seen.append((self.timeout, messages, kwargs.get("required_fields")))
        return fight_llm.Judgment(advantage=3, winning="贏", losing="輸")

    monkeypatch.setattr(OllamaClient, "chat_structured", chat_structured)
    client = OllamaClient(timeout=120)
    assert fight_llm.judge(client, REQUEST, 15, budget=50).advantage == 3
    timeout, messages, required = seen[0]
    assert timeout == 50 / naming.POSTS_PER_CALL and client.timeout == 120
    assert required == ["winning", "losing"]
    asked = messages[-1]["content"]
    assert "沈浪：武學【旋風腿】中品・屬快" in asked and "翻江龍（屬剛，難度 200）" in asked and "-15 到 15" in asked
    assert fight_llm.judge(client, REQUEST, 15, budget=naming.MIN_POST_SECONDS) is None and len(seen) == 1
    assert fight_llm.judge(client, REQUEST, 15).advantage == 3 and seen[-1][0] == 120  # 沒給預算：照 client 自己的

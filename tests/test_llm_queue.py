"""LLM 佇列（線上架構設計 5.2）：真人先、假人有上限、一人一件、排太久拿退路、看得到前面幾件。"""
import threading
import time

import pytest

import llm_queue


def _hold(queue, owner, *, bot=False, wait=5.0):
    """讓 owner 的一件在佇列裡跑著不放，直到 release.set()；回傳 (started, release, thread, result)。"""
    started, release, result = threading.Event(), threading.Event(), {}

    def job():
        started.set()
        release.wait(5)
        return f"{owner} 的結果"

    def go():
        result["value"] = queue.run(owner, job, fallback="退路", bot=bot, wait=wait)

    thread = threading.Thread(target=go)
    thread.start()
    return started, release, thread, result


def _wait_until(predicate, seconds=2.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_runs_the_job_and_returns_its_result():
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    assert queue.run("甲", lambda: 7, fallback=0) == 7
    assert queue.snapshot() == {"running": 0, "waiting": 0, "bots_waiting": 0}


def test_humans_go_before_bots_that_queued_earlier():
    queue = llm_queue.LlmQueue(slots=1, bot_cap=2)
    started, release, holder, _ = _hold(queue, "佔著的人")
    assert started.wait(2)
    order = []
    bot = threading.Thread(target=lambda: queue.run("假人甲", lambda: order.append("假人"), fallback=None, bot=True))
    bot.start()
    assert _wait_until(lambda: queue.snapshot()["bots_waiting"] == 1)
    human = threading.Thread(target=lambda: queue.run("真人乙", lambda: order.append("真人"), fallback=None))
    human.start()
    assert _wait_until(lambda: queue.snapshot()["waiting"] == 1)
    assert queue.position("真人乙") == 1 and queue.position("假人甲") == 2
    release.set()
    for t in (holder, bot, human):
        t.join(2)
    assert order == ["真人", "假人"]


def test_one_job_per_person_the_second_gets_the_fallback():
    """同一個人連按兩下、開兩個分頁：第二件直接拿退路，不叫模型（Review Focus 1）。"""
    queue = llm_queue.LlmQueue(slots=2, bot_cap=1)
    started, release, holder, _ = _hold(queue, "甲")
    assert started.wait(2)
    called = []
    assert queue.run("甲", lambda: called.append(1), fallback="退路") == "退路"
    assert called == []
    release.set()
    holder.join(2)


def test_bot_cap_full_means_fallback():
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    started, release, holder, _ = _hold(queue, "假人甲", bot=True)
    assert started.wait(2)
    assert queue.run("假人乙", lambda: "叫了", fallback="退路", bot=True) == "退路"
    release.set()
    holder.join(2)


def test_waiting_too_long_gives_the_fallback_without_calling():
    """排超過 wait 秒：拿退路、不叫模型，位置讓出來（Review Focus 2）。"""
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    started, release, holder, _ = _hold(queue, "甲")
    assert started.wait(2)
    called = []
    assert queue.run("乙", lambda: called.append(1), fallback="退路", wait=0.05) == "退路"
    assert called == [] and queue.position("乙") is None
    release.set()
    holder.join(2)


def test_a_failing_job_frees_its_slot():
    """job 丟例外：例外照丟，位置讓出來（Review Focus 3）。"""
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)

    def boom():
        raise RuntimeError("模型炸了")

    with pytest.raises(RuntimeError):
        queue.run("甲", boom, fallback=None)
    assert queue.run("乙", lambda: "好了", fallback=None) == "好了"


def test_position_while_running_and_after():
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    started, release, holder, result = _hold(queue, "甲")
    assert started.wait(2)
    assert queue.position("甲") == 0
    release.set()
    holder.join(2)
    assert result["value"] == "甲 的結果" and queue.position("甲") is None


# ── 計畫沒寫、實作時補的幾條 ───────────────────────────────────


def test_it_needs_at_least_one_slot():
    with pytest.raises(ValueError):
        llm_queue.LlmQueue(slots=0, bot_cap=1)


def test_two_slots_run_two_jobs_at_once_and_the_third_waits_for_one_to_finish():
    """「顯卡同時處理 slots 件」：兩個位子兩件一起跑，第三件排在後面、等其中一件放掉才輪到。"""
    queue = llm_queue.LlmQueue(slots=2, bot_cap=1)
    first, release_first, holder_a, _ = _hold(queue, "甲")
    second, release_second, holder_b, _ = _hold(queue, "乙")
    assert first.wait(2) and second.wait(2)
    assert queue.snapshot() == {"running": 2, "waiting": 0, "bots_waiting": 0}
    third, release_third, holder_c, result = _hold(queue, "丙")
    assert _wait_until(lambda: queue.snapshot()["waiting"] == 1)
    assert not third.is_set() and queue.position("丙") == 2
    release_first.set()
    assert third.wait(2) and queue.position("丙") == 0
    for release in (release_second, release_third):
        release.set()
    for t in (holder_a, holder_b, holder_c):
        t.join(2)
    assert result["value"] == "丙 的結果" and queue.snapshot() == {"running": 0, "waiting": 0, "bots_waiting": 0}


def test_a_waiter_that_dies_while_waiting_does_not_leave_its_ticket_behind():
    """排隊的時候這個執行緒出了例外（例如時鐘壞了）：票一定要拿掉，不然它永遠擋在後面的人前面，連它自己的下一件也永遠拿退路。"""
    broken = {"now": False}

    def clock():
        if broken["now"]:
            raise OSError("時鐘壞了")
        return time.monotonic()

    queue = llm_queue.LlmQueue(slots=1, bot_cap=1, clock=clock)
    started, release, holder, _ = _hold(queue, "甲")
    assert started.wait(2)
    broken["now"] = True
    with pytest.raises(OSError):
        queue.run("乙", lambda: "不該跑", fallback=None)
    broken["now"] = False
    assert queue.position("乙") is None and queue.snapshot()["waiting"] == 0
    release.set()
    holder.join(2)
    assert queue.run("乙", lambda: "好了", fallback=None) == "好了"  # 乙的下一件照常排得進去

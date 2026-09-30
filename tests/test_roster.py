from conftest import FixedRandom

from tianxia import roster, team


# ── 誰擁有誰 ──────────────────────────────────────────


def test_nobody_owns_anyone_at_the_start(state, world):
    assert roster.owned_by(world, "mate") is None
    assert roster.owned_companions(world, "沈浪") == []


def test_recruitable_here_lists_the_free_recruitable_characters_at_a_location(content, world):
    assert roster.recruitable_here(content, world, "town") == ["mate", "pupil", "scholar"]
    assert roster.recruitable_here(content, world, "lake") == ["friend", "hero"]
    assert roster.recruitable_here(content, world, "cave") == ["captain"]


def test_recruitable_here_excludes_someone_already_taken(content, world):
    world.try_recruit("mate", "李四")
    assert roster.recruitable_here(content, world, "town") == ["pupil", "scholar"]


# ── 成功率 ──────────────────────────────────────────────


def test_recruit_chance_rises_with_affinity_and_is_clamped(content, state):
    assert roster.recruit_chance(content, state, "mate") == 0.35
    state.player.affinities["mate"] = 100
    assert roster.recruit_chance(content, state, "mate") == 0.85
    state.player.affinities["mate"] = 100000
    assert roster.recruit_chance(content, state, "mate") == 0.95
    state.player.affinities["mate"] = -100000
    assert roster.recruit_chance(content, state, "mate") == 0.05


# ── 嘗試招募 ──────────────────────────────────────────


def test_attempt_recruit_succeeds_and_seeds_the_starting_skill(state, content, world):
    msgs = roster.attempt_recruit(state, content, world, "mate", FixedRandom(0.3))  # < 0.35
    assert msgs == ["【韓鐵】被你的誠意打動，願意追隨於你！"]
    assert state.player.team == ["mate"]
    assert state.player.stamina == 150 - content.config.recruit_stamina
    progress = world.get_companion("mate")
    assert progress.owner == "沈浪" and progress.wugong_id == "palm"


def test_attempt_recruit_can_fail_without_a_duel(state, content, world):
    msgs = roster.attempt_recruit(state, content, world, "mate", FixedRandom(0.4))  # 招募失敗、決鬥骰也沒過
    assert msgs == ["【韓鐵】婉拒了你這次的招攬，看來還需要多花心思。"]
    assert state.player.team == [] and roster.owned_by(world, "mate") is None


def test_attempt_recruit_failure_can_provoke_a_duel(state, content, world):
    msgs = roster.attempt_recruit(state, content, world, "mate", FixedRandom(0.36))  # 招募失敗、觸發決鬥
    assert msgs == ["【韓鐵】對你的貿然嘗試大為不悅，當場要求與你一較高下——你惹上了一場決鬥。"]
    assert roster.owned_by(world, "mate") is None


def test_attempt_recruit_someone_already_yours_is_a_no_op(state, content, world):
    roster.attempt_recruit(state, content, world, "mate", FixedRandom(0.3))
    stamina_before = state.player.stamina
    assert roster.attempt_recruit(state, content, world, "mate", FixedRandom(0.3)) == ["【韓鐵】已經是你的同伴了。"]
    assert state.player.stamina == stamina_before  # 不再扣體力


def test_attempt_recruit_someone_taken_by_another_player_is_a_miss(state, content, world):
    world.try_recruit("mate", "李四")
    stamina_before = state.player.stamina
    msgs = roster.attempt_recruit(state, content, world, "mate", FixedRandom(0.3))
    assert msgs == ["【韓鐵】已經被李四招攬走了，這次撲了個空。"]
    assert state.player.stamina == stamina_before


def test_attempt_recruit_does_not_overwrite_an_existing_companions_progress(state, content, world):
    world.update_companion("mate", lambda p: setattr(p, "level", 5))
    roster.attempt_recruit(state, content, world, "mate", FixedRandom(0.3))
    assert world.get_companion("mate").level == 5  # 進度沒被重置


# ── 劇情/福緣直接結識 ─────────────────────────────────────


def test_recruit_grants_directly_and_adds_to_the_team(state, content, world):
    msgs = roster.recruit(state, content, world, "hero")
    assert msgs == ["【俠女】加入了你的隊伍！"]
    assert state.player.team == ["hero"]
    assert world.get_companion("hero").owner == "沈浪" and world.get_companion("hero").wugong_id == "wave"


def test_recruit_someone_already_yours_gives_consolation_xinde(state, content, world):
    roster.recruit(state, content, world, "hero")
    msgs = roster.recruit(state, content, world, "hero")
    assert msgs == ["【俠女】早已在你身邊，這份緣分化為心得。", "心得 +30"]
    assert state.player.stats["xinde"] == 30


def test_recruit_someone_taken_by_another_player_gives_consolation_xinde(state, content, world):
    other_state = state.model_copy(deep=True)
    other_state.player.name = "李四"
    roster.recruit(other_state, content, world, "hero")
    msgs = roster.recruit(state, content, world, "hero")
    assert msgs == ["【俠女】已經是李四的同伴了，這份緣分化為心得。", "心得 +30"]
    assert state.player.stats["xinde"] == 30
    assert state.player.team == []  # 沒有真的收進隊伍


def test_recruit_loses_a_race_gives_consolation_xinde(state, content, world, monkeypatch):
    monkeypatch.setattr(world, "try_recruit", lambda *args: False)
    msgs = roster.recruit(state, content, world, "hero")
    assert msgs == ["【俠女】剛剛被別人招攬走了，這份緣分化為心得。", "心得 +30"]
    assert state.player.stats["xinde"] == 30


# ── 新立門戶福緣 ─────────────────────────────────────────


def test_fortune_due_from_day_two(state, content):
    assert not roster.fortune_due(state, content)
    state.world.time = 2 * 86400
    assert roster.fortune_due(state, content)
    state.player.fortune = True
    assert not roster.fortune_due(state, content)  # 已經發生過了


def test_fortune_overdue_after_day_seven(state, content):
    assert not roster.fortune_overdue(state, content)
    state.world.time = 8 * 86400
    assert roster.fortune_overdue(state, content)
    state.player.fortune = True
    assert not roster.fortune_overdue(state, content)


# ── 門下頁的文字 ──────────────────────────────────────────


def test_roster_lines_lists_the_player_then_owned_companions(state, content, world):
    assert roster.roster_lines(state, content, world) == [("本人　沈浪　第 1 級", "player")]
    roster.recruit(state, content, world, "hero")
    world.update_companion("hero", lambda p: setattr(p, "level", 4))
    assert roster.roster_lines(state, content, world) == [
        ("本人　沈浪　第 1 級", "player"),
        ("俠女　第 4 級　出戰", "hero"),
    ]


def test_roster_lines_marks_a_bench_companion(state, content, world):
    roster.recruit(state, content, world, "hero")
    team.remove_from_team(state, "hero")
    assert roster.roster_lines(state, content, world) == [
        ("本人　沈浪　第 1 級", "player"),
        ("俠女　第 1 級　在門下", "hero"),
    ]


def test_roster_lines_only_shows_this_players_companions(state, content, world):
    other_state = state.model_copy(deep=True)
    other_state.player.name = "李四"
    roster.recruit(other_state, content, world, "hero")
    assert roster.roster_lines(state, content, world) == [("本人　沈浪　第 1 級", "player")]

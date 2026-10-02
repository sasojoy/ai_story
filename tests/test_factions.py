from tianxia.factions import rank4_seats
from tianxia.models import Config


def test_rank_four_seats_follow_the_server_size():
    assert rank4_seats(Config(server_max_players=3000)) == 24
    assert rank4_seats(Config(server_max_players=1000)) == 8


def test_a_small_server_still_has_one_rank_four_seat_per_faction():
    assert rank4_seats(Config(server_max_players=30)) == 1
    assert rank4_seats(Config(server_max_players=5)) == 1

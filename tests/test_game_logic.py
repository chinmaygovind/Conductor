"""
Unit tests for game_logic.py.

All tests operate directly on state dicts — no Flask or database needed.
"""

import pytest
import random
import game_logic as logic
from game_data_na import CARD_COUNTS, ROUTE_BY_ID, DESTINATION_TICKETS, ROUTE_SCORING


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(player_specs, map_variant="usa"):
    return logic.init_game_state(player_specs, map_variant)


def advance_to_main(state, player_specs):
    """Fast-forward through initial_tickets phase: keep first 2 pending for each player."""
    for p in player_specs:
        pid = str(p["id"])
        ps = state["player_states"][pid]
        pending = ps.get("pending_tickets", [])
        if pending:
            logic.keep_initial_tickets(state, pid, pending[:2])


def give_hand(state, pid, cards: dict):
    """Set a player's hand to exactly `cards`."""
    state["player_states"][str(pid)]["hand"] = dict(cards)


def set_current(state, pid):
    state["current_player_id"] = str(pid)
    state["draw_step"] = 0


# ---------------------------------------------------------------------------
# Deck / initialization
# ---------------------------------------------------------------------------

def test_build_deck_total_cards():
    deck = logic.build_deck()
    assert len(deck) == sum(CARD_COUNTS.values())


def test_build_deck_color_counts():
    deck = logic.build_deck()
    for color, count in CARD_COUNTS.items():
        assert deck.count(color) == count


def test_init_game_state_phase(two_player_specs):
    state = make_state(two_player_specs)
    assert state["phase"] == "initial_tickets"


def test_init_game_state_player_hands(two_player_specs):
    state = make_state(two_player_specs)
    for p in two_player_specs:
        ps = state["player_states"][str(p["id"])]
        assert sum(ps["hand"].values()) == 4


def test_init_game_state_trains(two_player_specs):
    state = make_state(two_player_specs)
    for p in two_player_specs:
        assert state["player_states"][str(p["id"])]["trains"] == 45


def test_init_game_state_five_face_up(two_player_specs):
    state = make_state(two_player_specs)
    assert len(state["face_up"]) == 5
    assert all(c is not None for c in state["face_up"])


def test_init_game_state_no_three_locos_face_up(two_player_specs):
    random.seed(42)
    for _ in range(20):
        state = make_state(two_player_specs)
        loco_count = state["face_up"].count("locomotive")
        assert loco_count < 3, f"Found {loco_count} locos in face-up row"


def test_init_game_state_europe_has_stations(two_player_specs):
    state = make_state(two_player_specs, "europe")
    for p in two_player_specs:
        ps = state["player_states"][str(p["id"])]
        assert ps["station_count"] == 3


def test_init_game_state_europe_pending_tickets(two_player_specs):
    state = make_state(two_player_specs, "europe")
    for p in two_player_specs:
        ps = state["player_states"][str(p["id"])]
        # 1 long + 3 short = 4 pending
        assert len(ps["pending_tickets"]) == 4


def test_init_game_state_usa_pending_tickets(two_player_specs):
    state = make_state(two_player_specs)
    for p in two_player_specs:
        ps = state["player_states"][str(p["id"])]
        assert len(ps["pending_tickets"]) == 3


# ---------------------------------------------------------------------------
# Initial ticket selection
# ---------------------------------------------------------------------------

def test_keep_initial_tickets_advances_to_main(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    assert state["phase"] == "main"


def test_keep_initial_tickets_must_keep_two(two_player_specs):
    state = make_state(two_player_specs)
    pid = "1"
    pending = state["player_states"][pid]["pending_tickets"]
    result = logic.keep_initial_tickets(state, pid, pending[:1])
    assert not result["ok"]
    assert "2" in result["error"]


def test_keep_initial_tickets_invalid_ids(two_player_specs):
    state = make_state(two_player_specs)
    result = logic.keep_initial_tickets(state, "1", [9999, 9998])
    assert not result["ok"]


def test_keep_initial_tickets_returned_go_back_to_deck(two_player_specs):
    state = make_state(two_player_specs)
    pid = "1"
    pending = state["player_states"][pid]["pending_tickets"]
    keep = pending[:2]
    returned = pending[2:]
    deck_before = len(state["dest_deck"])
    logic.keep_initial_tickets(state, pid, keep)
    if returned:
        assert len(state["dest_deck"]) == deck_before + len(returned)


def test_keep_initial_tickets_kept_stored_on_player(two_player_specs):
    state = make_state(two_player_specs)
    pid = "1"
    pending = state["player_states"][pid]["pending_tickets"]
    keep = pending[:2]
    logic.keep_initial_tickets(state, pid, keep)
    assert set(keep).issubset(set(state["player_states"][pid]["tickets"]))


# ---------------------------------------------------------------------------
# Draw face-up cards
# ---------------------------------------------------------------------------

def test_draw_face_up_adds_card_to_hand(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    hand_before = sum(state["player_states"][pid]["hand"].values())
    card = state["face_up"][0]
    result = logic.draw_face_up(state, pid, 0)
    assert result["ok"]
    assert result["card"] == card
    assert sum(state["player_states"][pid]["hand"].values()) == hand_before + 1


def test_draw_face_up_wrong_player(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    # Get the non-current player
    pid = next(p for p in state["turn_order"] if p != state["current_player_id"])
    result = logic.draw_face_up(state, pid, 0)
    assert not result["ok"]


def test_draw_face_up_two_draws_end_turn(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    # Force no locos in face_up so we can draw twice
    state["face_up"] = ["red", "blue", "green", "orange", "white"]
    logic.draw_face_up(state, pid, 0)
    logic.draw_face_up(state, pid, 1)
    assert state["current_player_id"] != pid


def test_draw_face_up_locomotive_counts_as_both(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["face_up"][0] = "locomotive"
    result = logic.draw_face_up(state, pid, 0)
    assert result["ok"]
    # Turn should have advanced (draw_step back to 0 and current player changed)
    assert state["current_player_id"] != pid


def test_draw_face_up_no_loco_as_second_draw(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["face_up"] = ["red", "locomotive", "green", "orange", "white"]
    logic.draw_face_up(state, pid, 0)  # first draw (red)
    result = logic.draw_face_up(state, pid, 1)  # try loco as second
    assert not result["ok"]
    assert "locomotive" in result["error"].lower() or "second" in result["error"].lower()


def test_draw_face_up_replaces_drawn_card(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["deck"] = ["black"] + state["deck"]
    logic.draw_face_up(state, pid, 0)
    assert len(state["face_up"]) == 5


# ---------------------------------------------------------------------------
# 3-locomotive sweep (sweep_count drives the client's slide-away animation)
# ---------------------------------------------------------------------------

def test_maybe_replace_three_locos_reports_sweep():
    # A realistic deck so the reshuffle can escape the 3-loco state.
    deck = ["red", "blue", "green", "yellow", "black", "white"] * 4
    face_up, swept = logic._maybe_replace_three_locos(
        ["locomotive", "locomotive", "locomotive", "red", "blue"], deck)
    assert swept is True
    assert face_up.count("locomotive") < 3


def test_maybe_replace_three_locos_no_sweep_when_under_three():
    deck = ["red", "blue", "green"] * 4
    face_up, swept = logic._maybe_replace_three_locos(
        ["red", "blue", "green", "yellow", "black"], deck)
    assert swept is False
    assert face_up == ["red", "blue", "green", "yellow", "black"]


def test_init_and_public_state_expose_sweep_count(two_player_specs):
    state = make_state(two_player_specs)
    assert state["sweep_count"] == 0
    pub = logic.get_public_state(state, "1")
    assert pub["sweep_count"] == 0


def test_draw_face_up_bumps_sweep_count_on_three_locos(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    set_current(state, pid)
    # Two locos face-up already, and the next card drawn from the deck is a loco,
    # so refilling the emptied slot creates a 3rd loco -> full wipe.
    state["face_up"] = ["red", "locomotive", "locomotive", "blue", "green"]
    state["deck"] = ["red", "blue", "green", "yellow", "black", "white"] * 4 + ["locomotive"]
    before = state["sweep_count"]
    result = logic.draw_face_up(state, pid, 0)  # take the red card
    assert result["ok"]
    assert state["sweep_count"] == before + 1
    assert state["face_up"].count("locomotive") < 3


def test_draw_face_up_no_sweep_bump_on_normal_draw(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    set_current(state, pid)
    state["face_up"] = ["red", "blue", "green", "yellow", "black"]
    state["deck"] = ["white"] * 6
    before = state["sweep_count"]
    result = logic.draw_face_up(state, pid, 0)
    assert result["ok"]
    assert state["sweep_count"] == before


# ---------------------------------------------------------------------------
# Draw blind
# ---------------------------------------------------------------------------

def test_draw_blind_adds_to_hand(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    hand_before = sum(state["player_states"][pid]["hand"].values())
    result = logic.draw_blind(state, pid)
    assert result["ok"]
    assert sum(state["player_states"][pid]["hand"].values()) == hand_before + 1


def test_draw_blind_twice_ends_turn(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    logic.draw_blind(state, pid)
    logic.draw_blind(state, pid)
    assert state["current_player_id"] != pid


def test_draw_blind_reshuffles_discard(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["deck"] = []
    state["discard"] = ["red", "blue", "green"]
    result = logic.draw_blind(state, pid)
    assert result["ok"]


def test_draw_blind_no_cards_error(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["deck"] = []
    state["discard"] = []
    result = logic.draw_blind(state, pid)
    assert not result["ok"]


def test_draw_blind_wrong_player(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = next(p for p in state["turn_order"] if p != state["current_player_id"])
    result = logic.draw_blind(state, pid)
    assert not result["ok"]


# ---------------------------------------------------------------------------
# Claim route
# ---------------------------------------------------------------------------

def test_claim_route_basic(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    # Route 1: Vancouver-Seattle, length 1, gray — give player 1 red card
    give_hand(state, pid, {"red": 5})
    result = logic.claim_route(state, pid, 1, {"red": 1})
    assert result["ok"]
    assert result["points"] == ROUTE_SCORING[1]
    assert state["claimed_routes"]["1"] == pid
    assert state["player_states"][pid]["trains"] == 44


def test_claim_route_not_your_turn(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = next(p for p in state["turn_order"] if p != state["current_player_id"])
    give_hand(state, pid, {"red": 5})
    result = logic.claim_route(state, pid, 1, {"red": 1})
    assert not result["ok"]


def test_claim_route_already_claimed(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"red": 10})
    logic.claim_route(state, pid, 1, {"red": 1})
    # Advance turn back to pid somehow — just force it
    pid2 = state["current_player_id"]
    give_hand(state, pid2, {"red": 10})
    result = logic.claim_route(state, pid2, 1, {"red": 1})
    assert not result["ok"]


def test_claim_route_insufficient_cards(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"red": 0})
    result = logic.claim_route(state, pid, 6, {"yellow": 1})  # Route 6 is length 6
    assert not result["ok"]


def test_claim_route_wrong_card_count(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"yellow": 10})
    # Route 6 is Seattle-Helena, length 6, yellow — only give 5
    result = logic.claim_route(state, pid, 6, {"yellow": 5})
    assert not result["ok"]
    assert "exactly 6" in result["error"]


def test_claim_route_colored_wrong_color(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"red": 10})
    # Route 6 is yellow — trying to use red
    result = logic.claim_route(state, pid, 6, {"red": 6})
    assert not result["ok"]
    assert "yellow" in result["error"]


def test_claim_route_gray_any_single_color(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"black": 5})
    # Route 1 is gray length 1 — any color works
    result = logic.claim_route(state, pid, 1, {"black": 1})
    assert result["ok"]


def test_claim_route_gray_mixed_colors_fails(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"red": 1, "blue": 1})
    # Route with length 2 (route 2 is also VAN-SEA length 1, so use a length-2 route)
    # Route 14: LA-Las Vegas, length 2, gray
    result = logic.claim_route(state, pid, 14, {"red": 1, "blue": 1})
    assert not result["ok"]


def test_claim_route_with_locomotives(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"yellow": 4, "locomotive": 2})
    # Route 6: Seattle-Helena, length 6, yellow — use 4 yellow + 2 loco
    result = logic.claim_route(state, pid, 6, {"yellow": 4, "locomotive": 2})
    assert result["ok"]


def test_claim_route_insufficient_trains(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"yellow": 10})
    state["player_states"][pid]["trains"] = 1
    result = logic.claim_route(state, pid, 6, {"yellow": 6})
    assert not result["ok"]
    assert "trains" in result["error"]


def test_claim_route_scoring(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"yellow": 10})
    # Route 6: length 6 = 15 points
    result = logic.claim_route(state, pid, 6, {"yellow": 6})
    assert result["ok"]
    assert result["points"] == 15
    assert state["player_states"][pid]["route_score"] == 15


def test_claim_route_advances_turn(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"red": 5})
    logic.claim_route(state, pid, 1, {"red": 1})
    assert state["current_player_id"] != pid


def test_claim_double_route_blocked_2_player(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid1 = state["current_player_id"]
    pid2 = next(p for p in state["turn_order"] if p != pid1)

    # Claim route 1 (VAN-SEA side A) as player 1
    give_hand(state, pid1, {"red": 5})
    logic.claim_route(state, pid1, 1, {"red": 1})

    # Try to claim route 2 (VAN-SEA side B) as player 2
    give_hand(state, pid2, {"blue": 5})
    result = logic.claim_route(state, pid2, 2, {"blue": 1})
    assert not result["ok"]
    assert "double" in result["error"].lower() or "player" in result["error"].lower()


def test_claim_double_route_allowed_4_player(four_player_specs):
    state = make_state(four_player_specs)
    advance_to_main(state, four_player_specs)

    # Claim route 1 (VAN-SEA side A) as player 1
    pid1 = state["current_player_id"]
    give_hand(state, pid1, {"red": 5})
    logic.claim_route(state, pid1, 1, {"red": 1})

    # Advance to next player and claim other side
    pid2 = state["current_player_id"]
    give_hand(state, pid2, {"blue": 5})
    result = logic.claim_route(state, pid2, 2, {"blue": 1})
    assert result["ok"]


def test_claim_triggers_final_round(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    # Set trains to exactly 2 (trigger ≤2 condition)
    state["player_states"][pid]["trains"] = 3
    give_hand(state, pid, {"red": 5})
    # Route 1 costs 1 train → leaves 2 trains = triggers final round
    logic.claim_route(state, pid, 1, {"red": 1})
    assert state["phase"] == "final_round"


def test_claim_not_in_initial_phase(two_player_specs):
    state = make_state(two_player_specs)
    # Still in initial_tickets phase
    pid = state["current_player_id"]
    give_hand(state, pid, {"red": 5})
    result = logic.claim_route(state, pid, 1, {"red": 1})
    assert not result["ok"]


# ---------------------------------------------------------------------------
# Destinations mid-game
# ---------------------------------------------------------------------------

def test_draw_destination_tickets(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    deck_before = len(state["dest_deck"])
    result = logic.draw_destination_tickets(state, pid)
    assert result["ok"]
    drawn = len(state["player_states"][pid]["pending_tickets"])
    assert drawn == min(3, deck_before)


def test_draw_destination_tickets_empty_deck(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["dest_deck"] = []
    result = logic.draw_destination_tickets(state, pid)
    assert not result["ok"]


def test_keep_drawn_tickets_basic(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    logic.draw_destination_tickets(state, pid)
    pending = state["player_states"][pid]["pending_tickets"]
    keep = pending[:1]
    result = logic.keep_drawn_tickets(state, pid, keep)
    assert result["ok"]
    assert keep[0] in state["player_states"][pid]["tickets"]


def test_keep_drawn_tickets_must_keep_one(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    logic.draw_destination_tickets(state, pid)
    result = logic.keep_drawn_tickets(state, pid, [])
    assert not result["ok"]


def test_keep_drawn_tickets_returns_discards_to_deck(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    logic.draw_destination_tickets(state, pid)
    pending = state["player_states"][pid]["pending_tickets"]
    returned = pending[1:]
    deck_before = len(state["dest_deck"])
    logic.keep_drawn_tickets(state, pid, pending[:1])
    assert len(state["dest_deck"]) == deck_before + len(returned)


# ---------------------------------------------------------------------------
# Turn management / resign
# ---------------------------------------------------------------------------

def test_resign_player_not_current_does_not_advance(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    current = state["current_player_id"]
    other = next(p for p in state["turn_order"] if p != current)
    result = logic.resign_player(state, other)
    assert result["ok"]
    # Current player should still be the same
    assert state["current_player_id"] == current


def test_resign_current_player_advances_turn(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    logic.resign_player(state, pid)
    # In a 2-player game resigning ends the game immediately (only 1 active player).
    # In 3+ players it would advance the turn instead.
    assert state["phase"] == "ended" or state["current_player_id"] != pid


def test_resign_all_players_ends_game(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    for pid in state["turn_order"]:
        logic.resign_player(state, pid)
    assert state["phase"] == "ended"


def test_resign_during_initial_phase_blocked(two_player_specs):
    state = make_state(two_player_specs)
    result = logic.resign_player(state, "1")
    assert not result["ok"]


# ---------------------------------------------------------------------------
# Final round
# ---------------------------------------------------------------------------

def test_final_round_order(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    # Force trigger
    state["player_states"][pid]["trains"] = 1
    give_hand(state, pid, {"red": 5})
    logic.claim_route(state, pid, 1, {"red": 1})
    assert state["phase"] == "final_round"
    # The other player should go first in final round, then trigger player
    other = next(p for p in state["turn_order"] if p != pid)
    assert state["current_player_id"] == other
    assert pid in state["final_round_players_left"]


def test_final_round_ends_after_all_play(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["player_states"][pid]["trains"] = 1
    give_hand(state, pid, {"red": 5})
    logic.claim_route(state, pid, 1, {"red": 1})
    assert state["phase"] == "final_round"
    # Both players draw to finish their turns
    for _ in range(10):
        if state["phase"] == "ended":
            break
        cur = state["current_player_id"]
        logic.draw_blind(state, cur)
        if state.get("draw_step", 0) == 1:
            logic.draw_blind(state, cur)
    assert state["phase"] == "ended"


# ---------------------------------------------------------------------------
# End game scoring
# ---------------------------------------------------------------------------

def test_tiebreak_uses_completed_tickets_not_kept(monkeypatch, two_player_specs):
    """On a score tie, the player with more COMPLETED tickets wins (official rule),
    not the one who merely KEPT more. Regression for the g173 fix."""
    import collections
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    p1, p2 = state["turn_order"][0], state["turn_order"][1]

    # Neutralise longest path so it can't decide the tie (both get the bonus).
    monkeypatch.setattr(logic, "longest_path", lambda s, pid: 0)

    def path_routes(c1, c2):
        adj = collections.defaultdict(list)
        for rid, r in ROUTE_BY_ID.items():
            adj[r["city1"]].append((r["city2"], rid))
            adj[r["city2"]].append((r["city1"], rid))
        q = collections.deque([(c1, [])]); seen = {c1}
        while q:
            city, pth = q.popleft()
            if city == c2:
                return pth
            for nb, rid in adj[city]:
                if nb not in seen:
                    seen.add(nb); q.append((nb, pth + [rid]))
        return []

    tk, t2, t3 = DESTINATION_TICKETS[0], DESTINATION_TICKETS[1], DESTINATION_TICKETS[2]

    # P1: keeps ONE ticket and completes it (claims its connecting path).
    for rid in path_routes(tk["city1"], tk["city2"]):
        state["claimed_routes"][str(rid)] = p1
    state["player_states"][p1]["tickets"] = [tk["id"]]
    state["player_states"][p1]["route_score"] = 0

    # P2: keeps TWO tickets, completes NEITHER (no routes), but route_score is set
    # so the totals tie exactly:  P1 = tk.pts ;  P2 = route_score - t2 - t3 = tk.pts.
    state["player_states"][p2]["tickets"] = [t2["id"], t3["id"]]
    state["player_states"][p2]["route_score"] = tk["points"] + t2["points"] + t3["points"]

    state["phase"] = "final_round"
    state["final_round_players_left"] = []
    logic._end_game(state)

    s1, s2 = state["scores"][p1], state["scores"][p2]
    assert s1["total"] == s2["total"], "test setup should tie the totals"
    # OLD logic (most tickets KEPT) would pick p2; NEW logic (most COMPLETED) picks p1.
    assert state["winner_id"] == p1


def test_end_game_ticket_completed_adds_points(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)

    # Force game to end immediately
    state["phase"] = "final_round"
    state["final_round_players_left"] = []
    logic._end_game(state)

    assert state["phase"] == "ended"
    assert state["winner_id"] is not None
    for pid, sc in state["scores"].items():
        assert "total" in sc
        assert "tickets" in sc


def test_end_game_longest_path_bonus(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    # Give player 1 some routes
    state["claimed_routes"]["1"] = pid   # VAN-SEA len 1
    state["claimed_routes"]["4"] = pid   # SEA-POR len 1
    state["player_states"][pid]["trains"] = 43
    state["player_states"][pid]["route_score"] = 2

    state["phase"] = "final_round"
    state["final_round_players_left"] = []
    logic._end_game(state)

    sc = state["scores"][pid]
    # The player with longer routes should get +10
    bonus_players = [p for p, s in state["scores"].items() if s.get("longest_path_bonus")]
    assert len(bonus_players) >= 1


def test_end_game_incomplete_ticket_deducts_points(two_player_specs):
    from game_data_na import TICKET_BY_ID
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    # Add a ticket but don't claim any routes → incomplete → negative delta
    tid = list(TICKET_BY_ID.keys())[0]
    ticket = TICKET_BY_ID[tid]
    state["player_states"][pid]["tickets"] = [tid]
    state["phase"] = "final_round"
    state["final_round_players_left"] = []
    logic._end_game(state)
    ticket_results = state["scores"][pid]["tickets"]
    assert any(t["delta"] < 0 for t in ticket_results)


# ---------------------------------------------------------------------------
# Path / graph algorithms
# ---------------------------------------------------------------------------

def test_is_path_connected_simple(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["claimed_routes"]["1"] = pid   # Vancouver-Seattle
    state["claimed_routes"]["4"] = pid   # Seattle-Portland
    assert logic.is_path_connected(state, pid, "Vancouver", "Portland")


def test_is_path_connected_not_connected(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    assert not logic.is_path_connected(state, pid, "Vancouver", "Miami")


def test_is_path_connected_no_routes(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    assert not logic.is_path_connected(state, pid, "Vancouver", "Seattle")


def test_longest_path_no_routes(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    assert logic.longest_path(state, pid) == 0


def test_longest_path_single_route(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["claimed_routes"]["6"] = pid  # Seattle-Helena length 6
    assert logic.longest_path(state, pid) == 6


def test_longest_path_chain(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["claimed_routes"]["1"] = pid   # Vancouver-Seattle len 1
    state["claimed_routes"]["4"] = pid   # Seattle-Portland len 1
    assert logic.longest_path(state, pid) == 2


def test_longest_path_branching(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    # Three routes from Seattle: VAN(1), POR(1), HEL(6)
    state["claimed_routes"]["1"] = pid  # VAN-SEA len 1
    state["claimed_routes"]["4"] = pid  # SEA-POR len 1
    state["claimed_routes"]["6"] = pid  # SEA-HEL len 6
    # Longest trail (no edge reuse): HEL→SEA→VAN = 6+1 = 7
    # (Can't combine both arms from Seattle because edges can't be reused)
    lp = logic.longest_path(state, pid)
    assert lp == 7


# ---------------------------------------------------------------------------
# Europe-specific: tunnels
# ---------------------------------------------------------------------------

def test_claim_tunnel_returns_pending(two_player_specs):
    from game_data_europe import EUROPE_ROUTE_BY_ID
    state = make_state(two_player_specs, "europe")
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    # Find a tunnel route
    tunnel_routes = [r for r in EUROPE_ROUTE_BY_ID.values() if r.get("tunnel")]
    assert tunnel_routes, "No tunnel routes found in Europe data"
    route = tunnel_routes[0]
    color = route["color"] if route["color"] != "gray" else "red"
    give_hand(state, pid, {color: 10, "locomotive": 10})
    cards = {color: route["length"]} if color != "gray" else {"red": route["length"]}
    result = logic.claim_route(state, pid, route["id"], cards)
    if result.get("ok") and result.get("tunnel_pending"):
        assert state.get("pending_tunnel") is not None


def test_resolve_tunnel_abort_returns_cards(two_player_specs):
    from game_data_europe import EUROPE_ROUTE_BY_ID
    state = make_state(two_player_specs, "europe")
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    # Find a valid Europe tunnel route to use as the route_id
    tunnel_routes = [r for r in EUROPE_ROUTE_BY_ID.values() if r.get("tunnel")]
    assert tunnel_routes, "No tunnel routes in Europe data"
    tunnel_route_id = tunnel_routes[0]["id"]
    state["pending_tunnel"] = {
        "player_id": pid,
        "route_id": tunnel_route_id,
        "cards_offered": {"red": 3},
        "extra_cost": 1,
        "extra_color": "red",
        "revealed": ["red"],
    }
    state["player_states"][pid]["hand"] = {}
    # Abort — cards_offered should be returned to hand
    result = logic.resolve_tunnel(state, pid, proceed=False)
    assert result["ok"]
    assert not result["claimed"]
    assert state["player_states"][pid]["hand"].get("red", 0) == 3
    assert state["pending_tunnel"] is None


def test_resolve_tunnel_free_claims_route(two_player_specs):
    from game_data_europe import EUROPE_ROUTE_BY_ID
    state = make_state(two_player_specs, "europe")
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    tunnel_routes = [r for r in EUROPE_ROUTE_BY_ID.values() if r.get("tunnel")]
    route = tunnel_routes[0]
    state["pending_tunnel"] = {
        "player_id": pid,
        "route_id": route["id"],
        "cards_offered": {"red": route["length"]},
        "extra_cost": 0,
        "extra_color": "red",
        "revealed": [],
    }
    state["player_states"][pid]["hand"] = {}
    result = logic.resolve_tunnel(state, pid, proceed=True)
    assert result["ok"]
    assert state["claimed_routes"].get(str(route["id"])) == pid


# ---------------------------------------------------------------------------
# Europe-specific: stations
# ---------------------------------------------------------------------------

def test_place_station_basic(two_player_specs):
    state = make_state(two_player_specs, "europe")
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"red": 5})
    result = logic.place_station(state, pid, "London", {"red": 1})
    assert result["ok"]
    assert "London" in state["stations"].get(pid, [])


def test_place_station_cost_increases(two_player_specs):
    state = make_state(two_player_specs, "europe")
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    # First station: 1 card
    give_hand(state, pid, {"red": 10})
    logic.place_station(state, pid, "London", {"red": 1})
    # Force turn back
    set_current(state, pid)
    # Second station: 2 cards
    result = logic.place_station(state, pid, "Paris", {"red": 2})
    assert result["ok"]
    set_current(state, pid)
    # Third station: 3 cards
    result = logic.place_station(state, pid, "Berlin", {"red": 3})
    assert result["ok"]


def test_place_station_wrong_card_count(two_player_specs):
    state = make_state(two_player_specs, "europe")
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"red": 10})
    result = logic.place_station(state, pid, "London", {"red": 2})  # should cost 1
    assert not result["ok"]


def test_place_station_usa_map_blocked(two_player_specs):
    state = make_state(two_player_specs, "usa")
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    give_hand(state, pid, {"red": 5})
    result = logic.place_station(state, pid, "Seattle", {"red": 1})
    assert not result["ok"]


# ---------------------------------------------------------------------------
# get_public_state
# ---------------------------------------------------------------------------

def test_public_state_hides_other_hand(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    other = next(p for p in state["turn_order"] if p != pid)
    pub = logic.get_public_state(state, pid)
    assert pub["players"][pid]["hand"]        # viewer sees own hand
    assert pub["players"][other]["hand"] == {}  # other player's hand hidden


def test_public_state_shows_own_tickets(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    state["player_states"][pid]["tickets"] = [1, 2]
    pub = logic.get_public_state(state, pid)
    assert pub["players"][pid]["tickets"] == [1, 2]


def test_public_state_hides_other_tickets(two_player_specs):
    state = make_state(two_player_specs)
    advance_to_main(state, two_player_specs)
    pid = state["current_player_id"]
    other = next(p for p in state["turn_order"] if p != pid)
    state["player_states"][other]["tickets"] = [1, 2]
    pub = logic.get_public_state(state, pid)
    assert pub["players"][other]["tickets"] == []

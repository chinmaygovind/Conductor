"""
Full game logic for Conductor (North America + Europe).
All state lives in a single dict that is serialized to the DB as JSON.
"""

import random
from collections import defaultdict, deque
from game_data_na import (
    ROUTES, ROUTE_BY_ID, DESTINATION_TICKETS, TICKET_BY_ID,
    CARD_COUNTS, ROUTE_SCORING, DOUBLE_ROUTE_GROUPS, PLAYER_COLORS,
)
from game_data_europe import (
    EUROPE_ROUTES, EUROPE_ROUTE_BY_ID, EUROPE_DESTINATION_TICKETS, EUROPE_TICKET_BY_ID,
    EUROPE_ROUTE_SCORING, EUROPE_DOUBLE_ROUTE_GROUPS,
)


def _map_data(map_variant: str):
    """Return (ROUTE_BY_ID, TICKET_BY_ID, ROUTE_SCORING, DOUBLE_ROUTE_GROUPS) for the given map."""
    if map_variant == "europe":
        return EUROPE_ROUTE_BY_ID, EUROPE_TICKET_BY_ID, EUROPE_ROUTE_SCORING, EUROPE_DOUBLE_ROUTE_GROUPS
    return ROUTE_BY_ID, TICKET_BY_ID, ROUTE_SCORING, DOUBLE_ROUTE_GROUPS


# ---------------------------------------------------------------------------
# State initialization
# ---------------------------------------------------------------------------

def build_deck() -> list[str]:
    deck = []
    for color, count in CARD_COUNTS.items():
        deck.extend([color] * count)
    random.shuffle(deck)
    return deck


def init_game_state(players: list[dict], map_variant: str = "usa") -> dict:
    """
    players: list of {id, name, color, turn_order}
    map_variant: "usa" or "europe"
    Returns the full game state dict.
    """
    deck = build_deck()
    face_up: list[str] = []
    for _ in range(5):
        face_up.append(deck.pop())
    face_up, _ = _maybe_replace_three_locos(face_up, deck)

    is_europe = (map_variant == "europe")

    if is_europe:
        short_tickets = [t["id"] for t in EUROPE_DESTINATION_TICKETS if not t["long"]]
        long_tickets  = [t["id"] for t in EUROPE_DESTINATION_TICKETS if t["long"]]
        random.shuffle(short_tickets)
        random.shuffle(long_tickets)
        dest_deck = short_tickets  # only short tickets drawn mid-game
    else:
        dest_deck = list(range(1, len(DESTINATION_TICKETS) + 1))
        random.shuffle(dest_deck)

    player_states: dict[str, dict] = {}
    for p in players:
        hand: dict[str, int] = {}
        for _ in range(4):
            c = deck.pop()
            hand[c] = hand.get(c, 0) + 1
        ps: dict = {
            "name": p["name"],
            "color": p["color"],
            "turn_order": p["turn_order"],
            "hand": hand,
            "tickets": [],
            "trains": 45,
            "route_score": 0,
            "pending_tickets": [],
        }
        if is_europe:
            ps["station_count"] = 3
        player_states[str(p["id"])] = ps

    turn_order = sorted(players, key=lambda x: x["turn_order"])

    # Deal initial destinations
    if is_europe:
        # Each player gets 1 long + 3 short as pending choices; must keep ≥2
        for p in players:
            pid = str(p["id"])
            pending = []
            if long_tickets:
                long_id = long_tickets.pop()
                player_states[pid]["long_ticket_id"] = long_id
                pending.append(long_id)
            pending += [dest_deck.pop() for _ in range(min(3, len(dest_deck)))]
            player_states[pid]["pending_tickets"] = pending
    else:
        for p in players:
            pid = str(p["id"])
            drawn = [dest_deck.pop() for _ in range(3)]
            player_states[pid]["pending_tickets"] = drawn

    current_player_id = str(turn_order[0]["id"])

    state = {
        "map": map_variant,
        "deck": deck,
        "face_up": face_up,
        "discard": [],
        "dest_deck": dest_deck,
        "claimed_routes": {},
        "player_states": player_states,
        "current_player_id": current_player_id,
        "turn_order": [str(p["id"]) for p in turn_order],
        "phase": "initial_tickets",
        "final_round_players_left": [],
        "draw_step": 0,
        "action_log": [],
        "winner_id": None,
        "scores": {},
        "final_round_triggered_by": None,
        "turns_taken": 0,
        "sweep_count": 0,   # bumped each 3-locomotive face-up wipe (drives client animation)
    }
    if is_europe:
        state["stations"] = {}       # {player_id: [city, ...]}
        state["pending_tunnel"] = None
    return state


def _maybe_replace_three_locos(face_up: list[str], deck: list[str]) -> tuple[list[str], bool]:
    """If 3+ locomotives are face-up, discard all five and draw five new ones.

    Returns (face_up, did_sweep) — did_sweep is True if at least one full
    replacement happened, so callers can signal the client to play the sweep
    animation.

    Safety cap: if every available card is a locomotive (e.g. bots hoarded all
    non-loco cards), reshuffling will never produce a valid hand. After a few
    attempts we accept the all-loco state rather than spinning forever.
    """
    did_sweep = False
    for _ in range(30):
        if face_up.count("locomotive") < 3:
            break
        did_sweep = True
        deck.extend(face_up)
        random.shuffle(deck)
        n = min(5, len(deck))
        face_up = [deck.pop() for _ in range(n)]
    return face_up, did_sweep


def _ensure_deck(state: dict):
    """Reshuffle discard into deck if deck is empty."""
    if not state["deck"] and state["discard"]:
        state["deck"] = state["discard"][:]
        random.shuffle(state["deck"])
        state["discard"] = []


# ---------------------------------------------------------------------------
# Initial ticket selection
# ---------------------------------------------------------------------------

def keep_initial_tickets(state: dict, player_id: str, keep_ids: list[int]) -> dict:
    ps = state["player_states"][player_id]
    pending = ps["pending_tickets"]
    is_europe = state.get("map") == "europe"
    min_keep = 2
    if len(keep_ids) < min_keep:
        return {"ok": False, "error": f"Must keep at least {min_keep} destination{'s' if min_keep > 1 else ''}."}
    if not all(k in pending for k in keep_ids):
        return {"ok": False, "error": "Invalid ticket selection."}

    ps["tickets"].extend(keep_ids)
    returned = [t for t in pending if t not in keep_ids]
    state["dest_deck"] = returned + state["dest_deck"]
    ps["pending_tickets"] = []
    # If the long ticket was discarded, clear its marker
    if ps.get("long_ticket_id") and ps["long_ticket_id"] not in keep_ids:
        ps["long_ticket_id"] = None

    _advance_initial_tickets(state)
    return {"ok": True}


def _advance_initial_tickets(state: dict):
    """Move to next player for initial ticket selection; when all done, start main game."""
    all_done = all(
        len(ps["pending_tickets"]) == 0
        for ps in state["player_states"].values()
    )
    if all_done:
        state["phase"] = "main"
        state["draw_step"] = 0
        state["current_player_id"] = state["turn_order"][0]
    else:
        # Advance to next player who still has pending tickets
        order = state["turn_order"]
        cur = state["current_player_id"]
        idx = order.index(cur)
        for i in range(1, len(order) + 1):
            nxt = order[(idx + i) % len(order)]
            if state["player_states"][nxt]["pending_tickets"]:
                state["current_player_id"] = nxt
                return


# ---------------------------------------------------------------------------
# Draw Train Car Cards
# ---------------------------------------------------------------------------

def draw_face_up(state: dict, player_id: str, slot: int) -> dict:
    """Draw a specific face-up card (slot 0-4). Returns error dict on failure."""
    if state["phase"] not in ("main", "final_round"):
        return {"ok": False, "error": "Not main game phase."}
    if state["current_player_id"] != player_id:
        return {"ok": False, "error": "Not your turn."}
    if state.get("pending_tunnel"):
        return {"ok": False, "error": "Resolve the pending tunnel first."}
    if state["player_states"][player_id].get("pending_tickets"):
        return {"ok": False, "error": "Keep your destinations first."}

    card = state["face_up"][slot]
    if card == "locomotive" and state["draw_step"] == 1:
        return {"ok": False, "error": "Cannot take a locomotive as the second card."}

    ps = state["player_states"][player_id]
    ps["hand"][card] = ps["hand"].get(card, 0) + 1
    _log(state, f"{ps['name']} drew face-up {card}.")

    # Replace drawn card
    _ensure_deck(state)
    if state["deck"]:
        state["face_up"][slot] = state["deck"].pop()
    else:
        state["face_up"][slot] = None
    state["face_up"], _swept = _maybe_replace_three_locos(
        [c for c in state["face_up"] if c is not None], state["deck"]
    )
    if _swept:
        state["sweep_count"] = state.get("sweep_count", 0) + 1
    # Re-pad to 5 slots
    while len(state["face_up"]) < 5:
        state["face_up"].append(None)

    if card == "locomotive":
        # Locomotive face-up counts as both draws
        state["draw_step"] = 0
        _end_draw_action(state, player_id)
    else:
        state["draw_step"] += 1
        if state["draw_step"] >= 2:
            state["draw_step"] = 0
            _end_draw_action(state, player_id)

    return {"ok": True, "card": card}


def draw_blind(state: dict, player_id: str) -> dict:
    """Draw blindly from the top of the deck."""
    if state["phase"] not in ("main", "final_round"):
        return {"ok": False, "error": "Not main game phase."}
    if state["current_player_id"] != player_id:
        return {"ok": False, "error": "Not your turn."}
    if state.get("pending_tunnel"):
        return {"ok": False, "error": "Resolve the pending tunnel first."}
    if state["player_states"][player_id].get("pending_tickets"):
        return {"ok": False, "error": "Keep your destinations first."}
    _ensure_deck(state)
    if not state["deck"]:
        return {"ok": False, "error": "No cards left to draw."}

    card = state["deck"].pop()
    ps = state["player_states"][player_id]
    ps["hand"][card] = ps["hand"].get(card, 0) + 1
    _log(state, f"{ps['name']} drew a blind card.")

    state["draw_step"] += 1
    if state["draw_step"] >= 2:
        state["draw_step"] = 0
        _end_draw_action(state, player_id)

    return {"ok": True, "card": card}


def _end_draw_action(state: dict, player_id: str):
    _next_turn(state)


# ---------------------------------------------------------------------------
# Claim a Route
# ---------------------------------------------------------------------------

def claim_route(state: dict, player_id: str, route_id: int, cards_to_use: dict) -> dict:
    """
    cards_to_use: {color: count} — the cards the player wants to spend.
    Locomotives are wildcards (and required for ferry routes).
    For tunnel routes: validates offer, draws 3 reveal cards, returns
    {"ok": True, "tunnel_pending": True, ...} — caller must call resolve_tunnel next.
    """
    if state["phase"] not in ("main", "final_round"):
        return {"ok": False, "error": "Not main game phase."}
    if state["current_player_id"] != player_id:
        return {"ok": False, "error": "Not your turn."}
    if state["draw_step"] != 0:
        return {"ok": False, "error": "You are in the middle of drawing cards."}
    if state.get("pending_tunnel"):
        return {"ok": False, "error": "Resolve the pending tunnel first."}
    if state["player_states"][player_id].get("pending_tickets"):
        return {"ok": False, "error": "Keep your destinations first."}

    map_variant = state.get("map", "usa")
    route_by_id, _, route_scoring, double_groups = _map_data(map_variant)
    route = route_by_id.get(route_id)
    if not route:
        return {"ok": False, "error": "Invalid route."}

    route_id_str = str(route_id)
    if route_id_str in state["claimed_routes"]:
        return {"ok": False, "error": "Route already claimed."}

    # Double-route restriction
    if route["double_group"]:
        group_ids = double_groups[route["double_group"]]
        other_ids = [rid for rid in group_ids if rid != route_id]
        num_players = len(state["turn_order"])
        for oid in other_ids:
            oid_str = str(oid)
            if oid_str in state["claimed_routes"]:
                if num_players <= 3:
                    return {"ok": False, "error": "Only one double-route allowed in 2-3 player games."}
                if state["claimed_routes"][oid_str] == player_id:
                    return {"ok": False, "error": "You already own the other side of this route."}

    ps = state["player_states"][player_id]
    required_length = route["length"]
    route_color = route["color"]
    ferry_locos = route.get("ferry", 0)
    is_tunnel  = route.get("tunnel", False)

    total_cards = sum(cards_to_use.values())
    if total_cards != required_length:
        return {"ok": False, "error": f"Need exactly {required_length} cards."}

    loco_count = cards_to_use.get("locomotive", 0)
    non_loco = {c: n for c, n in cards_to_use.items() if c != "locomotive"}

    # Ferry validation: must have at least ferry_locos locomotives
    if ferry_locos > 0:
        if loco_count < ferry_locos:
            return {"ok": False, "error": f"Ferry route requires at least {ferry_locos} locomotive card(s)."}
        # Non-loco cards for a ferry must all be the same color
        if len(non_loco) > 1:
            return {"ok": False, "error": "Ferry route: non-locomotive cards must all be the same color."}

    if route_color == "gray":
        if len(non_loco) > 1:
            return {"ok": False, "error": "Gray routes require cards of a single color plus locomotives."}
    else:
        for c in non_loco:
            if c != route_color:
                return {"ok": False, "error": f"Route requires {route_color} cards."}

    hand = ps["hand"]
    for color, count in cards_to_use.items():
        if hand.get(color, 0) < count:
            return {"ok": False, "error": f"Not enough {color} cards."}

    if ps["trains"] < required_length:
        return {"ok": False, "error": "Not enough trains."}

    # ── Tunnel: draw 3 reveal cards, hold state pending player confirmation ───
    if is_tunnel:
        # Temporarily remove cards from hand so they can't be used for anything else
        for color, count in cards_to_use.items():
            hand[color] -= count
            if hand[color] == 0:
                del hand[color]

        # Determine the "matching" color for extra cost (non-loco color, or loco if all-loco offer)
        if non_loco:
            extra_color = next(iter(non_loco))
        else:
            extra_color = "locomotive"

        # Draw up to 3 reveal cards
        revealed = []
        for _ in range(3):
            _ensure_deck(state)
            if state["deck"]:
                revealed.append(state["deck"].pop())

        # Count extra cost: how many revealed cards match extra_color or are locos
        extra_cost = sum(
            1 for c in revealed
            if c == extra_color or c == "locomotive"
        )

        # Put revealed cards into discard
        state["discard"].extend(revealed)

        state["pending_tunnel"] = {
            "player_id": player_id,
            "route_id": route_id,
            "cards_offered": dict(cards_to_use),
            "extra_cost": extra_cost,
            "extra_color": extra_color,
            "revealed": revealed,
        }
        return {
            "ok": True,
            "tunnel_pending": True,
            "revealed": revealed,
            "extra_cost": extra_cost,
            "extra_color": extra_color,
        }

    # ── Normal / ferry claim ─────────────────────────────────────────────────
    return _apply_claim(state, player_id, route, cards_to_use, route_scoring)


def _apply_claim(state: dict, player_id: str, route: dict, cards_to_use: dict, route_scoring: dict) -> dict:
    """Remove cards, place trains, record claim, advance turn."""
    ps = state["player_states"][player_id]
    hand = ps["hand"]
    required_length = route["length"]

    for color, count in cards_to_use.items():
        hand[color] = hand.get(color, 0) - count
        if hand[color] <= 0:
            hand.pop(color, None)
    state["discard"].extend(_expand_cards(cards_to_use))

    ps["trains"] -= required_length
    points = route_scoring[required_length]
    ps["route_score"] += points
    state["claimed_routes"][str(route["id"])] = player_id
    _log(state, f"{ps['name']} claimed {route['city1']}–{route['city2']} (+{points} pts).")

    if ps["trains"] <= 2 and state["phase"] == "main":
        _trigger_final_round(state, player_id)
    else:
        _next_turn(state)
    return {"ok": True, "points": points}


# ---------------------------------------------------------------------------
# Tunnel resolution (Europe only)
# ---------------------------------------------------------------------------

def resolve_tunnel(state: dict, player_id: str, proceed: bool, extra_cards: dict | None = None) -> dict:
    """
    Called after claim_route returns tunnel_pending=True.
    proceed=True  → player pays extra_cards (if any) and claims the route.
    proceed=False → player aborts; offered cards are returned, turn advances.
    """
    pt = state.get("pending_tunnel")
    if not pt or pt["player_id"] != player_id:
        return {"ok": False, "error": "No pending tunnel for you."}
    if state["current_player_id"] != player_id:
        return {"ok": False, "error": "Not your turn."}

    map_variant = state.get("map", "europe")
    route_by_id, _, route_scoring, _ = _map_data(map_variant)
    route = route_by_id[pt["route_id"]]

    ps = state["player_states"][player_id]
    offered = pt["cards_offered"]
    extra_cost = pt["extra_cost"]
    extra_color = pt["extra_color"]

    if not proceed or extra_cost == 0:
        # Return offered cards to hand
        for color, count in offered.items():
            ps["hand"][color] = ps["hand"].get(color, 0) + count
        state["pending_tunnel"] = None

        if not proceed:
            _log(state, f"{ps['name']} abandoned the {route['city1']}–{route['city2']} tunnel.")
            _next_turn(state)
            return {"ok": True, "claimed": False}
        else:
            # extra_cost == 0: free tunnel, proceed to claim
            return _apply_claim(state, player_id, route, offered, route_scoring)

    # Player must pay extra_cost cards of extra_color (or locomotive)
    extra_cards = extra_cards or {}
    total_extra = sum(extra_cards.values())
    if total_extra != extra_cost:
        # Return cards and report error (don't cancel the pending state yet)
        for color, count in offered.items():
            ps["hand"][color] = ps["hand"].get(color, 0) + count
        state["pending_tunnel"] = None
        return {"ok": False, "error": f"Must pay exactly {extra_cost} extra card(s)."}

    # Validate extra cards: must be extra_color or locomotive
    for c, n in extra_cards.items():
        if c != extra_color and c != "locomotive":
            for color, count in offered.items():
                ps["hand"][color] = ps["hand"].get(color, 0) + count
            state["pending_tunnel"] = None
            return {"ok": False, "error": f"Extra cards must be {extra_color} or locomotive."}
        if ps["hand"].get(c, 0) < n:
            for color, count in offered.items():
                ps["hand"][color] = ps["hand"].get(color, 0) + count
            state["pending_tunnel"] = None
            return {"ok": False, "error": f"Not enough {c} cards for extra cost."}

    state["pending_tunnel"] = None
    # Return offered cards so _apply_claim can deduct everything in one pass
    for color, count in offered.items():
        ps["hand"][color] = ps["hand"].get(color, 0) + count

    all_used = dict(offered)
    for c, n in extra_cards.items():
        all_used[c] = all_used.get(c, 0) + n

    return _apply_claim(state, player_id, route, all_used, route_scoring)


# ---------------------------------------------------------------------------
# Station placement (Europe only)
# ---------------------------------------------------------------------------

def place_station(state: dict, player_id: str, city: str, cards_to_use: dict) -> dict:
    """
    Player places one of their 3 train stations in city.
    Cost: 1 card for 1st station, 2 cards for 2nd, 3 cards for 3rd (all same color).
    """
    if state.get("map") != "europe":
        return {"ok": False, "error": "Stations are a Europe-only mechanic."}
    if state["phase"] not in ("main", "final_round"):
        return {"ok": False, "error": "Not main game phase."}
    if state["current_player_id"] != player_id:
        return {"ok": False, "error": "Not your turn."}
    if state["draw_step"] != 0:
        return {"ok": False, "error": "You are in the middle of drawing cards."}
    if state.get("pending_tunnel"):
        return {"ok": False, "error": "Resolve the pending tunnel first."}

    ps = state["player_states"][player_id]
    if ps.get("pending_tickets"):
        return {"ok": False, "error": "Keep your destinations first."}
    stations_placed = len(state["stations"].get(player_id, []))
    if ps.get("station_count", 0) <= 0:
        return {"ok": False, "error": "No stations remaining."}

    required_cost = stations_placed + 1  # 1st=1, 2nd=2, 3rd=3
    total = sum(cards_to_use.values())
    if total != required_cost:
        return {"ok": False, "error": f"Station costs {required_cost} card(s) of one color."}

    loco_count = cards_to_use.get("locomotive", 0)
    non_loco = {c: n for c, n in cards_to_use.items() if c != "locomotive"}
    if len(non_loco) > 1:
        return {"ok": False, "error": "Station cards must all be the same color."}

    # Check city exists and isn't already occupied by this player
    existing = state["stations"].get(player_id, [])
    if city in existing:
        return {"ok": False, "error": "You already have a station in that city."}

    hand = ps["hand"]
    for color, count in cards_to_use.items():
        if hand.get(color, 0) < count:
            return {"ok": False, "error": f"Not enough {color} cards."}

    for color, count in cards_to_use.items():
        hand[color] -= count
        if hand[color] <= 0:
            hand.pop(color, None)
    state["discard"].extend(_expand_cards(cards_to_use))

    state["stations"].setdefault(player_id, []).append(city)
    ps["station_count"] = ps.get("station_count", 3) - 1
    _log(state, f"{ps['name']} placed a station in {city}.")
    _next_turn(state)
    return {"ok": True}


def _expand_cards(cards: dict) -> list:
    result = []
    for color, count in cards.items():
        result.extend([color] * count)
    return result


# ---------------------------------------------------------------------------
# Draw Destinations
# ---------------------------------------------------------------------------

def draw_destination_tickets(state: dict, player_id: str) -> dict:
    if state["phase"] not in ("main", "final_round"):
        return {"ok": False, "error": "Not main game phase."}
    if state["current_player_id"] != player_id:
        return {"ok": False, "error": "Not your turn."}
    if state["draw_step"] != 0:
        return {"ok": False, "error": "You are in the middle of drawing cards."}
    if state.get("pending_tunnel"):
        return {"ok": False, "error": "Resolve the tunnel first."}
    if state["player_states"][player_id].get("pending_tickets"):
        return {"ok": False, "error": "Keep your current destinations first."}

    if not state["dest_deck"]:
        return {"ok": False, "error": "No destinations left."}

    _, ticket_by_id, _, _ = _map_data(state.get("map", "usa"))
    ps = state["player_states"][player_id]
    available = min(3, len(state["dest_deck"]))
    drawn = state["dest_deck"][:available]
    state["dest_deck"] = state["dest_deck"][available:]
    ps["pending_tickets"] = drawn

    return {"ok": True, "tickets": [ticket_by_id[t] for t in drawn]}


def keep_drawn_tickets(state: dict, player_id: str, keep_ids: list[int]) -> dict:
    if state["current_player_id"] != player_id:
        return {"ok": False, "error": "Not your turn."}

    ps = state["player_states"][player_id]
    pending = ps["pending_tickets"]
    if not pending:
        return {"ok": False, "error": "No pending tickets."}
    if len(keep_ids) < 1:
        return {"ok": False, "error": "Must keep at least 1 ticket."}
    if not all(k in pending for k in keep_ids):
        return {"ok": False, "error": "Invalid ticket selection."}

    ps["tickets"].extend(keep_ids)
    returned = [t for t in pending if t not in keep_ids]
    state["dest_deck"].extend(returned)
    ps["pending_tickets"] = []
    _log(state, f"{ps['name']} drew destinations.")
    _next_turn(state)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Turn management
# ---------------------------------------------------------------------------

def _next_turn(state: dict):
    order = state["turn_order"]
    cur = state["current_player_id"]
    idx = order.index(cur)
    state["turns_taken"] = state.get("turns_taken", 0) + 1

    if state["phase"] == "final_round":
        remaining = state["final_round_players_left"]
        if cur in remaining:
            remaining.remove(cur)
        # Drop any resigned players from final round remaining
        state["final_round_players_left"] = [
            p for p in remaining
            if not state["player_states"].get(p, {}).get("resigned")
        ]
        if not state["final_round_players_left"]:
            _end_game(state)
            return

    # Skip resigned players when finding next turn
    nxt = None
    for i in range(1, len(order) + 1):
        candidate = order[(idx + i) % len(order)]
        if not state["player_states"].get(candidate, {}).get("resigned"):
            nxt = candidate
            break
    if nxt is None:
        _end_game(state)
        return

    state["current_player_id"] = nxt
    state["draw_step"] = 0


def resign_player(state: dict, player_id: str) -> dict:
    ps = state["player_states"].get(player_id)
    if not ps:
        return {"ok": False, "error": "Player not found."}
    if ps.get("resigned"):
        return {"ok": False, "error": "Already resigned."}
    if state.get("phase") not in ("main", "final_round"):
        return {"ok": False, "error": "Cannot resign during this phase."}

    ps["resigned"] = True
    state.setdefault("action_log", []).append(f"{ps['name']} has resigned from the game.")

    # End immediately if only 1 (or 0) active players remain
    active = [pid for pid, p in state["player_states"].items() if not p.get("resigned")]
    if len(active) <= 1:
        _end_game(state)
        return {"ok": True}

    # If it was their turn, advance past them
    if state.get("current_player_id") == player_id:
        if state["phase"] == "final_round":
            remaining = state.get("final_round_players_left", [])
            if player_id in remaining:
                remaining.remove(player_id)
            state["final_round_players_left"] = [
                p for p in remaining
                if not state["player_states"].get(p, {}).get("resigned")
            ]
            if not state["final_round_players_left"]:
                _end_game(state)
                return {"ok": True}
        _next_turn(state)

    return {"ok": True}


def _trigger_final_round(state: dict, triggering_player_id: str):
    """Set up the final round: all other players get one last turn, then the triggering player too."""
    state["phase"] = "final_round"
    state["final_round_triggered_by"] = triggering_player_id
    order = state["turn_order"]
    idx = order.index(triggering_player_id)
    # Order: players after trigger go first, triggering player gets the very last turn
    remaining = [order[(idx + i + 1) % len(order)] for i in range(len(order) - 1)]
    remaining.append(triggering_player_id)
    state["final_round_players_left"] = remaining

    state["current_player_id"] = order[(idx + 1) % len(order)]
    state["draw_step"] = 0


# ---------------------------------------------------------------------------
# End game and scoring
# ---------------------------------------------------------------------------

def _end_game(state: dict):
    state["phase"] = "ended"
    is_europe = state.get("map") == "europe"
    _, ticket_by_id, _, _ = _map_data(state.get("map", "usa"))

    scores = {}
    for pid, ps in state["player_states"].items():
        total = ps["route_score"]
        ticket_details = []
        for tid in ps["tickets"]:
            ticket = ticket_by_id[tid]
            completed = is_path_connected(state, pid, ticket["city1"], ticket["city2"])
            delta = ticket["points"] if completed else -ticket["points"]
            total += delta
            ticket_details.append({"id": tid, "completed": completed, "delta": delta})

        station_bonus = 0
        if is_europe:
            unused = ps.get("station_count", 0)
            station_bonus = unused * 4
            total += station_bonus

        scores[pid] = {
            "name": ps["name"],
            "color": ps["color"],
            "route_score": ps["route_score"],
            "tickets": ticket_details,
            "longest_path": 0,
            "station_bonus": station_bonus,
            "total": total,
        }

    # Longest path bonus (10 pts, both maps)
    max_path = 0
    for pid in state["player_states"]:
        lp = longest_path(state, pid)
        scores[pid]["longest_path"] = lp
        if lp > max_path:
            max_path = lp

    winners_of_longest = [pid for pid in scores if scores[pid]["longest_path"] == max_path]
    for pid in winners_of_longest:
        scores[pid]["total"] += 10
        scores[pid]["longest_path_bonus"] = True

    state["scores"] = scores

    # Tiebreak: highest score, then most COMPLETED
    # destinations, then longest path.
    sorted_players = sorted(scores.items(), key=lambda x: (
        x[1]["total"],
        sum(1 for t in x[1]["tickets"] if t["completed"]),
        x[1]["longest_path"],
    ), reverse=True)
    state["winner_id"] = sorted_players[0][0]
    _log(state, f"Game ended! Winner: {scores[state['winner_id']]['name']}")


# ---------------------------------------------------------------------------
# Graph algorithms
# ---------------------------------------------------------------------------

def _build_player_graph(state: dict, player_id: str) -> dict[str, set[str]]:
    """Return adjacency list of routes owned by player_id, plus station-borrowed routes."""
    route_by_id, _, _, _ = _map_data(state.get("map", "usa"))
    graph: dict[str, set[str]] = defaultdict(set)
    for route_id_str, pid in state["claimed_routes"].items():
        if pid == player_id:
            route = route_by_id[int(route_id_str)]
            graph[route["city1"]].add(route["city2"])
            graph[route["city2"]].add(route["city1"])

    # Europe stations: for each city where this player has a station, also add
    # all opponent routes FROM that city (player may use one opponent route per station)
    if state.get("map") == "europe":
        station_cities = state.get("stations", {}).get(player_id, [])
        for city in station_cities:
            for route_id_str, pid in state["claimed_routes"].items():
                if pid != player_id:
                    route = route_by_id[int(route_id_str)]
                    if route["city1"] == city:
                        graph[city].add(route["city2"])
                    elif route["city2"] == city:
                        graph[city].add(route["city1"])
    return graph


def is_path_connected(state: dict, player_id: str, city1: str, city2: str) -> bool:
    """BFS to check if city1 and city2 are connected in the player's network."""
    graph = _build_player_graph(state, player_id)
    if city1 not in graph and city2 not in graph:
        return False
    visited = set()
    queue = deque([city1])
    while queue:
        node = queue.popleft()
        if node == city2:
            return True
        if node in visited:
            continue
        visited.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                queue.append(neighbor)
    return False


def longest_path(state: dict, player_id: str) -> int:
    """Find the longest trail (path reusing no edge, but cities OK) in the player's network.

    Uses backtracking DFS over edges. Each route is a unique edge identified by its
    index in `edges`, so parallel routes between the same two cities are treated
    separately. Cities may be visited multiple times; edges may not.
    """
    route_by_id, _, _, _ = _map_data(state.get("map", "usa"))
    edges: list[tuple[str, str, int]] = []
    for route_id_str, pid in state["claimed_routes"].items():
        if pid == player_id:
            route = route_by_id[int(route_id_str)]
            edges.append((route["city1"], route["city2"], route["length"]))

    if not edges:
        return 0

    # Adjacency: city -> list of (neighbor, edge_index, length)
    adj: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for i, (c1, c2, length) in enumerate(edges):
        adj[c1].append((c2, i, length))
        adj[c2].append((c1, i, length))

    cities = {c for c1, c2, _ in edges for c in (c1, c2)}
    best = [0]

    def dfs(city: str, used_edges: set[int], length: int) -> None:
        if length > best[0]:
            best[0] = length
        for neighbor, edge_idx, seg_len in adj[city]:
            if edge_idx not in used_edges:
                used_edges.add(edge_idx)
                dfs(neighbor, used_edges, length + seg_len)
                used_edges.remove(edge_idx)

    # Try every city as a starting point (required for non-Eulerian graphs)
    for start in cities:
        dfs(start, set(), 0)

    return best[0]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _log(state: dict, msg: str):
    state["action_log"].append(msg)
    if len(state["action_log"]) > 100:
        state["action_log"] = state["action_log"][-100:]


def get_public_state(state: dict, viewer_id: str) -> dict:
    """Return the game state suitable for sending to a specific player."""
    _, ticket_by_id, _, _ = _map_data(state.get("map", "usa"))
    is_europe = state.get("map") == "europe"

    players_public = {}
    for pid, ps in state["player_states"].items():
        pub_ps: dict = {
            "name": ps["name"],
            "color": ps["color"],
            "turn_order": ps["turn_order"],
            "trains": ps["trains"],
            "route_score": ps["route_score"],
            "ticket_count": len(ps["tickets"]),
            "card_count": sum(ps["hand"].values()),
            "hand": ps["hand"] if pid == viewer_id else {},
            "tickets": ps["tickets"] if pid == viewer_id else [],
            "pending_tickets": (
                [ticket_by_id[t] for t in ps["pending_tickets"]]
                if pid == viewer_id else []
            ),
        }
        if is_europe:
            pub_ps["station_count"] = ps.get("station_count", 0)
            if pid == viewer_id:
                pub_ps["long_ticket_id"] = ps.get("long_ticket_id")
        players_public[pid] = pub_ps

    pub: dict = {
        "map": state.get("map", "usa"),
        "phase": state["phase"],
        "face_up": state["face_up"],
        "sweep_count": state.get("sweep_count", 0),
        "deck_count": len(state["deck"]),
        "dest_deck_count": len(state["dest_deck"]),
        "claimed_routes": state["claimed_routes"],
        "current_player_id": state["current_player_id"],
        "turn_order": state["turn_order"],
        "draw_step": state["draw_step"],
        "players": players_public,
        "action_log": state["action_log"][-10:],
        "scores": state.get("scores", {}),
        "winner_id": state.get("winner_id"),
        "final_round_players_left": state.get("final_round_players_left", []),
        "final_round_triggered_by": state.get("final_round_triggered_by"),
        "round_number": state.get("turns_taken", 0) // max(len(state["turn_order"]), 1) + 1,
    }
    if is_europe:
        pub["stations"] = state.get("stations", {})
        pt = state.get("pending_tunnel")
        # Only send tunnel details to the player who triggered it
        if pt and pt["player_id"] == viewer_id:
            pub["pending_tunnel"] = pt
        else:
            pub["pending_tunnel"] = None
    return pub

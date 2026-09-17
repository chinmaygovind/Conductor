"""
shitter-bot — the sophisticated Conductor brain.

A self-contained, instant (no tree search) policy that plays the way a strong
human does. Public entry: shitter_policy(state, pid) -> (action, params).

Design goals (all validated by benchmark vs the other bots):
  1. Know which tickets it still owes and PRIORITISE completing them, closest
     ticket first, by claiming the next route on that ticket's path.
  2. Prefer to complete tickets with FEWER, LONGER routes — a slightly longer
     path made of long routes scores more route points and feeds longest-path
     (the `_HOP_PENALTY` term in path-finding biases toward long segments).
  3. Grow ONE mostly-continuous network so it reliably earns the longest-path
     bonus (continuity bonus for routes that extend / join its own track).
  4. Model opponents from their claimed routes (which clusters they are linking)
     and block a route that bridges their network — but only once its own
     tickets are done or the block is convenient, so it never wastes trains.

While it still owes tickets it only ever claims routes on a ticket path; long
value routes, longest-path extension and speculative blocking unlock once every
ticket is complete (or unreachable). That ordering is what keeps completion high.
"""
import os
import sys
import heapq
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game_logic as logic
from game_data_na import (ROUTE_BY_ID, ROUTE_SCORING, TICKET_BY_ID,
                          DOUBLE_ROUTE_GROUPS)

# Routes pre-sorted by point value (high first) for claim scanning.
ROUTES_BY_VALUE = sorted(
    [(ROUTE_SCORING.get(r["length"], 1), rid, r) for rid, r in ROUTE_BY_ID.items()],
    reverse=True,
)

# route_id -> partner route id (the other side of a double route).
DOUBLE_ROUTE_PARTNER = {}
for _rid, _r in ROUTE_BY_ID.items():
    _dg = _r.get("double_group")
    if _dg:
        for _oid in DOUBLE_ROUTE_GROUPS.get(_dg, []):
            if _oid != _rid:
                DOUBLE_ROUTE_PARTNER[_rid] = _oid
                break

_PTS = ROUTE_SCORING          # length -> route points {1:1,2:2,3:4,4:7,5:10,6:15}

# Per-route penalty added during ticket path-finding. It makes a path of a few
# LONG routes cheaper than many short ones for the same cities, so the bot takes
# a slightly longer route built from long segments (more route score + longest
# path) rather than the strict minimum-train path. Kept small so it never causes
# a wasteful detour.
_HOP_PENALTY = 0.8

# Drawing EXTRA destinations mid-game — ENABLED but DISCIPLINED.
# History: a naive "draw when network is big" fallback backfired hard (you MUST
# keep >=1 of the 3, and a fresh cross-map ticket is usually unfinishable dead
# weight): real prod games g178 (-54 pts, scored 21) and g179 (-23, scored 62).
# The discipline that makes it safe lives in shitter_keep_tickets(): mid-game it
# only keeps tickets already EASILY EXTENDABLE onto the network (already connected
# or <= _EASY_EXTEND_MAX new trains), so a drawn ticket is near-free or skipped.
# We also only draw once the current plan is done (not owing) and the network is
# large with trains to spare. A/B (100-120 games/opp): with the easy-extend filter
# the blow-up games vanish and tickets-completed RISES (chin 2P 2.56->2.70), at a
# tiny tempo cost (~1-2 games/100) that only shows in fast bot games — human-paced
# games reward the extra completed tickets (DB: 4-6 tickets ~115 pts vs ~90 for 3).
# Set SHITTER_DRAW_TICKETS=0 to disable.
_DRAW_TICKET_MIN_TRAINS = int(os.environ.get("SHITTER_DRAW_MIN_TRAINS", "18"))
_DRAW_TICKET_MIN_CITIES = int(os.environ.get("SHITTER_DRAW_MIN_CITIES", "12"))
_DRAW_TICKETS_ENABLED   = os.environ.get("SHITTER_DRAW_TICKETS", "1") == "1"

# Anti-hoarding tempo thresholds: how good a route must score before we claim it
# (vs drawing cards). Self-play A/B "showed no gain" from spending trains earlier —
# but that's because bot opponents never trigger a fast endgame. Real games vs humans
# (prod DB) told the true story: shitter ended games with ~10 trains and ~8 cards
# unbuilt because a fast human (fishy) ended the game while it was still hoarding.
# Fixes: build earlier (lower HI bar, higher MID-trains cutoff) AND react to an
# opponent nearing the end (see _claim_threshold / _ENDGAME_OPP_TRAINS). Env-tunable.
_TEMPO_MID_TRAINS = int(os.environ.get("SHITTER_TEMPO_MID_TRAINS", "15"))
_TEMPO_MID_THRESH = float(os.environ.get("SHITTER_TEMPO_MID_THRESH", "1.0"))
_TEMPO_HI_THRESH  = float(os.environ.get("SHITTER_TEMPO_HI_THRESH", "2.5"))
# When any opponent has <= this many trains the game is about to end — stop hoarding
# and grab affordable routes now, regardless of our own train count.
_ENDGAME_OPP_TRAINS = int(os.environ.get("SHITTER_ENDGAME_OPP_TRAINS", "7"))


def _claim_threshold(owing, trains, opp_min_trains):
    """Minimum route score to claim (vs draw). Drops the bar as our OWN trains
    dwindle, and — the key fix vs fast human opponents — also when an OPPONENT is
    nearly out of trains, since the game is about to end and unbuilt trains are just
    wasted route points + longest-path track."""
    if owing:
        return 0.0                      # always advance a ticket path
    if opp_min_trains <= _ENDGAME_OPP_TRAINS:
        return _TEMPO_MID_THRESH        # opponent about to end it — grab anything affordable
    if trains <= _TEMPO_MID_TRAINS:
        return _TEMPO_MID_THRESH        # our own end-game — use our trains
    return _TEMPO_HI_THRESH             # early — don't waste good cards on junk routes


# ---------------------------------------------------------------------------
# Claim feasibility
# ---------------------------------------------------------------------------

def _can_claim_fast(hand, route, trains, n_players, claimed, pid,
                    sorted_hand=None, locos=None):
    """Return the card dict to claim `route`, or None if not affordable/legal."""
    length = route["length"]
    if length > trains:
        return None
    rid_str = str(route["id"])
    if rid_str in claimed:
        return None
    if n_players <= 3:
        partner = DOUBLE_ROUTE_PARTNER.get(route["id"])
        if partner and str(partner) in claimed:
            return None
    color = route.get("color", "gray")
    if locos is None:
        locos = hand.get("locomotive", 0)

    def _try(c):
        have = hand.get(c, 0)
        cu = min(have, length)
        lu = length - cu
        if lu > locos:
            return None
        r = {}
        if cu:
            r[c] = cu
        if lu:
            r["locomotive"] = lu
        return r

    if color == "gray":
        sh = sorted_hand if sorted_hand is not None else sorted(
            ((c, n) for c, n in hand.items() if c != "locomotive" and n > 0),
            key=lambda x: -x[1],
        )
        for c, _ in sh:
            r = _try(c)
            if r is not None:
                return r
        return {"locomotive": length} if locos >= length else None
    r = _try(color)
    if r is not None:
        return r
    return {"locomotive": length} if locos >= length else None


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def _available_adj(state, pid):
    """Adjacency over routes still usable by pid (owned cost 0, opponent = blocked)."""
    claimed   = state["claimed_routes"]
    n_players = len(state.get("turn_order", []))
    adj = {}
    for rid, r in ROUTE_BY_ID.items():
        owner = claimed.get(str(rid))
        if owner is not None and owner != pid:
            continue
        if owner is None and n_players <= 3:
            partner = DOUBLE_ROUTE_PARTNER.get(rid)
            if partner and str(partner) in claimed:
                continue
        cost = 0.0 if owner == pid else r["length"]
        adj.setdefault(r["city1"], []).append((cost, r["city2"], rid))
        adj.setdefault(r["city2"], []).append((cost, r["city1"], rid))
    return adj


def _path_route_ids(adj, start, end):
    """Dijkstra over available routes, biased toward fewer/longer segments via
    _HOP_PENALTY. Returns the route-id list of the chosen path, or None."""
    if start == end:
        return []
    dist = {start: 0.0}
    prev = {}
    heap = [(0.0, start)]
    while heap:
        d, city = heapq.heappop(heap)
        if city == end:
            path, cur = [], end
            while cur in prev:
                pc, rid = prev[cur]
                path.append(rid)
                cur = pc
            return list(reversed(path))
        if d > dist.get(city, float("inf")):
            continue
        for cost, nbr, rid in adj.get(city, []):
            nd = d + cost + (_HOP_PENALTY if cost > 0 else 0.0)
            if nd < dist.get(nbr, float("inf")):
                dist[nbr] = nd
                prev[nbr] = (city, rid)
                heapq.heappush(heap, (nd, nbr))
    return None


def _my_cities(claimed, pid):
    cities = set()
    for rid, owner in claimed.items():
        if owner == pid:
            r = ROUTE_BY_ID.get(int(rid))
            if r:
                cities.add(r["city1"]); cities.add(r["city2"])
    return cities


def _my_degrees(claimed, pid):
    """City -> number of my own routes touching it. Degree-1 cities are the
    ENDPOINTS of my network; extending an endpoint lengthens my longest trail,
    whereas building off a junction just adds a branch."""
    deg = {}
    for rid, owner in claimed.items():
        if owner == pid:
            r = ROUTE_BY_ID.get(int(rid))
            if r:
                deg[r["city1"]] = deg.get(r["city1"], 0) + 1
                deg[r["city2"]] = deg.get(r["city2"], 0) + 1
    return deg


def _component_root(edges):
    """Union-find over (city1, city2) edges -> {city: root}."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for a, b in edges:
        parent[find(a)] = find(b)
    return {c: find(c) for c in parent}


def _estimate_opponent_needs(state, pid):
    """Routes that would link an opponent's separate clusters (they likely want
    these to finish tickets). Returns {route_id: block_value}."""
    claimed = state["claimed_routes"]
    need = {}
    for opp in state["player_states"]:
        if opp == pid:
            continue
        edges = [(ROUTE_BY_ID[int(rid)]["city1"], ROUTE_BY_ID[int(rid)]["city2"])
                 for rid, o in claimed.items() if o == opp and int(rid) in ROUTE_BY_ID]
        if not edges:
            continue
        root = _component_root(edges)
        for rid, route in ROUTE_BY_ID.items():
            if str(rid) in claimed:
                continue
            r1 = root.get(route["city1"]); r2 = root.get(route["city2"])
            if r1 and r2 and r1 != r2:                 # bridges two of their clusters
                need[rid] = need.get(rid, 0) + 6 + route["length"]
            elif r1 or r2:                             # merely extends their network
                need[rid] = need.get(rid, 0) + 2
    return need


def _draw_toward(face_up, focus_routes, draw_step):
    """Draw a locomotive or the colour the focus routes need MOST; else draw blind.
    Colours are weighted by route length (a length-6 route needs six of its colour,
    a length-2 only two), so the card we grab is the one that most advances an
    affordable claim rather than just the first matching face-up card."""
    need_colors = {}
    for rid in focus_routes:
        r = ROUTE_BY_ID.get(rid)
        if not r:
            continue
        col = r.get("color", "gray")
        if col not in ("gray", "locomotive"):
            need_colors[col] = need_colors.get(col, 0) + r["length"]
    if draw_step == 0:
        for i, card in enumerate(face_up):
            if card == "locomotive":
                return "draw_face_up", {"slot": i}
    best_i, best_need = None, 0
    for i, card in enumerate(face_up):
        if card and card != "locomotive":
            need = need_colors.get(card, 0)
            if need > best_need:
                best_need, best_i = need, i
    if best_i is not None:
        return "draw_face_up", {"slot": best_i}
    return "draw_blind", {}


# ---------------------------------------------------------------------------
# Ticket selection — overlap, continuity, cross-map value
# ---------------------------------------------------------------------------
# How a strong human picks tickets (per chinmay): choose tickets whose paths
# OVERLAP so one corridor of long segments serves several tickets; keep them on
# ONE continuous chain to chase the longest-path bonus; prefer high-value cross-
# map tickets (their paths are made of long segments = most route points + LP).
# Mid-game, only AFTER the current plan is basically done, draw more and keep only
# tickets that are very EASILY EXTENDABLE onto the existing network.

_SYNERGY_W    = float(os.environ.get("SHITTER_SYNERGY_W", "0.7"))   # value per train shared between tickets
_CONTINUITY_W = float(os.environ.get("SHITTER_CONTINUITY_W", "0.5"))# value per new train laid on the single main chain
_KEEP_BUDGET_FRAC = 0.85
_EASY_EXTEND_MAX  = int(os.environ.get("SHITTER_EASY_EXTEND_MAX", "7"))  # mid-game: max new trains for a "free" keep


def _clampf(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def _keep_candidates(state, pid, pending):
    """For each pending ticket build (tid, ticket, needed_route_ids|None, new_train_cost).
    Uses the SAME long-segment-biased pathing the policy builds with, and treats
    already-connected tickets as free (cost 0)."""
    claimed = state["claimed_routes"]
    owned   = {int(r) for r, o in claimed.items() if o == pid}
    adj     = _available_adj(state, pid)
    out = []
    for tid in pending:
        t = TICKET_BY_ID.get(tid)
        if not t:
            continue
        if logic.is_path_connected(state, pid, t["city1"], t["city2"]):
            out.append((tid, t, set(), 0))                 # already done = free
            continue
        path = _path_route_ids(adj, t["city1"], t["city2"])
        if path is None:
            out.append((tid, t, None, 10 ** 9))            # unreachable
            continue
        need = {r for r in path if r not in owned}
        cost = sum(ROUTE_BY_ID[r]["length"] for r in need)
        out.append((tid, t, need, cost))
    return out, owned


def _eval_keep_subset(sub, owned, trains):
    """Expected value of keeping `sub` (list of keep-candidate tuples), with a
    synergy bonus for overlapping ticket paths and a continuity bonus for laying
    that track as ONE chain attached to the main network (longest-path bonus)."""
    union = set()
    indep = 0
    for _tid, _t, need, cost in sub:
        if need:
            union |= need
            indep += cost
    new_trains = sum(ROUTE_BY_ID[r]["length"] for r in union if r in ROUTE_BY_ID)

    budget = max(1.0, trains * _KEEP_BUDGET_FRAC)
    over   = max(0.0, new_trains - budget)
    feas   = _clampf(0.92 - 0.9 * (over / budget), 0.35, 0.92)

    ev = 0.0
    for _tid, t, need, cost in sub:
        pts = t.get("points", 0)
        if need is None:
            p = 0.02                                       # unreachable -> dead weight
        else:
            p = feas * _clampf(1.0 - 0.008 * cost, 0.60, 0.97)
        ev += pts * (2.0 * p - 1.0)

    # Synergy: trains the kept tickets SHARE (built once, count for several).
    ev += _SYNERGY_W * feas * max(0, indep - new_trains)

    # Continuity: of the new track, how much lands on the SINGLE largest network
    # component (owned + planned). Track that chains onto one continuous line is
    # worth more (feeds the longest-path bonus) than the same track split into
    # disconnected islands.
    if union:
        owned_edges = [(ROUTE_BY_ID[r]["city1"], ROUTE_BY_ID[r]["city2"])
                       for r in owned if r in ROUTE_BY_ID]
        plan_edges  = [(ROUTE_BY_ID[r]["city1"], ROUTE_BY_ID[r]["city2"])
                       for r in union if r in ROUTE_BY_ID]
        root = _component_root(owned_edges + plan_edges)
        comp_len = {}
        for r in (owned | union):
            rr = ROUTE_BY_ID.get(r)
            if not rr:
                continue
            cr = root.get(rr["city1"])
            comp_len[cr] = comp_len.get(cr, 0) + rr["length"]
        main = max(comp_len, key=comp_len.get) if comp_len else None
        on_main = sum(ROUTE_BY_ID[r]["length"] for r in union
                      if r in ROUTE_BY_ID and root.get(ROUTE_BY_ID[r]["city1"]) == main)
        ev += _CONTINUITY_W * feas * on_main
    return ev


def shitter_keep_tickets(state, pid, pending, min_keep, mid_game):
    """Pick the keep-subset that maximises EV+synergy+continuity (>= min_keep).
    Mid-game, hard-filter out any ticket that is NOT already easily extendable
    (already connected or <= _EASY_EXTEND_MAX new trains) before choosing — we
    only ever draw mid-game when the current plan is done, so newly kept tickets
    must be near-free, never speculative cross-map dead weight."""
    import itertools
    cand, owned = _keep_candidates(state, pid, pending)
    if not cand:
        return list(pending[:min_keep])
    trains = state["player_states"].get(pid, {}).get("trains", 45)

    if mid_game:
        easy = [c for c in cand if c[2] is not None and c[3] <= _EASY_EXTEND_MAX]
        if easy:
            cand = easy                                    # only keep near-free tickets
        else:
            cand.sort(key=lambda c: c[3])                  # forced: keep the cheapest one
            return [cand[0][0]]

    if len(cand) <= min_keep:
        return [c[0] for c in cand]

    best, best_ev = None, None
    idx = list(range(len(cand)))
    for k in range(min_keep, len(cand) + 1):
        for combo in itertools.combinations(idx, k):
            ev = _eval_keep_subset([cand[i] for i in combo], owned, trains)
            if best_ev is None or ev > best_ev:
                best_ev, best = ev, combo
    return [cand[i][0] for i in best]


# ---------------------------------------------------------------------------
# Public policy
# ---------------------------------------------------------------------------

def shitter_policy(state, pid):
    ps        = state["player_states"].get(pid, {})
    hand      = ps.get("hand", {})
    trains    = ps.get("trains", 45)
    tickets   = ps.get("tickets", [])
    draw_step = state.get("draw_step", 0)
    face_up   = state["face_up"]
    claimed   = state["claimed_routes"]
    n_players = len(state.get("turn_order", []))
    locos     = hand.get("locomotive", 0)
    sorted_hand = sorted(
        ((c, n) for c, n in hand.items() if c != "locomotive" and n > 0),
        key=lambda x: -x[1],
    )

    my_cities = _my_cities(claimed, pid)
    my_deg    = _my_degrees(claimed, pid)
    endpoints = {c for c, d in my_deg.items() if d == 1}
    my_root   = _component_root([(ROUTE_BY_ID[int(r)]["city1"], ROUTE_BY_ID[int(r)]["city2"])
                                 for r, o in claimed.items()
                                 if o == pid and int(r) in ROUTE_BY_ID])
    adj       = _available_adj(state, pid)

    # Incomplete reachable tickets -> their (long-route-biased) path.
    targets = []   # (remaining_trains, points, set(needed route ids))
    for tid in tickets:
        t = TICKET_BY_ID.get(tid)
        if not t or logic.is_path_connected(state, pid, t["city1"], t["city2"]):
            continue
        path = _path_route_ids(adj, t["city1"], t["city2"])
        if not path:
            continue
        need = [rid for rid in path if str(rid) not in claimed]
        targets.append((sum(ROUTE_BY_ID[r]["length"] for r in need),
                        t.get("points", 0), set(need)))
    targets.sort(key=lambda x: (x[0], -x[1]))

    plan_routes = set()
    for _rem, _pts, need in targets:
        plan_routes |= need
    closest  = targets[0][2] if targets else set()
    opp_need = _estimate_opponent_needs(state, pid)
    owing    = bool(targets)

    # How hard to chase the longest-path bonus by extending our endpoints. Once
    # tickets are done we check whether an opponent's longest path rivals ours; if
    # they're ahead or close, extending (linear growth) is worth much more — taking
    # a slightly worse route to lengthen our single path can flip the 10pt bonus
    # and the tiebreak. (longest_path is only computed here, in the endgame phase.)
    extend_weight = 3.0
    if not owing and my_cities:
        try:
            my_lp  = logic.longest_path(state, pid)
            opp_lp = max((logic.longest_path(state, o)
                          for o in state["player_states"] if o != pid), default=0)
            extend_weight = 6.0 if opp_lp >= my_lp - 2 else 3.0
        except Exception:
            extend_weight = 4.0

    if draw_step == 0:
        best_rid, best_cards, best_score = None, None, -1.0
        for _val, rid, route in ROUTES_BY_VALUE:
            if str(rid) in claimed:
                continue
            on_plan = rid in plan_routes
            if owing and not on_plan:
                continue                                 # reserve trains for tickets
            cards = _can_claim_fast(hand, route, trains, n_players, claimed, pid,
                                    sorted_hand, locos)
            if cards is None:
                continue
            length = route["length"]
            score  = 0.0

            if on_plan:                                  # ticket completion dominates
                score += 50.0
                if rid in closest:
                    score += 15.0                        # focus the closest ticket

            score += _PTS.get(length, 1) + 0.8 * length  # route points + longest-path nudge

            c1, c2 = route["city1"], route["city2"]
            c1in, c2in = c1 in my_cities, c2 in my_cities
            if c1in and c2in:
                # Both ends already mine: MERGING two separate clusters into one
                # network is valuable (helps tickets + a longer single path); a
                # route inside one cluster is just a useless cycle.
                if my_root.get(c1) != my_root.get(c2):
                    score += 6.0 + 0.3 * length          # merge clusters
                else:
                    score += 1.0                         # cycle — minimal value
            elif c1in or c2in:
                # Connects to my network. Extending an ENDPOINT lengthens my single
                # longest trail (great for longest-path); building off a junction is
                # just a branch.
                if (c1 in endpoints) or (c2 in endpoints):
                    score += 5.0 + extend_weight + 0.3 * length
                else:
                    score += 4.0                         # branch off a junction

            ob = opp_need.get(rid, 0)
            if ob > 0 and (on_plan or length >= 4 or trains > 22):
                score += min(ob, 8.0)                    # convenient, worthwhile block

            if score > best_score:
                best_score, best_rid, best_cards = score, rid, cards

        # Claim if the best route clears the tempo bar. The bar drops as our trains
        # dwindle AND when an opponent is nearly out of trains — otherwise a fast
        # human ends the game while we sit on unbuilt trains (DB: winners end with
        # ~4 trains left, losers ~18).
        opp_min_trains = min(
            (p.get("trains", 45) for opid, p in state["player_states"].items() if opid != pid),
            default=45)
        threshold = _claim_threshold(owing, trains, opp_min_trains)
        if best_rid is not None and best_score >= threshold:
            return "claim", {"route_id": best_rid, "cards": best_cards}

        # No worthwhile route to claim: if our network is large and tickets are
        # done, draw new tickets (likely already-connected free points) instead
        # of just drawing cards. This is free tempo — we weren't going to build.
        if (_DRAW_TICKETS_ENABLED
                and not owing
                and trains >= _DRAW_TICKET_MIN_TRAINS
                and len(my_cities) >= _DRAW_TICKET_MIN_CITIES
                and len(state.get("dest_deck", [])) >= 3):
            return "draw_tickets", {}

    return _draw_toward(face_up, closest or plan_routes, draw_step)


# ---------------------------------------------------------------------------
# shittér-bot (shitter_bot_2) — the rival
# ---------------------------------------------------------------------------
# Plays EXACTLY like shitter-bot, but quietly sabotages one target (by default
# "fishy"). It cheats: it reads the target's PRIVATE hand + destinations to
# know precisely which routes he still needs and which colours he's hunting. The
# camouflage rule is strict — it only ever acts on that knowledge when the move
# also looks like ordinary strong play, so nothing it does stands out:
#   * Colour-snipe (Lever 1): only when the normal brain would draw BLIND anyway
#     (i.e. we had no colour of our own to chase). Taking a face-up card then is a
#     completely normal pickup; we just pick the colour that hurts the target most.
#   * Blocking claim (Lever 2): only once OUR OWN tickets are secured (never
#     self-sabotage), only on a fresh turn where the brain merely wanted to draw,
#     and only for a genuinely damaging AND affordable route — the same
#     opportunistic blocking a strong player already does, just aimed. A small
#     random pass keeps it from being a perfect, tell-tale pattern.

_SABOTAGE_TARGETS = [s.strip().lower() for s in
                     os.environ.get("SHITTER2_TARGETS", "fish,kmit").split(",") if s.strip()]
_SNIPE_MIN    = float(os.environ.get("SHITTER2_SNIPE_MIN", "1.0"))
_BLOCK_MIN    = float(os.environ.get("SHITTER2_BLOCK_MIN", "6.0"))
_BLOCK_COST_W = float(os.environ.get("SHITTER2_BLOCK_COST_W", "1.0"))
_BLOCK_SKIP   = float(os.environ.get("SHITTER2_BLOCK_SKIP", "0.15"))


def _find_target(state, pid):
    """pid of the opponent we're out to get (name matches a target token), or None.
    Ties broken toward whoever is closest to winning (score + trains spent)."""
    best, best_score = None, -1.0
    for opid, p in state["player_states"].items():
        if opid == pid:
            continue
        name = str(p.get("name", "")).lower()
        if any(tok in name for tok in _SABOTAGE_TARGETS):
            sc = p.get("route_score", 0) + (45 - p.get("trains", 45))
            if sc > best_score:
                best_score, best = sc, opid
    return best


def _target_incomplete_paths(state, target):
    """[(ticket_points, [needed_route_id, ...])] for the target's still-incomplete,
    reachable tickets — from his ACTUAL (hidden) tickets. This is the cheat: we
    know exactly which routes he still needs, not just a guess from the board."""
    tps     = state["player_states"].get(target, {})
    claimed = state["claimed_routes"]
    adj     = _available_adj(state, target)
    out = []
    for tid in tps.get("tickets", []):
        t = TICKET_BY_ID.get(tid)
        if not t or logic.is_path_connected(state, target, t["city1"], t["city2"]):
            continue
        path = _path_route_ids(adj, t["city1"], t["city2"])
        if not path:
            continue
        need = [rid for rid in path if str(rid) not in claimed]
        if need:
            out.append((t.get("points", 0), need))
    return out


def _target_wanted_colors(state, target):
    """Colours the target still has to COLLECT to finish his tickets (route need
    minus what he already hoards). Peeks at his hidden hand + tickets."""
    thand  = state["player_states"].get(target, {}).get("hand", {})
    wanted = {}
    for _pts, need in _target_incomplete_paths(state, target):
        for rid in need:
            col = ROUTE_BY_ID[rid].get("color", "gray")
            if col in ("gray", "locomotive"):
                continue                      # any colour works — can't deny it
            wanted[col] = wanted.get(col, 0.0) + ROUTE_BY_ID[rid]["length"]
    for col in list(wanted):
        wanted[col] = max(0.0, wanted[col] - 0.5 * thand.get(col, 0))
    return wanted


def _snipe_target_color(state, target, face_up):
    """Grab the face-up card of the colour the target needs MOST, denying it to
    him. Only called on an otherwise-blind draw, so it's free tempo and looks
    exactly like a normal face-up pickup."""
    wanted = _target_wanted_colors(state, target)
    if not wanted:
        return None
    best_i, best_w = None, 0.0
    for i, card in enumerate(face_up):
        if card and card != "locomotive":
            w = wanted.get(card, 0.0)
            if w > best_w:
                best_w, best_i = w, i
    if best_i is not None and best_w >= _SNIPE_MIN:
        return "draw_face_up", {"slot": best_i}
    return None


def _best_target_block(state, pid, target, hand, trains, n_players, claimed):
    """Most damaging AFFORDABLE route on the target's ticket paths, valued net of
    our own train cost and bonused when it also touches our network (so it reads as
    an ordinary self-serving claim). Returns claim params, or None."""
    need_w = {}
    for pts, need in _target_incomplete_paths(state, target):
        for rid in need:
            need_w[rid] = need_w.get(rid, 0.0) + pts + ROUTE_BY_ID[rid]["length"]
    if not need_w:
        return None
    sorted_hand = sorted(((c, n) for c, n in hand.items() if c != "locomotive" and n > 0),
                         key=lambda x: -x[1])
    locos     = hand.get("locomotive", 0)
    my_cities = _my_cities(claimed, pid)
    best_rid, best_cards, best_val = None, None, 0.0
    for rid, w in need_w.items():
        route = ROUTE_BY_ID[rid]
        cards = _can_claim_fast(hand, route, trains, n_players, claimed, pid,
                                sorted_hand, locos)
        if cards is None:
            continue
        length = route["length"]
        val = w - _BLOCK_COST_W * length
        if route["city1"] in my_cities or route["city2"] in my_cities:
            val += 3.0                         # double-duty: also grows our network
        if length <= 2:
            val += 1.0                         # cheap for us, still severs his plan
        if val > best_val:
            best_val, best_rid, best_cards = val, rid, cards
    if best_rid is not None and best_val >= _BLOCK_MIN:
        return {"route_id": best_rid, "cards": best_cards}
    return None


def _v2_owing(state, pid):
    """Do we still owe a reachable ticket of our own? (Never sabotage while owing.)"""
    tps = state["player_states"].get(pid, {})
    adj = None
    for tid in tps.get("tickets", []):
        t = TICKET_BY_ID.get(tid)
        if not t or logic.is_path_connected(state, pid, t["city1"], t["city2"]):
            continue
        if adj is None:
            adj = _available_adj(state, pid)
        if _path_route_ids(adj, t["city1"], t["city2"]):
            return True
    return False


def shitter_policy_v2(state, pid):
    """shittér-bot: identical to shitter-bot, with quiet, low-suspicion sabotage of
    one target layered on top."""
    action, params = shitter_policy(state, pid)
    target = _find_target(state, pid)
    if target is None:
        return action, params                  # target not in this game — pure shitter-bot

    draw_step = state.get("draw_step", 0)
    face_up   = state["face_up"]

    # Lever 2 — opportunistic blocking claim (see module note for the safety rules).
    if (action in ("draw_blind", "draw_face_up", "draw_tickets")
            and draw_step == 0
            and not _v2_owing(state, pid)
            and random.random() > _BLOCK_SKIP):
        ps = state["player_states"].get(pid, {})
        block = _best_target_block(state, pid, target, ps.get("hand", {}),
                                   ps.get("trains", 45),
                                   len(state.get("turn_order", [])),
                                   state["claimed_routes"])
        if block is not None:
            return "claim", block

    # Lever 1 — snipe the target's most-wanted face-up colour on an otherwise-blind draw.
    if action == "draw_blind":
        snipe = _snipe_target_color(state, target, face_up)
        if snipe is not None:
            return snipe

    return action, params

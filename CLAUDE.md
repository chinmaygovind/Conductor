# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full multiplayer online **Ticket to Ride** with two maps (North America + Europe).
Flask + Flask-SocketIO backend, vanilla JS + hand-traced SVG frontend, SQLite/PostgreSQL.
Includes accounts, Google OAuth, ELO ranking, friends, leaderboard, game replays, and an
admin DB browser — not just the game itself.

- **Run locally:** `python app.py` → http://localhost:5001 (eventlet dev server; `PORT` env overrides)
- **Production:** http://52.54.184.133 (EC2, Ubuntu) — auto-deploys from `main` on every push

## Commands

```bash
python app.py                          # run locally on :5001
pytest tests/                          # full suite (pytest.ini adds -v --tb=short)
pytest tests/test_bot.py               # one file
pytest tests/test_bot.py::test_name    # one test
pytest tests/ -x -q                    # stop at first failure (what the pre-push hook runs)
sh scripts/install-hooks.sh            # install pre-push hook that runs tests before pushing to main
```

- **Python 3.14 dev / 3.11 CI.** Only stdlib + `requirements.txt` — no build step, no JS bundler.
- Tests need `SECRET_KEY` set (CI passes it; `tests/conftest.py` sets a default + an isolated
  `instance/test_tickettoride.db` and forces `CLAUDE_BOT_ITER=0` so the slow ISMCTS bot is skipped).
- No linter is configured.

## Architecture

### Request / event flow
`app.py` (2100+ lines) holds **all** HTTP routes (32 of them) and **all** SocketIO handlers.
Gameplay happens over sockets; HTTP routes cover auth, accounts, lobbies, replay, and admin.
Every game mutation follows the same shape: a socket handler → calls a pure function in
`game_logic.py` that mutates the state dict in place → `app.py` saves `state_json` back to the DB
→ `_broadcast_state()` emits to clients → `_kickoff_bots()` advances any bot turns.

### Game state shape
All game state lives in `Game.state_json` (a JSON text column). `game_logic.py` mutates it in place;
`app.py` persists it. `state["map"]` (`"usa"` or `"europe"`) is set at `init_game_state` and every
map-aware branch reads it.
```python
{
  "map": "usa",               # or "europe" — selects data module + rule variants
  "deck": [...], "face_up": [...],   # 5 face-up cards (None = empty slot)
  "dest_deck": [...],
  "claimed_routes": {},       # {route_id_str: player_id_str}
  "player_states": {
    "pid": {"hand": {"red": 2, ...}, "tickets": [...], "pending_tickets": [],
            "trains": 45, "route_score": 0}
  },
  "current_player_id": "...",
  "phase": "initial_tickets | main | final_round | ended",
  "draw_step": 0,             # 0 = fresh turn, 1 = first card drawn
  "turn_order": [...], "action_log": [...],
}
```

### Two maps share one engine
`game_logic.py` is map-agnostic and dispatches on `state["map"]` via `_map_data()`:
- **USA:** `game_data_na.py` (36 cities, 99 routes, 30 tickets), `route_segments.py` for SVG.
- **Europe:** `game_data_europe.py`, `route_segments_europe.py`, plus Europe-only mechanics —
  **tunnels** (`resolve_tunnel` socket event / `bot_resolve_tunnel`), **stations**
  (`place_station`), and **ferries**. When touching game rules, check whether a branch is
  Europe-only before assuming it applies to both maps.

### Double-route rule
In ≤3-player games, only ONE side of a double route can be claimed by anyone. Enforced in
`game_logic.claim_route`; bot code must respect it.

### Bot system (`bot.py`)
Bots are `Player` rows whose `session_key` starts with `"bot_"`. Public API:
`bot_turn(state, pid, personality)`, `bot_keep_initial_tickets(...)`, `bot_resolve_tunnel(...)`.
Personalities (see `PERSONALITIES` list): `fish_bot`, `chin_bot`, `rocket_bot`, `ticket_bot`,
`chaos_bot`, `greedy_bot`, `blocking_bot`, `claude_bot`, `shitter_bot`.
- `claude_bot` — ISMCTS engine in `claude-bot/`, entered via `bot.py:_claude_turn` →
  `claude-bot/bot_entry.py`. Iteration count is `CLAUDE_BOT_ITER` (default **0** = instant
  `heuristic`/`ticket_path_policy`; set `>0` to enable full ISMCTS search). See `claude-bot/README.md`.
- `shitter_bot` — sophisticated instant policy in `shitter-bot/policy.py`, loaded lazily by
  `bot.py:_shitter_turn`. Completes tickets, keeps one continuous network for the longest-path
  bonus, and blocks opponent bridge routes when free.
- `bot_chat.py` — bot trash-talk / chat reactions.

**Bot execution:** after each action `_kickoff_bots(game, code)` runs bots until the current player
is human. In production this is a detached `eventlet.spawn_n` greenlet (so state flushes to clients
first); under `TESTING` it runs **synchronously** (a background greenlet would outlive the test and
commit on a stale session). Keep this branch intact when editing bot orchestration.

### Socket broadcast
`_broadcast_state(game, code)` emits two events after every action:
1. `game_state` → the player's **personal** room (includes private hand + tickets)
2. `game_state_update` → the **game-code** room (public data: claimed_routes, face_up, scores)

The client merges `game_state_update` carefully so it never clobbers private hand/ticket data.

### Accounts, ELO & social (`models.py`)
- `User` — username/email, optional password hash **or** `google_id`, notify flags, and stats
  (`elo` with tiers via `elo_tier`, games/wins, `total_points`). Guests get a session-only identity.
- `Game` — `code`, `status`, `map_variant`, `state_json`, and `replay_json` (append-only action log
  powering `/replay/<code>`).
- `Player` — one row per seat, linked to a `User` when logged in; `session_key` ties a browser
  session (or `bot_*`) to a seat.
- `Friendship`, `GameResult` — social graph and per-user finished-game history (ELO before/after).
- **A guest is not signed in, and `/login` must stay reachable for one.**
  `login_page` used to redirect anybody with a `guest_name` to the lobbies, so
  the nav's CREATE ACCOUNT was the one link that did nothing - a guest who
  decided to make a real account was sent back where they started. Only
  `get_current_user()` is redirected now; `?register=1` (which the nav already
  carried) still opens the register tab.
- **Auth routes:** `/login`, `/register`, `/guest`, `/auth/google[/callback]`. Email (SMTP) and
  SMS (Twilio) notifications are optional, configured via env; absent creds just disable them.
- **Other surfaces:** `/leaderboard`, `/account`, `/account/history`, `/replay/<code>`, and an
  `/admin` DB browser (view/edit/delete rows) — treat admin routes as trusted/internal.

### Frontend
`static/js/game.js` (2200+ lines) does everything client-side: renders an SVG board overlay on a
board image (viewBox `0 0 1024 683`), handles socket events, modals, and UI. Route rendering uses
explicit `(cx, cy, angle)` segment data from `route_segments*.py` (passed as `BOARD_DATA`), falling
back to linear interpolation. Templates in `templates/` inject per-game globals (`GAME_CODE`,
`MY_PLAYER_ID`, `MY_COLOR`, `BOARD_DATA`). No frontend build/test tooling.

### Config & secrets
Env is loaded from `.env` (gitignored). Keys: `SECRET_KEY`, `PORT`, `SITE_URL`, `DATABASE_URL`
(SQLite default → `instance/tickettoride.db`; set for PostgreSQL), `SMTP_*`, `TWILIO_*`, and
`CLAUDE_BOT_ITER`. Google OAuth client creds are stored in the DB (set via `/auth/google/setup`),
not env.

## Deployment

Push to `main` → `.github/workflows/deploy.yml` runs `pytest`, then SSHes to EC2, does
`git reset --hard origin/main`, `pip install -r requirements.txt`, and restarts the systemd service.
Production runtime: `gunicorn --worker-class eventlet -w 1` behind nginx (`deploy/`).

- **Single gunicorn worker is required** — socket rooms live in in-process memory. Don't add workers
  without a message queue (Redis + `SocketIO(message_queue=...)`).
- **SQLite on EC2** — data is on instance disk; lost if the instance is terminated. No HTTPS currently.
- `app.py` uses `async_mode="eventlet"` in both local and production.

## Notes on stale docs

`claude-bot/README.md` and `claude-bot/HANDOFF.md` predate the current setup (they describe a
multi-branch model and a `game_data.py` that no longer exist). Reality: `main` is the single
deployed branch, map data lives in `game_data_na.py` / `game_data_europe.py`, and `aws-deploy` is
legacy/stale. Trust the code and this file over those docs.

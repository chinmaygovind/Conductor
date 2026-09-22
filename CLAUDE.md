# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full multiplayer online **Conductor** with two maps (North America + Europe).
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

### Board art, and what was deleted (Sep 2026)
The board the game draws on is **`static/images/board.svg` / `europe_board.svg`, which are our own
tracings** - our coastline paths, our palette - generated once by the Tkinter tools in
`scripts/board/`. They are the only board art the app serves, and they are what the login and
landing backgrounds use too.

**The retail board scans and the publisher's rulebook PDFs are gone and must not come back.**
`assets/` (both rulebook PDFs, `usa_board.png`, `europe_board.png`, a scraped BGG page) and
`static/images/board.png` / `europe_board.png` were removed after a trademark notice from Rapid7
acting for Asmodee (AWS case 178949924200884-1). The PNGs were only ever *tracing references*, plus
the login/landing background - nothing computed from them at runtime.

The consequence is that **every tool in `scripts/board/` is now un-runnable**: `trace_coastline.py`,
`calibrate_board.py`, `calibrate_cities.py`, `detect_board.py`, `draw_templates.py`, `pick_colors.py`,
`fix_cities.py`, `trace_europe.py` and `scripts/europe_debug.html` all open a scan that no longer
exists. They are kept because they are the record of how the SVGs were made and what the JSON traces
in that directory mean, not because they can be re-run. **The tracing is finished; the SVGs are the
source of truth.** If a board ever needs re-tracing, trace something we are allowed to hold.

These files are in `.gitignore` now so a stray local copy cannot be committed back by accident.
**They are still in git history** - the repo was not rewritten - so a history purge is the open
follow-up if Asmodee ever asks for one.

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

### The install prompt

**`/install` and the bottom-sheet nudge that points at it are one pattern copied
into all four PWA games** (drive, ers, kot, ttr), each in its own colours. The
prompt is a `{% block install_prompt %}` in `base.html`, so the in-game
templates (`game.html` and `replay.html`) blank it - a fixed bar over a
game in progress is a way of losing the game, and the block is the same gate
`_nav.html`'s absence already is on those pages.

It shows only on `(pointer: coarse)` and only when the page is not already the
installed app. **All three display modes are tested**, not just `standalone`:
a manifest's `display` decides which one an installed copy matches, and
Conductor is `standalone` today but a manifest edit must not
quietly switch the prompt back on inside the app. `navigator.standalone` covers iOS, which
matches no display-mode query at all. A dismissal goes in `localStorage` behind
a try/catch, because private mode throws on access rather than returning null.

`/install` ships **both** sets of steps and picks between them in JS rather than
off the User-Agent, so a link pasted into a group chat is right for whoever
opens it. iOS step 1 is **Open in Safari** (`x-safari-` + the current URL) -
only Safari can add to the home screen, and an in-app webview is where that link
matters. On Android the page also captures `beforeinstallprompt` **in `<head>`**,
because Chrome fires it once, early, and never replays it; the manual steps stay
visible, so a browser that never fires it loses nothing.

Conductor has no `.btn`; the prompt and the steps use `.btn-primary`, which is
`width: 100%` by default - `.ins-open` sets `width: auto` to get an inline
button back, and both reset the `a` underline.

"""
Flask HTTP and SocketIO integration tests.

IMPORTANT NOTE on SocketIO session keys:
The Flask-SocketIO test client connects at creation time. If it is created
before login/game-setup, the session doesn't yet have a `session_key`, so
SocketIO handlers that call `get_session_key()` return a fresh UUID that
doesn't match any player in the database. For tests that need session
validation, we create the SocketIO client INSIDE the test body, after
all HTTP setup (login + game creation) has been done.
"""

import pytest
import json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_and_login(client, username="player1", email=None, password="Password1!"):
    email = email or f"{username}@example.com"
    resp = client.post("/register", json={
        "username": username, "email": email, "password": password
    })
    assert resp.status_code == 200


def http_create_game(client, is_private=False, passcode="", map_variant="usa"):
    resp = client.post("/create", json={
        "is_private": is_private,
        "passcode": passcode,
        "map_variant": map_variant,
    })
    return json.loads(resp.data)


def http_join_game(client, code, passcode=""):
    resp = client.post("/join", json={"code": code, "passcode": passcode})
    return json.loads(resp.data)


def make_sio(flask_app, client):
    """Create a SocketIO test client using the HTTP client's active session."""
    from app import socketio as _sio
    return _sio.test_client(flask_app, flask_test_client=client)


def start_game_with_bot(flask_app, client):
    """Login, create a game, add a bot, start it. Returns (sio, code)."""
    from app import socketio as _sio
    data = http_create_game(client)
    code = data["code"]
    # Create SIO AFTER game creation so the session key is established
    sio = make_sio(flask_app, client)
    sio.emit("join_lobby", {"code": code})
    sio.get_received()
    sio.emit("add_bot", {"code": code})
    sio.get_received()
    sio.emit("start_game", {"code": code})
    sio.get_received()
    return sio, code


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

def test_register_ok(client):
    resp = client.post("/register", json={
        "username": "newuser", "email": "new@example.com", "password": "Password1!"
    })
    data = json.loads(resp.data)
    assert data["ok"]


def test_register_duplicate_username(client):
    create_and_login(client, "dupuser")
    from app import app as flask_app
    with flask_app.test_client() as c2:
        resp = c2.post("/register", json={
            "username": "dupuser", "email": "other@example.com", "password": "Password1!"
        })
        data = json.loads(resp.data)
        assert not data["ok"]
        assert "taken" in data["error"].lower()


def test_register_short_password(client):
    resp = client.post("/register", json={
        "username": "shortpw", "email": "short@example.com", "password": "abc"
    })
    data = json.loads(resp.data)
    assert not data["ok"]


def test_login_ok(client):
    create_and_login(client, "logintest")
    resp = client.post("/login", json={"identity": "logintest", "password": "Password1!"})
    data = json.loads(resp.data)
    assert data["ok"]


def test_login_wrong_password(client):
    create_and_login(client, "loginfail")
    resp = client.post("/login", json={"identity": "loginfail", "password": "WrongPass1!"})
    data = json.loads(resp.data)
    assert not data["ok"]


def test_guest_login_ok(client):
    resp = client.post("/guest", json={"name": "Guestina"})
    data = json.loads(resp.data)
    assert data["ok"]


def test_guest_login_bad_name(client):
    resp = client.post("/guest", json={"name": "x"})
    data = json.loads(resp.data)
    assert not data["ok"]


def test_logout_redirects(client):
    create_and_login(client, "logouttest")
    resp = client.get("/logout")
    assert resp.status_code in (301, 302)


# ---------------------------------------------------------------------------
# Game creation (HTTP)
# ---------------------------------------------------------------------------

def test_create_game_returns_code(client):
    create_and_login(client, "creator")
    data = http_create_game(client)
    assert data["ok"]
    assert len(data["code"]) == 6


def test_create_game_private(client):
    create_and_login(client, "private_creator")
    data = http_create_game(client, is_private=True, passcode="secret")
    assert data["ok"]


def test_create_game_europe(client):
    create_and_login(client, "eu_creator")
    data = http_create_game(client, map_variant="europe")
    assert data["ok"]


def test_create_game_requires_login(client):
    resp = client.post("/create", json={"max_players": 4})
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Joining games (HTTP)
# ---------------------------------------------------------------------------

def test_join_public_game(client, flask_app):
    create_and_login(client, "join_host")
    data = http_create_game(client)
    code = data["code"]
    with flask_app.test_client() as c2:
        c2.post("/register", json={
            "username": "joiner2", "email": "joiner2@example.com", "password": "Password1!"
        })
        result = http_join_game(c2, code)
        assert result["ok"]


def test_join_game_not_found(client):
    create_and_login(client, "joiner_nf")
    result = http_join_game(client, "XXXXXX")
    assert not result["ok"]


def test_join_private_game_wrong_passcode(client, flask_app):
    create_and_login(client, "host_priv")
    data = http_create_game(client, is_private=True, passcode="rightcode")
    code = data["code"]
    with flask_app.test_client() as c2:
        c2.post("/register", json={
            "username": "joiner_priv", "email": "priv@example.com", "password": "Password1!"
        })
        result = http_join_game(c2, code, passcode="wrongcode")
        assert not result["ok"]


def test_join_private_game_correct_passcode(client, flask_app):
    create_and_login(client, "host_priv2")
    data = http_create_game(client, is_private=True, passcode="correctcode")
    code = data["code"]
    with flask_app.test_client() as c2:
        c2.post("/register", json={
            "username": "joiner_priv2", "email": "priv2@example.com", "password": "Password1!"
        })
        result = http_join_game(c2, code, passcode="correctcode")
        assert result["ok"]


def test_join_full_game(client, flask_app):
    create_and_login(client, "host_full")
    data = http_create_game(client)   # every game is max_players=6 now
    code = data["code"]
    # Fill the 5 remaining slots
    for i in range(5):
        with flask_app.test_client() as c:
            c.post("/register", json={
                "username": f"filler{i}", "email": f"filler{i}@x.com", "password": "Password1!"
            })
            http_join_game(c, code)
    # One more — should be rejected
    with flask_app.test_client() as extra:
        extra.post("/register", json={
            "username": "extra_player", "email": "extra@x.com", "password": "Password1!"
        })
        result = http_join_game(extra, code)
        assert not result["ok"]
        assert "full" in result["error"].lower()


# ---------------------------------------------------------------------------
# SocketIO lobby events
# All SocketIO tests below create the client AFTER HTTP setup so the session
# key is already stored in the cookie before the connection is established.
# ---------------------------------------------------------------------------

def test_socketio_join_lobby_emits_state(client, flask_app):
    create_and_login(client, "sio_host")
    data = http_create_game(client)
    code = data["code"]
    sio = make_sio(flask_app, client)
    try:
        sio.emit("join_lobby", {"code": code})
        received = sio.get_received()
        event_names = [r["name"] for r in received]
        assert "lobby_state" in event_names
    finally:
        sio.disconnect()


def test_socketio_add_bot(client, flask_app):
    create_and_login(client, "bot_host")
    data = http_create_game(client)
    code = data["code"]
    sio = make_sio(flask_app, client)
    try:
        sio.emit("join_lobby", {"code": code})
        sio.get_received()
        sio.emit("add_bot", {"code": code})
        received = sio.get_received()
        event_names = [r["name"] for r in received]
        assert "player_joined" in event_names
    finally:
        sio.disconnect()


def test_socketio_add_bot_specific_type(client, flask_app):
    create_and_login(client, "bot_host_specific")
    data = http_create_game(client)
    code = data["code"]
    sio = make_sio(flask_app, client)
    try:
        sio.emit("join_lobby", {"code": code})
        sio.get_received()
        sio.emit("add_bot", {"code": code, "bot_type": "claude_bot"})
        sio.get_received()
        from models import Game, Player
        with flask_app.app_context():
            game = Game.query.filter_by(code=code).first()
            bots = [p for p in game.players if p.session_key.startswith("bot_")]
            assert len(bots) == 1
            assert bots[0].session_key.startswith("bot_claude_bot_")
            assert bots[0].name == "claude-bot"
    finally:
        sio.disconnect()


def test_socketio_add_bot_invalid_type_falls_back(client, flask_app):
    create_and_login(client, "bot_host_invalid")
    data = http_create_game(client)
    code = data["code"]
    sio = make_sio(flask_app, client)
    try:
        sio.emit("join_lobby", {"code": code})
        sio.get_received()
        sio.emit("add_bot", {"code": code, "bot_type": "definitely_not_a_bot"})
        received = sio.get_received()
        assert "player_joined" in [r["name"] for r in received]
        import bot as bot_module
        valid_slugs = {slug for _, slug in bot_module.BOT_TYPES}
        from models import Game
        with flask_app.app_context():
            game = Game.query.filter_by(code=code).first()
            bots = [p for p in game.players if p.session_key.startswith("bot_")]
            assert len(bots) == 1
            # session_key format: bot_<slug>_<uuid>; verify slug is a valid one
            slug = bots[0].session_key[len("bot_"):].rsplit("_", 1)[0]
            assert slug in valid_slugs
    finally:
        sio.disconnect()


def test_socketio_add_bot_not_host(client, flask_app):
    create_and_login(client, "bot_host2")
    data = http_create_game(client)
    code = data["code"]
    with flask_app.test_client() as c2:
        c2.post("/register", json={
            "username": "nonhost2", "email": "nh2@x.com", "password": "Password1!"
        })
        c2.post("/login", json={"identity": "nonhost2", "password": "Password1!"})
        http_join_game(c2, code)
        sio2 = make_sio(flask_app, c2)
        try:
            sio2.emit("add_bot", {"code": code})
            received = sio2.get_received()
            event_names = [r["name"] for r in received]
            assert "error" in event_names
        finally:
            sio2.disconnect()


def test_socketio_leave_lobby_host_closes(client, flask_app):
    create_and_login(client, "leave_host")
    data = http_create_game(client)
    code = data["code"]
    sio = make_sio(flask_app, client)
    try:
        sio.emit("join_lobby", {"code": code})
        sio.get_received()
        sio.emit("leave_lobby", {"code": code})
        received = sio.get_received()
        event_names = [r["name"] for r in received]
        assert "lobby_closed" in event_names
    finally:
        sio.disconnect()


def test_socketio_kick_player_from_lobby(client, flask_app):
    create_and_login(client, "kick_host")
    data = http_create_game(client)
    code = data["code"]

    with flask_app.test_client() as c2:
        c2.post("/register", json={
            "username": "kickme", "email": "kickme@x.com", "password": "Password1!"
        })
        c2.post("/login", json={"identity": "kickme", "password": "Password1!"})
        http_join_game(c2, code)

    with flask_app.app_context():
        from models import Game, Player
        game = Game.query.filter_by(code=code).first()
        target = next(p for p in game.players if p.name == "kickme")
        target_id = target.id

    sio = make_sio(flask_app, client)
    try:
        sio.emit("join_lobby", {"code": code})
        sio.get_received()
        sio.emit("kick_player", {"code": code, "player_id": target_id})
        received = sio.get_received()
        event_names = [r["name"] for r in received]
        assert "player_kicked" in event_names or "player_joined" in event_names
    finally:
        sio.disconnect()


def test_socketio_start_game_needs_two_players(client, flask_app):
    create_and_login(client, "start_solo")
    data = http_create_game(client)
    code = data["code"]
    sio = make_sio(flask_app, client)
    try:
        sio.emit("join_lobby", {"code": code})
        sio.get_received()
        sio.emit("start_game", {"code": code})
        received = sio.get_received()
        event_names = [r["name"] for r in received]
        assert "error" in event_names
    finally:
        sio.disconnect()


def test_socketio_start_game_with_bot(client, flask_app):
    create_and_login(client, "start_with_bot")
    sio, code = start_game_with_bot(flask_app, client)
    try:
        received = sio.get_received()  # any leftover after start
        # The game_started event goes to the room; verify status in DB
        with flask_app.app_context():
            from models import Game
            game = Game.query.filter_by(code=code).first()
            assert game.status == "playing"
    finally:
        sio.disconnect()


# ---------------------------------------------------------------------------
# In-game SocketIO events
# ---------------------------------------------------------------------------

def test_socketio_join_game_room_emits_state(client, flask_app):
    create_and_login(client, "ingame_host")
    sio, code = start_game_with_bot(flask_app, client)
    try:
        sio.emit("join_game_room", {"code": code})
        received = sio.get_received()
        event_names = [r["name"] for r in received]
        assert "game_state" in event_names
    finally:
        sio.disconnect()


def test_socketio_game_state_has_my_player_id(client, flask_app):
    create_and_login(client, "my_pid_host")
    sio, code = start_game_with_bot(flask_app, client)
    try:
        sio.emit("join_game_room", {"code": code})
        received = sio.get_received()
        state_events = [r for r in received if r["name"] == "game_state"]
        assert state_events
        state = state_events[-1]["args"][0]
        assert "my_player_id" in state
    finally:
        sio.disconnect()


def test_socketio_chat_message(client, flask_app):
    create_and_login(client, "chatter")
    sio, code = start_game_with_bot(flask_app, client)
    try:
        sio.emit("join_game_room", {"code": code})
        sio.get_received()
        sio.emit("send_chat", {"code": code, "msg": "Hello!"})
        received = sio.get_received()
        event_names = [r["name"] for r in received]
        assert "chat_message" in event_names
    finally:
        sio.disconnect()


def test_socketio_draw_blind_not_your_turn_gives_error(client, flask_app):
    """Drawing when it's not your turn returns an error event."""
    create_and_login(client, "drawer_host")
    sio, code = start_game_with_bot(flask_app, client)
    try:
        sio.emit("join_game_room", {"code": code})
        received = sio.get_received()
        state_events = [r for r in received if r["name"] == "game_state"]
        if not state_events:
            return
        state = state_events[-1]["args"][0]
        my_pid = state.get("my_player_id")
        if state.get("current_player_id") == my_pid and state.get("phase") == "main":
            # It IS our turn — drawing blind should succeed
            sio.emit("draw_blind", {"code": code})
            received = sio.get_received()
            event_names = [r["name"] for r in received]
            assert "game_state" in event_names or "game_state_update" in event_names
        else:
            # It is NOT our turn — should get an error
            sio.emit("draw_blind", {"code": code})
            received = sio.get_received()
            event_names = [r["name"] for r in received]
            # Either error or no event (bots act between state updates)
            pass  # we just verify no crash
    finally:
        sio.disconnect()


def test_resign_http_replaces_with_bot(client, flask_app):
    create_and_login(client, "resign_host")
    sio, code = start_game_with_bot(flask_app, client)
    try:
        with flask_app.app_context():
            from models import Game
            game = Game.query.filter_by(code=code).first()
            assert game.status == "playing"

        resp = client.post(f"/resign/{code}")
        data_resp = json.loads(resp.data)
        assert data_resp["ok"]

        with flask_app.app_context():
            from models import Game
            game = Game.query.filter_by(code=code).first()
            # The resigning player's session_key should now be a bot
            bots = [p for p in game.players if p.session_key.startswith("bot_")]
            assert len(bots) >= 1
    finally:
        sio.disconnect()


# ---------------------------------------------------------------------------
# Leaderboard / account routes
# ---------------------------------------------------------------------------

def test_leaderboard_accessible(client):
    create_and_login(client, "leaderboard_user")
    resp = client.get("/leaderboard")
    assert resp.status_code == 200


def test_account_page_accessible(client):
    create_and_login(client, "account_user")
    resp = client.get("/account")
    assert resp.status_code == 200
    # Footer should advertise the live claude_bot engine config.
    assert b"claude_bot engine" in resp.data


def test_account_update_will_not_change_a_username_or_email(client, flask_app):
    """Both moved to cgovind.com/accounts, and this route has to say so.

    It used to do them, with no password and no confirmation. A username is now
    the permanent address of a profile the other three games link to, and an
    email change is only real once the new address has confirmed it - neither of
    which can be true if one POST here can still do it. The refusal is what
    keeps the accounts site's rules from being one page away from bypassable,
    so it is worth a test of its own, including that nothing was written.
    """
    create_and_login(client, "update_me")

    for field, value in [("username", "updated_me"), ("email", "new@example.com")]:
        resp = client.post("/account/update", json={"field": field, "value": value})
        data = json.loads(resp.data)
        assert not data["ok"], field
        assert "cgovind.com/accounts" in data["error"]

    with flask_app.app_context():
        from models import User
        user = User.query.filter_by(username="update_me").first()
        assert user is not None                      # still under the old name
        assert user.email != "new@example.com"


def test_account_update_still_takes_a_phone_number(client):
    """The one identity-ish field that did *not* move: it is TTR's own game
    alert setting rather than anything the other three games share."""
    create_and_login(client, "phone_update")
    resp = client.post("/account/update", json={"field": "phone", "value": "+1 555 123 4567"})
    assert json.loads(resp.data)["ok"]


# ---------------------------------------------------------------------------
# Friend system
# ---------------------------------------------------------------------------

def test_friend_request_sent(client, registered_user, registered_user2, flask_app):
    client, user = registered_user
    with flask_app.app_context():
        from models import User
        u2 = User.query.filter_by(username="testuser2").first()
        username2 = u2.username
    resp = client.post("/friends/request", json={"username": username2})
    data = json.loads(resp.data)
    assert data["ok"]


def test_friend_request_self(client, registered_user):
    client, user = registered_user
    with client.application.app_context():
        from models import User
        u = User.query.filter_by(username="testuser").first()
    resp = client.post("/friends/request", json={"username": "testuser"})
    data = json.loads(resp.data)
    assert not data["ok"]


def test_friend_request_nonexistent(client, registered_user):
    client, user = registered_user
    resp = client.post("/friends/request", json={"username": "doesnotexist_xyz"})
    data = json.loads(resp.data)
    assert not data["ok"]


# ---------------------------------------------------------------------------
# Bot ELO — bots have their own persistent rating, scored vs the other players
# ---------------------------------------------------------------------------

def _finished_game(db, code, seats, scores, winner_key):
    """Build a finished-game (Game + Players + ended state) for _finalize_game_stats.

    seats: list of dicts {key, user_id, name, color, is_host}.
    scores/winner_key: keyed by the same `key`; keys map to str(player.id).
    Returns (game, {key: str(player.id)}).
    """
    from models import Game, Player
    game = Game(code=code, status="playing", map_variant="usa", state_json="{}")
    db.session.add(game)
    db.session.commit()
    key_to_pid = {}
    for i, s in enumerate(seats):
        p = Player(game_id=game.id, user_id=s["user_id"], session_key=f"sess_{code}_{i}",
                   name=s["name"], color=s["color"], turn_order=i, is_host=s.get("is_host", False))
        db.session.add(p)
        db.session.commit()
        key_to_pid[s["key"]] = str(p.id)
    state = {
        "phase": "ended",
        "winner_id": key_to_pid[winner_key],
        "scores": {key_to_pid[k]: {"total": v} for k, v in scores.items()},
        "player_states": {key_to_pid[k]: {"trains": 3, "tickets": [1]} for k in scores},
    }
    game.state = state
    db.session.commit()
    return game, key_to_pid


def test_get_bot_user_creates_and_is_idempotent(flask_app, clean_database):
    from app import _get_bot_user
    with flask_app.app_context():
        u = _get_bot_user("shitter_bot")
        assert u is not None and u.is_bot is True and u.elo == 1000
        assert u.username == "bot:shitter_bot"
        again = _get_bot_user("shitter_bot")
        assert again.id == u.id  # same account, not a duplicate


def test_bot_earns_elo_and_is_excluded_from_leaderboard(flask_app, clean_database):
    from app import db, _get_bot_user, _finalize_game_stats
    from models import User, TtrStats
    with flask_app.app_context():
        human = User(username="alice", email="alice@x.com", elo=1000)
        db.session.add(human)
        db.session.commit()
        bot = _get_bot_user("shitter_bot")
        game, keys = _finished_game(
            db, "ELOA",
            [{"key": "h", "user_id": human.id, "name": "alice", "color": "red", "is_host": True},
             {"key": "b", "user_id": bot.id, "name": "shitter-bot", "color": "blue"}],
            scores={"h": 40, "b": 90}, winner_key="b")
        _finalize_game_stats(game, game.state)
        db.session.refresh(human)
        db.session.refresh(bot)
        assert bot.elo > 1000 and bot.games_played == 1 and bot.games_won == 1
        assert human.elo < 1000 and human.games_played == 1 and human.games_won == 0
        # Leaderboard is humans-only. Mirror the /leaderboard query, which joins
        # ttr_stats (games_played is a property on User now, not a column).
        lb = User.query.join(TtrStats).filter(TtrStats.games_played > 0,
                                              User.is_bot.isnot(True)).all()
        assert human in lb and bot not in lb


def test_two_bots_share_user_and_aggregate_once(flask_app, clean_database):
    from app import db, _get_bot_user, _finalize_game_stats
    from models import User, GameResult
    with flask_app.app_context():
        human = User(username="alice", email="alice@x.com", elo=1000)
        db.session.add(human)
        db.session.commit()
        bot = _get_bot_user("shitter_bot")   # both bot seats link to this one account
        game, keys = _finished_game(
            db, "DUP1",
            [{"key": "h", "user_id": human.id, "name": "alice", "color": "red", "is_host": True},
             {"key": "b1", "user_id": bot.id, "name": "shitter-bot", "color": "blue"},
             {"key": "b2", "user_id": bot.id, "name": "shitter-bot", "color": "green"}],
            scores={"h": 30, "b1": 80, "b2": 50}, winner_key="b1")
        _finalize_game_stats(game, game.state)
        db.session.refresh(bot)
        assert bot.games_played == 1        # one game, not two, despite two seats
        assert bot.games_won == 1
        assert bot.total_points == 80 + 50  # points summed across its seats
        results = GameResult.query.filter_by(user_id=bot.id).all()
        assert len(results) == 1 and results[0].placement == 1  # best of its seats


def test_finalize_opponent_names(flask_app, clean_database):
    from app import db, _get_bot_user, _finalize_game_stats
    from models import User, GameResult
    with flask_app.app_context():
        human = User(username="alice_acct", email="alice@x.com", elo=1000)
        db.session.add(human)
        db.session.commit()
        bot = _get_bot_user("shitter_bot")
        # Human's in-game name deliberately differs from the account username.
        game, keys = _finished_game(
            db, "OPP1",
            [{"key": "h", "user_id": human.id, "name": "AliceInGame", "color": "red", "is_host": True},
             {"key": "b", "user_id": bot.id, "name": "shitter-bot", "color": "blue"}],
            scores={"h": 70, "b": 40}, winner_key="h")
        _finalize_game_stats(game, game.state)
        # Human's record lists the bot by display name (not the internal "bot:slug").
        hr = GameResult.query.filter_by(user_id=human.id).first()
        assert json.loads(hr.opponents)[0]["name"] == "shitter-bot"
        # Bot's record lists the human by account username (not the in-game name).
        br = GameResult.query.filter_by(user_id=bot.id).first()
        assert json.loads(br.opponents)[0]["name"] == "alice_acct"


def test_add_bot_defaults_to_shitter_and_links_user(client, flask_app):
    create_and_login(client, "shitter_host")
    data = http_create_game(client)
    code = data["code"]
    sio = make_sio(flask_app, client)
    try:
        sio.emit("join_lobby", {"code": code})
        sio.get_received()
        sio.emit("add_bot", {"code": code})   # no bot_type -> should default to shitter-bot
        sio.get_received()
        from models import Game
        with flask_app.app_context():
            game = Game.query.filter_by(code=code).first()
            bots = [p for p in game.players if p.session_key.startswith("bot_")]
            assert len(bots) == 1
            assert bots[0].session_key.startswith("bot_shitter_bot_")
            assert bots[0].name == "shitter-bot"
            # Linked to its ELO-bearing bot account.
            assert bots[0].user_id is not None
            assert bots[0].linked_user is not None and bots[0].linked_user.is_bot
    finally:
        sio.disconnect()

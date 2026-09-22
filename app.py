import eventlet
eventlet.monkey_patch()

import os
import re
import base64
import random
import string
import smtplib
import uuid
import secrets
import json as json_mod
import urllib.request as urlreq
import urllib.parse as urlparse
from email.mime.text import MIMEText
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

import subprocess as _subprocess

def _get_git_version():
    """Return (commit_subject, github_commit_url) or (None, None) if unavailable."""
    try:
        root = os.path.dirname(__file__)
        hash_ = _subprocess.check_output(
            ["git", "log", "-1", "--format=%h"], cwd=root, text=True,
            stderr=_subprocess.DEVNULL).strip()
        subject = _subprocess.check_output(
            ["git", "log", "-1", "--format=%s"], cwd=root, text=True,
            stderr=_subprocess.DEVNULL).strip()
        remote = _subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=root, text=True,
            stderr=_subprocess.DEVNULL).strip()
        if remote.startswith("git@github.com:"):
            remote = "https://github.com/" + remote[len("git@github.com:"):].removesuffix(".git")
        else:
            remote = remote.removesuffix(".git")
        return subject, f"{remote}/commit/{hash_}"
    except Exception:
        return None, None

GIT_VERSION_NAME, GIT_COMMIT_URL = _get_git_version()

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, session)
from flask_socketio import SocketIO, join_room, leave_room, emit

from models import db, Game, Player, User, GameResult, Friendship, TtrStats
import visits
from game_data_na import ROUTES, CITIES, DESTINATION_TICKETS, PLAYER_COLORS, CARD_COLOR_HEX, BOARD_WIDTH, BOARD_HEIGHT
from game_data_europe import (
    EUROPE_ROUTES, EUROPE_CITIES, EUROPE_DESTINATION_TICKETS,
    EUROPE_BOARD_WIDTH, EUROPE_BOARD_HEIGHT,
)
from route_segments import ROUTE_SEGMENTS
from route_segments_europe import EUROPE_ROUTE_SEGMENTS
import game_logic as logic

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# Cross-subdomain single sign-on with Egyptian Rat Screw (ers.cgovind.com): with the
# same SECRET_KEY and a cookie scoped to .cgovind.com, a login here is valid there too.
# Set SESSION_COOKIE_DOMAIN=.cgovind.com in prod; leave unset locally.
_cookie_domain = os.environ.get("SESSION_COOKIE_DOMAIN")
if _cookie_domain:
    app.config["SESSION_COOKIE_DOMAIN"] = _cookie_domain
if os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
    app.config["SESSION_COOKIE_SECURE"] = True

# Inject asset version into all templates for cache-busting
_ASSET_VERSION = GIT_VERSION_NAME or 'dev'

# The main site, which is where /accounts and the flag art are served from.
# Deliberately not `SITE_URL`, which on the box already means this service's own
# public address.
MAIN_SITE_URL = os.environ.get("MAIN_SITE_URL", "https://cgovind.com").rstrip("/")


@app.context_processor
def inject_asset_version():
    # `presence_where` is what the heartbeat in base.html says about this
    # page. Derived from the endpoint rather than passed by each route, so a
    # new page gets a sensible answer without anybody remembering to add one.
    # `presence_on` is read off the session rather than by loading the user:
    # the heartbeat only needs to know whether this browser has an account,
    # and this runs on every render of every page. Not every route passes
    # `user` into its template, so relying on that would have quietly
    # switched the heartbeat off on the pages that do not.
    return {'asset_version': _ASSET_VERSION, 'site_url': MAIN_SITE_URL,
            'presence_on': bool(session.get('user_id')),
            'presence_where': PRESENCE_BY_ENDPOINT.get(request.endpoint or '', 'home')}


PRESENCE_BY_ENDPOINT = {
    'lobbies': 'lobby',
    'lobby': 'lobby',
    'game_page': 'game',
    'replay_page': 'replay',
    'leaderboard': 'board',
}

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///tickettoride.db"

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# SMS via Twilio REST (optional — requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")

# Email via SMTP (optional — requires SMTP_HOST, SMTP_USER, SMTP_PASS)
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

# Public URL used in notification links
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")

# Google OAuth (optional — requires GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET env vars)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")  # set explicitly for production
GOOGLE_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

with app.app_context():
    db.create_all()
    # Add new columns to existing databases without dropping data
    _migration_stmts = [
        "ALTER TABLE games ADD COLUMN is_private BOOLEAN DEFAULT 0",
        "ALTER TABLE games ADD COLUMN passcode VARCHAR(20)",
        "ALTER TABLE games ADD COLUMN last_activity_at DATETIME",
        "ALTER TABLE games ADD COLUMN map_variant VARCHAR(10) DEFAULT 'usa'",
        "ALTER TABLE users ADD COLUMN phone VARCHAR(20)",
        "ALTER TABLE users ADD COLUMN notify_new_game BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN is_bot BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN elo INTEGER DEFAULT 1000",
        "ALTER TABLE users ADD COLUMN games_played INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN games_won INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN trains_placed INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN tickets_drawn INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN total_points INTEGER DEFAULT 0",
        "ALTER TABLE players ADD COLUMN user_id INTEGER REFERENCES users(id)",
        "ALTER TABLE games ADD COLUMN replay_json TEXT DEFAULT '[]'",
        # Move per-user TTR stats out of `users` into `ttr_stats` so the account
        # (users) can be shared with the Egyptian Rat Screw app. Additive and
        # reversible: the old `users` stat columns are left in place as a backup
        # and this backfill only copies users that don't already have a row.
        ("CREATE TABLE IF NOT EXISTS ttr_stats ("
         " user_id INTEGER PRIMARY KEY REFERENCES users(id),"
         " elo INTEGER DEFAULT 1000, games_played INTEGER DEFAULT 0,"
         " games_won INTEGER DEFAULT 0, trains_placed INTEGER DEFAULT 0,"
         " tickets_drawn INTEGER DEFAULT 0, total_points INTEGER DEFAULT 0)"),
        ("INSERT INTO ttr_stats"
         " (user_id, elo, games_played, games_won, trains_placed, tickets_drawn, total_points)"
         " SELECT id, elo, games_played, games_won, trains_placed, tickets_drawn, total_points"
         " FROM users WHERE id NOT IN (SELECT user_id FROM ttr_stats)"),
    ]
    with db.engine.connect() as _conn:
        for _stmt in _migration_stmts:
            try:
                _conn.execute(db.text(_stmt))
                _conn.commit()
            except Exception:
                _conn.rollback()


# Every request logged, and this service's players marked as here.
# `visits.py` is one file copied into all five services and is byte-identical
# in each - the same convention `models.py` follows. The website repo's
# `tests/test_no_drift.py` is what stops the copies drifting, and it can only
# check this one on a machine with the submodule checked out.
visits.init_app(app, db, "ttr")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_session_key() -> str:
    if "session_key" not in session:
        session["session_key"] = str(uuid.uuid4())
    return session["session_key"]


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


def get_effective_name() -> str:
    """The name to put on a seat: theirs if they chose one, else their username.

    Everything that writes a player's name into a game reads it from here, so
    the display name set on cgovind.com/accounts follows somebody into every
    lobby without any of the game code knowing that is what happened.
    """
    user = get_current_user()
    if user:
        return user.display
    return session.get("guest_name", "Guest")


def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user() and not session.get("guest_name"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def _make_game_code() -> str:
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not Game.query.filter_by(code=code).first():
            return code


def get_player_for_game(game_code: str) -> Player | None:
    sk = get_session_key()
    game = Game.query.filter_by(code=game_code).first()
    if not game:
        return None
    return Player.query.filter_by(game_id=game.id, session_key=sk).first()


def _valid_username(u: str) -> bool:
    return bool(re.match(r'^[A-Za-z][A-Za-z0-9_\-]{1,29}$', u))


# ---------------------------------------------------------------------------
# Notification helpers (SMS + email)
# ---------------------------------------------------------------------------

def _send_sms(to_phone: str, message: str):
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER):
        return
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    data = urlparse.urlencode({"To": to_phone, "From": TWILIO_FROM_NUMBER, "Body": message}).encode()
    creds = base64.b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()
    req = urlreq.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Basic {creds}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlreq.urlopen(req, timeout=10):
            pass
    except Exception:
        pass


def _send_email(to_email: str, subject: str, body: str):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = to_email
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    except Exception:
        pass


def _send_game_notifications(game_code: str, host_name: str, site_url: str):
    join_url = f"{site_url}/lobby/{game_code}"
    message = f"{host_name} just created a Conductor game! Join here: {join_url}"
    with app.app_context():
        # Find the host's user_id from the game
        game = Game.query.filter_by(code=game_code).first()
        if not game:
            return
        host_player = next((p for p in game.players if p.is_host), None)
        host_user_id = host_player.user_id if host_player else None

        if host_user_id:
            # Notify only accepted friends of the host who have notifications on
            friend_ids = db.session.execute(
                db.text("""
                    SELECT friend_id FROM friendships
                    WHERE user_id = :uid AND status = 'accepted'
                    UNION
                    SELECT user_id FROM friendships
                    WHERE friend_id = :uid AND status = 'accepted'
                """),
                {"uid": host_user_id}
            ).fetchall()
            friend_user_ids = [row[0] for row in friend_ids]
            users_to_notify = User.query.filter(
                User.id.in_(friend_user_ids),
                User.notify_new_game == True,  # noqa: E712
            ).all()
        else:
            # Host is a guest — notify nobody (no friend graph without a user account)
            users_to_notify = []

        for user in users_to_notify:
            if user.phone:
                _send_sms(user.phone, message)
            elif user.email:
                _send_email(user.email, "New Conductor Game!", message)


# ---------------------------------------------------------------------------
# Google OAuth helpers
# ---------------------------------------------------------------------------

def _google_post(url: str, data: dict) -> dict:
    encoded = urlparse.urlencode(data).encode()
    req = urlreq.Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urlreq.urlopen(req, timeout=10) as resp:
        return json_mod.loads(resp.read())


def _google_get(url: str, token: str) -> dict:
    req = urlreq.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    with urlreq.urlopen(req, timeout=10) as resp:
        return json_mod.loads(resp.read())


# ---------------------------------------------------------------------------
# HTTP Routes — Auth
# ---------------------------------------------------------------------------

@app.route("/sw.js")
def service_worker():
    from flask import send_from_directory
    return send_from_directory(app.static_folder, "sw.js",
                               mimetype="application/javascript")


@app.route("/")
def index():
    if get_current_user() or session.get("guest_name"):
        return redirect(url_for("lobbies"))
    return redirect(url_for("login_page"))


@app.route("/login", methods=["GET"])
def login_page():
    # Only an *account* is sent away. A guest clicking CREATE ACCOUNT in the
    # nav is somebody who has decided to make a real one, and this is the page
    # that makes it - redirecting them to the lobbies made that link do
    # nothing. `?register=1` still opens the register tab.
    if get_current_user():
        return redirect(url_for("lobbies"))
    google_setup = bool(request.args.get("google_setup"))
    return render_template("login.html", google_enabled=GOOGLE_ENABLED,
                           google_setup=google_setup,
                           git_version_name=GIT_VERSION_NAME,
                           git_commit_url=GIT_COMMIT_URL)


@app.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    identity = data.get("identity", "").strip()
    password = data.get("password", "")
    if not identity or not password:
        return jsonify({"ok": False, "error": "Please fill in all fields."}), 400

    # Allow login by username, email, or phone
    user = User.query.filter_by(username=identity).first()
    if not user:
        user = User.query.filter_by(email=identity.lower()).first()
    if not user:
        user = User.query.filter_by(phone=identity).first()
    if not user or not user.check_password(password):
        return jsonify({"ok": False, "error": "Invalid username or password."}), 401

    session.permanent = True
    session["user_id"] = user.id
    return jsonify({"ok": True})


@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    phone = data.get("phone", "").strip() or None

    if not username or not email or not password:
        return jsonify({"ok": False, "error": "Please fill in all fields."}), 400
    if not _valid_username(username):
        return jsonify({"ok": False, "error": "Username must be 2-30 characters, start with a letter, and contain only letters, numbers, hyphens, or underscores."}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "Password must be at least 8 characters."}), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({"ok": False, "error": "Please enter a valid email address."}), 400
    if phone and not re.match(r'^\+?[0-9][0-9\s\-\(\)]{6,18}[0-9]$', phone):
        return jsonify({"ok": False, "error": "Please enter a valid phone number."}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"ok": False, "error": "Username already taken."}), 409
    if User.query.filter_by(email=email).first():
        return jsonify({"ok": False, "error": "An account with that email already exists."}), 409
    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({"ok": False, "error": "An account with that phone number already exists."}), 409

    user = User(username=username, email=email, phone=phone)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session.permanent = True
    session["user_id"] = user.id
    return jsonify({"ok": True})


@app.route("/guest", methods=["POST"])
def guest_login():
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Please enter a name."}), 400
    if not re.match(r'^[A-Za-z][A-Za-z0-9 _\-]{1,19}$', name):
        return jsonify({"ok": False, "error": "Name must be 2–20 characters, start with a letter, and contain only letters, numbers, spaces, hyphens, or underscores."}), 400
    session.pop("user_id", None)
    session["guest_name"] = name
    return jsonify({"ok": True})


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("guest_name", None)
    return redirect(url_for("login_page"))


@app.route("/settings/notify", methods=["POST"])
def toggle_notify():
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    user.notify_new_game = not user.notify_new_game
    db.session.commit()
    return jsonify({"ok": True, "notify": user.notify_new_game})


def _claude_bot_version():
    """Human-readable summary of the claude_bot engine config currently live.

    Sourced from the same env vars / defaults as claude-bot/bot_entry.py:_cfg().
    Since claude-bot/model/ is gitignored, production has no value model and so
    runs full rollouts ("auto" => off when no weights file present).
    """
    n_iter = int(os.environ.get("CLAUDE_BOT_ITER", "60"))   # keep in sync with bot_entry._cfg()
    policy = os.environ.get("CLAUDE_BOT_POLICY", "heuristic")
    use_value = os.environ.get("CLAUDE_BOT_VALUE", "auto")

    # Mirror _get_rollout_fn(): value model only used if its weights file exists.
    value_weights = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "claude-bot", "model", "value_weights.json")
    has_value_model = (use_value != "off") and os.path.exists(value_weights)
    eval_mode = "value-net" if has_value_model else "full-rollout"

    if n_iter <= 0:
        engine = "heuristic"   # ISMCTS disabled (e.g. tests / CLAUDE_BOT_ITER=0)
        return f"claude_bot engine: {engine} · {policy}-policy"

    return (f"claude_bot engine: ISMCTS · iter={n_iter} · "
            f"{policy}-policy · {eval_mode}")


@app.route("/account")
@require_login
def account_page():
    user = get_current_user()
    if not user:
        return redirect(url_for("login_page"))
    return render_template("account.html", user=user,
                           git_version_name=GIT_VERSION_NAME,
                           git_commit_url=GIT_COMMIT_URL,
                           claude_bot_version=_claude_bot_version())


@app.route("/account/history")
@require_login
def account_history():
    user = get_current_user()
    if not user:
        return redirect(url_for("login_page"))
    history = GameResult.query.filter_by(user_id=user.id)\
                              .order_by(GameResult.played_at.desc())\
                              .limit(50).all()
    for h in history:
        h.opponents_parsed = json_mod.loads(h.opponents or "[]")
    return render_template("account_history.html", user=user, history=history)


@app.route("/account/update", methods=["POST"])
@require_login
def account_update():
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    data = request.json or {}
    field = data.get("field", "")

    if field in ("username", "email"):
        # Both moved to cgovind.com/accounts, and this refuses rather than
        # redirects because it is the *route* that has to stop working, not
        # just the form. A username is the address of a profile the other three
        # games link to, so it is permanent now; an email change has to be
        # confirmed by the new address before it takes effect, which cannot be
        # done in a single POST. Leaving this branch in place would be a way
        # round both, one page over.
        return jsonify({"ok": False, "error":
                        "Your username and email are part of your cgovind.com "
                        "account now - change them at cgovind.com/accounts."}), 400

    elif field == "phone":
        new_val = data.get("value", "").strip() or None
        if new_val and not re.match(r'^\+?[0-9][0-9\s\-\(\)]{6,18}[0-9]$', new_val):
            return jsonify({"ok": False, "error": "Please enter a valid phone number."}), 400
        if new_val:
            existing = User.query.filter_by(phone=new_val).first()
            if existing and existing.id != user.id:
                return jsonify({"ok": False, "error": "Phone number already in use."}), 409
        user.phone = new_val

    elif field == "password":
        current_pw = data.get("current_password", "")
        new_pw = data.get("value", "")
        if user.password_hash and not user.check_password(current_pw):
            return jsonify({"ok": False, "error": "Current password is incorrect."}), 401
        if len(new_pw) < 8:
            return jsonify({"ok": False, "error": "New password must be at least 8 characters."}), 400
        user.set_password(new_pw)

    else:
        return jsonify({"ok": False, "error": "Unknown field."}), 400

    db.session.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# HTTP Routes — Google OAuth
# ---------------------------------------------------------------------------

@app.route("/auth/google")
def google_auth():
    if not GOOGLE_ENABLED:
        return redirect(url_for("login_page"))
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    redirect_uri = GOOGLE_REDIRECT_URI or url_for("google_callback", _external=True)
    params = urlparse.urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
    })
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@app.route("/auth/google/callback")
def google_callback():
    if not GOOGLE_ENABLED:
        return redirect(url_for("login_page"))

    state = request.args.get("state")
    if state != session.pop("oauth_state", None):
        return redirect(url_for("login_page"))
    if request.args.get("error"):
        return redirect(url_for("login_page"))

    code = request.args.get("code")
    redirect_uri = GOOGLE_REDIRECT_URI or url_for("google_callback", _external=True)

    try:
        token_data = _google_post("https://oauth2.googleapis.com/token", {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        access_token = token_data.get("access_token")
        if not access_token:
            return redirect(url_for("login_page"))

        user_info = _google_get(
            "https://www.googleapis.com/oauth2/v3/userinfo", access_token)
    except Exception:
        return redirect(url_for("login_page"))

    google_id = user_info.get("sub")
    email = user_info.get("email", "").lower()
    given_name = user_info.get("given_name", "")
    if not google_id:
        return redirect(url_for("login_page"))

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_id = google_id
            db.session.commit()
        else:
            # New Google user — pick a username
            session["pending_google"] = {
                "google_id": google_id,
                "email": email,
                "name": given_name,
            }
            return redirect(url_for("login_page", google_setup=1))

    session.permanent = True
    session["user_id"] = user.id
    return redirect(url_for("lobbies"))


@app.route("/auth/google/setup", methods=["POST"])
def google_setup():
    pending = session.get("pending_google")
    if not pending:
        return jsonify({"ok": False, "error": "No pending Google login."}), 400

    data = request.json or {}
    username = data.get("username", "").strip()
    if not _valid_username(username):
        return jsonify({"ok": False, "error": "Username must be 2-30 characters, start with a letter, and contain only letters, numbers, hyphens, or underscores."}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"ok": False, "error": "Username already taken."}), 409

    user = User(username=username, email=pending["email"],
                google_id=pending["google_id"])
    db.session.add(user)
    db.session.commit()

    session.pop("pending_google", None)
    session.permanent = True
    session["user_id"] = user.id
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# HTTP Routes — Lobbies & Game
# ---------------------------------------------------------------------------

@app.route("/api/friends")
@require_login
def api_friends():
    user = get_current_user()
    if not user:
        return jsonify([])
    accepted = Friendship.query.filter_by(user_id=user.id, status="accepted").all()
    result = []
    for f in accepted:
        friend = db.session.get(User, f.friend_id)
        if friend:
            result.append({
                "id": friend.id,
                "username": friend.username,
                "online": friend.id in _online_users,
                "elo": friend.elo or 1000,
            })
    return jsonify(result)


@app.route("/api/friend-requests")
@require_login
def api_friend_requests():
    user = get_current_user()
    if not user:
        return jsonify([])
    pending = Friendship.query.filter_by(friend_id=user.id, status="pending").all()
    result = []
    for f in pending:
        sender = db.session.get(User, f.user_id)
        if sender:
            result.append({"id": f.id, "username": sender.username, "elo": sender.elo or 1000})
    return jsonify(result)


@app.route("/friends/request", methods=["POST"])
@require_login
def friend_request():
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    data = request.json or {}
    username = data.get("username", "").strip()
    target = User.query.filter_by(username=username).first()
    if not target:
        return jsonify({"ok": False, "error": "User not found."}), 404
    if target.id == user.id:
        return jsonify({"ok": False, "error": "Cannot friend yourself."}), 400
    existing = Friendship.query.filter_by(user_id=user.id, friend_id=target.id).first()
    if existing:
        return jsonify({"ok": False, "error": "Request already sent or already friends."}), 409
    # Check reverse (they sent us a request already — auto-accept)
    reverse = Friendship.query.filter_by(user_id=target.id, friend_id=user.id).first()
    if reverse and reverse.status == "pending":
        reverse.status = "accepted"
        db.session.add(Friendship(user_id=user.id, friend_id=target.id, status="accepted"))
        db.session.commit()
        return jsonify({"ok": True, "accepted": True})
    db.session.add(Friendship(user_id=user.id, friend_id=target.id))
    db.session.commit()
    return jsonify({"ok": True, "accepted": False})


@app.route("/friends/accept", methods=["POST"])
@require_login
def friend_accept():
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    data = request.json or {}
    req_id = data.get("request_id")
    f = Friendship.query.filter_by(id=req_id, friend_id=user.id, status="pending").first()
    if not f:
        return jsonify({"ok": False, "error": "Request not found."}), 404
    f.status = "accepted"
    # Add reverse row so both sides see each other
    reverse = Friendship.query.filter_by(user_id=user.id, friend_id=f.user_id).first()
    if not reverse:
        db.session.add(Friendship(user_id=user.id, friend_id=f.user_id, status="accepted"))
    else:
        reverse.status = "accepted"
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/friends/decline", methods=["POST"])
@require_login
def friend_decline():
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    data = request.json or {}
    req_id = data.get("request_id")
    f = Friendship.query.filter_by(id=req_id, friend_id=user.id, status="pending").first()
    if f:
        db.session.delete(f)
        db.session.commit()
    return jsonify({"ok": True})


@app.route("/friends/remove", methods=["POST"])
@require_login
def friend_remove():
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    data = request.json or {}
    friend_id = data.get("friend_id")
    for f in Friendship.query.filter(
        ((Friendship.user_id == user.id) & (Friendship.friend_id == friend_id)) |
        ((Friendship.user_id == friend_id) & (Friendship.friend_id == user.id))
    ).all():
        db.session.delete(f)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/replay/<code>")
@require_login
def replay_page(code):
    from flask import abort
    game = Game.query.filter_by(code=code.upper()).first_or_404()
    if game.status != "ended":
        abort(404)
    try:
        replay_data = json_mod.loads(game.replay_json or "[]")
    except Exception:
        replay_data = []
    _map = game.map_variant or "usa"
    if _map == "europe":
        _bd = {"map": "europe", "cities": {k: list(v) for k, v in EUROPE_CITIES.items()},
               "routes": EUROPE_ROUTES, "route_segments": EUROPE_ROUTE_SEGMENTS,
               "card_colors": CARD_COLOR_HEX,
               "board_w": EUROPE_BOARD_WIDTH, "board_h": EUROPE_BOARD_HEIGHT}
    else:
        _bd = {"map": "usa", "cities": {k: list(v) for k, v in CITIES.items()},
               "routes": ROUTES, "route_segments": ROUTE_SEGMENTS,
               "card_colors": CARD_COLOR_HEX,
               "board_w": BOARD_WIDTH, "board_h": BOARD_HEIGHT}
    players_info = {str(p.id): {"name": p.name, "color": p.color} for p in game.players}
    return render_template("replay.html", game=game, replay_data=replay_data,
                           board_data=_bd, players_info=players_info,
                           user=get_current_user())


@app.route("/install")
def install():
    """How to put Conductor on a phone's home screen, for the prompt in `base.html`.

    Both sets of steps are in the page and JS picks between them, so the route
    never sniffs a User-Agent: a link to this page is right for whoever opens
    it rather than for whoever was sent it. No login - the point of the page is
    to be reachable by somebody who has only just arrived.
    """
    return render_template("install.html", user=get_current_user())


@app.route("/leaderboard")
@require_login
def leaderboard():
    top = User.query.join(TtrStats).filter(TtrStats.games_played > 0,
                                           User.is_bot.isnot(True))\
                    .order_by(TtrStats.elo.desc())\
                    .limit(100).all()
    current_user = get_current_user()
    return render_template("leaderboard.html", players=top, user=current_user)


@app.route("/admin")
def admin_page():
    user = get_current_user()
    if not user or user.username != "chinmay":
        return redirect(url_for("login_page"))
    return render_template("admin.html", user=user)


@app.route("/admin/table/<table_name>")
def admin_table(table_name):
    user = get_current_user()
    if not user or user.username != "chinmay":
        return ("Forbidden", 403)
    table_map = {
        "users": User,
        "games": Game,
        "players": Player,
        "game_results": GameResult,
        "friendships": Friendship,
    }
    model = table_map.get(table_name)
    if not model:
        return ("Not found", 404)
    page = request.args.get("page", 1, type=int)
    per_page = 50
    q = model.query.order_by(model.id.desc())
    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    cols = [c.name for c in model.__table__.columns]
    data = [[getattr(r, c) for c in cols] for r in rows]
    return jsonify({
        "table": table_name,
        "columns": cols,
        "rows": data,
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@app.route("/admin/edit/<table_name>/<int:row_id>", methods=["POST"])
def admin_edit(table_name, row_id):
    user = get_current_user()
    if not user or user.username != "chinmay":
        return ("Forbidden", 403)
    table_map = {
        "users": User,
        "games": Game,
        "players": Player,
        "game_results": GameResult,
        "friendships": Friendship,
    }
    model = table_map.get(table_name)
    if not model:
        return jsonify({"error": "Not found"}), 404
    row = model.query.get(row_id)
    if not row:
        return jsonify({"error": "Row not found"}), 404
    payload = request.get_json(force=True)
    cols = {c.name for c in model.__table__.columns}
    for key, val in payload.items():
        if key in cols and key != "id":
            setattr(row, key, val)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/admin/delete/<table_name>/<int:row_id>", methods=["POST"])
def admin_delete(table_name, row_id):
    user = get_current_user()
    if not user or user.username != "chinmay":
        return ("Forbidden", 403)
    table_map = {
        "users": User,
        "games": Game,
        "players": Player,
        "game_results": GameResult,
        "friendships": Friendship,
    }
    model = table_map.get(table_name)
    if not model:
        return jsonify({"error": "Not found"}), 404
    row = model.query.get(row_id)
    if not row:
        return jsonify({"error": "Row not found"}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})


def _get_lobbies_payload():
    """Return serializable dict of current public waiting + ongoing games."""
    waiting = (Game.query
               .filter_by(status="waiting", is_private=False)
               .order_by(Game.created_at.desc()).all())
    ongoing = (Game.query
               .filter(Game.status.in_(["playing", "final_round"]), Game.is_private == False)
               .order_by(Game.created_at.desc()).limit(10).all())

    def _game_card(g):
        host = next((p for p in g.players if p.is_host), None)
        return {
            "code": g.code,
            "host": host.name if host else "Unknown",
            "player_count": len(g.players),
            "max_players": g.max_players,
            "map_variant": g.map_variant or "usa",
        }

    return {
        "waiting": [_game_card(g) for g in waiting],
        "ongoing": [_game_card(g) for g in ongoing],
    }


def _emit_lobbies_update():
    socketio.emit("lobbies_update", _get_lobbies_payload(), to="global_lobby")


@app.route("/lobbies")
@require_login
def lobbies():
    user = get_current_user()

    # Redirect back into any active game this session is already part of
    sk = get_session_key()
    active = (Player.query
              .filter_by(session_key=sk)
              .join(Game, Game.id == Player.game_id)
              .filter(Game.status.in_(["playing", "waiting"]))
              .first())
    if active:
        # Don't redirect resigned players back into the game
        player_state = active.game.state.get("player_states", {}).get(str(active.id), {})
        if not player_state.get("resigned"):
            if active.game.status == "playing":
                return redirect(url_for("game_page", code=active.game.code))
            else:
                return redirect(url_for("lobby", code=active.game.code))

    guest_name = session.get("guest_name") if not user else None
    public_games = (Game.query
                    .filter_by(status="waiting", is_private=False)
                    .order_by(Game.created_at.desc())
                    .all())
    ongoing_games = (Game.query
                     .filter_by(status="playing", is_private=False)
                     .order_by(Game.created_at.desc())
                     .all())
    notify = user.notify_new_game if user else False
    return render_template("lobbies.html", user=user, guest_name=guest_name,
                           games=public_games, ongoing_games=ongoing_games,
                           notify_new_game=notify, online=_online_now())


# What each `where` a page can send is called on a profile. **This table is the
# whole security model of the status line**: the browser sends a key, and a key
# that is not in here means no detail at all rather than something to display.
# A profile page on cgovind.com is public, so anything that let a player put
# their own words on it would be a billboard with a text box attached.
PRESENCE_WHERE = {
    "lobby": "In Lobby",
    "game": "In Game",
    "replay": "Watching a replay",
    "board": "Reading the leaderboard",
}


@app.route("/api/presence", methods=["POST"])
def api_presence():
    """The heartbeat behind the green dot on cgovind.com/accounts.

    Sent on load and then once a minute while the tab is visible. Guests get a
    200 and no row: presence hangs off an account, and there is nowhere to hang
    a guest's.
    """
    user = get_current_user()
    if not user:
        return jsonify({"ok": True})
    where = str((request.json or {}).get("where", ""))[:20]
    visits.seen(db, user.id, "ttr", PRESENCE_WHERE.get(where))
    return jsonify({"ok": True})


def _online_now():
    """Who is about, anywhere on cgovind.com, for the lobbies page.

    Across all four games and not just this one, which is the point: the
    question a lobby raises is "is there anybody around to play", and somebody
    currently driving is somebody you can ask.
    """
    rows = visits.online_now(db.session.connection(), limit=12)
    for r in rows:
        r["label"] = PRESENCE_LABEL.get(r["service"], "Online")
    return rows


# The four games as a profile would name them, for the one-line "who is on"
# list. Deliberately short: this is a sidebar, not a profile.
PRESENCE_LABEL = {"drive": "Drive", "ttr": "Conductor",
                  "ers": "Egyptian Rat Screw", "kot": "King of Tokyo",
                  "site": "On the site"}


@app.route("/create", methods=["POST"])
@require_login
def create_game():
    player_name = get_effective_name()
    data = request.json or {}
    max_players = 6   # always the max; there's no lobby-size setting to choose
    is_private = bool(data.get("is_private", False))
    passcode = data.get("passcode", "").strip() if is_private else None
    map_variant = data.get("map_variant", "usa")
    if map_variant not in ("usa", "europe"):
        map_variant = "usa"

    sk = get_session_key()
    code = _make_game_code()

    game = Game(code=code, max_players=max_players,
                is_private=is_private, passcode=passcode or None,
                map_variant=map_variant)
    db.session.add(game)
    db.session.flush()

    user = get_current_user()
    color = PLAYER_COLORS[0]
    player = Player(
        game_id=game.id,
        user_id=user.id if user else None,
        session_key=sk,
        name=player_name,
        color=color,
        turn_order=0,
        is_host=True,
    )
    db.session.add(player)
    db.session.commit()

    site_url = SITE_URL or request.host_url.rstrip("/")
    eventlet.spawn(_send_game_notifications, code, player_name, site_url)
    _emit_lobbies_update()

    return jsonify({"ok": True, "code": code})


@app.route("/join", methods=["POST"])
@require_login
def join_game_http():
    player_name = get_effective_name()
    data = request.json or {}
    code = data.get("code", "").strip().upper()
    passcode = data.get("passcode", "").strip()

    if not code:
        return jsonify({"ok": False, "error": "Game code required."}), 400

    game = Game.query.filter_by(code=code).first()
    if not game:
        return jsonify({"ok": False, "error": "Game not found."}), 404
    if game.status != "waiting":
        return jsonify({"ok": False, "error": "Game already started."}), 400
    if game.is_private and game.passcode and game.passcode != passcode:
        return jsonify({"ok": False, "error": "Incorrect passcode."}), 403

    sk = get_session_key()

    # Already in the game by session key
    existing = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if existing:
        return jsonify({"ok": True, "code": code})

    # Same user in a different tab/browser — update session key instead of creating a duplicate player
    join_user = get_current_user()
    if join_user:
        existing_by_user = Player.query.filter_by(game_id=game.id, user_id=join_user.id).first()
        if existing_by_user:
            existing_by_user.session_key = sk
            db.session.commit()
            return jsonify({"ok": True, "code": code})

    if len(game.players) >= game.max_players:
        return jsonify({"ok": False, "error": "Game is full."}), 400

    used_colors = {p.color for p in game.players}
    available = [c for c in PLAYER_COLORS if c not in used_colors]
    if not available:
        return jsonify({"ok": False, "error": "No colors available."}), 400

    player = Player(
        game_id=game.id,
        user_id=join_user.id if join_user else None,
        session_key=sk,
        name=player_name,
        color=available[0],
        turn_order=len(game.players),
        is_host=False,
    )
    db.session.add(player)
    db.session.commit()

    socketio.emit("player_joined", game.to_lobby_dict(), to=code)
    _emit_lobbies_update()
    return jsonify({"ok": True, "code": code})


@app.route("/lobby/<code>")
@require_login
def lobby(code):
    game = Game.query.filter_by(code=code.upper()).first_or_404()
    player = get_player_for_game(code)
    if not player:
        user = get_current_user()
        if user:
            existing = Player.query.filter_by(game_id=game.id, user_id=user.id).first()
            if existing:
                # Same account but different session (second device) — block, don't steal the slot
                return redirect(url_for("lobbies"))
    if not player:
        return redirect(url_for("lobbies"))
    if game.status == "playing":
        return redirect(url_for("game_page", code=code.upper()))
    user = get_current_user()
    guest_name = session.get("guest_name") if not user else None
    import bot as bot_module
    # Dropdown order: shitter-bot first, the shittér-bot rival last, the rest between.
    _bt = list(bot_module.BOT_TYPES)
    _first = [t for t in _bt if t[1] == "shitter_bot"]
    _last  = [t for t in _bt if t[1] == "shitter_bot_2"]
    _mid   = [t for t in _bt if t[1] not in ("shitter_bot", "shitter_bot_2")]
    ordered_bot_types = _first + _mid + _last
    return render_template(
        "lobby.html", game=game, player=player, user=user,
        guest_name=guest_name, bot_types=ordered_bot_types,
    )


@app.route("/api/lobby/<code>/status")
def lobby_status(code):
    """Lightweight status poll for the lobby page. Lets a client that missed the
    game_started socket event (e.g. a dropped/spotty connection) still discover the
    game has started and navigate to it — HTTP is far more reliable than the socket
    when the connection is flaky."""
    game = Game.query.filter_by(code=code.upper()).first()
    if not game:
        return {"status": "missing"}, 404
    return {"status": game.status}


@app.route("/game/<code>")
@require_login
def game_page(code):
    user = get_current_user()
    game = Game.query.filter_by(code=code.upper()).first_or_404()
    player = get_player_for_game(code)
    if not player and user:
        existing = Player.query.filter_by(game_id=game.id, user_id=user.id).first()
        if existing and not existing.session_key.startswith("bot_"):
            # Same account, different session = second device. Don't steal the slot — spectate only.
            player = None
    # Resigned players are treated as spectators / kicked out
    if player:
        ps = game.state.get("player_states", {}).get(str(player.id), {})
        if ps.get("resigned"):
            return redirect(url_for("lobbies"))
    is_spectator = player is None
    if game.status == "waiting":
        if player:
            return redirect(url_for("lobby", code=code.upper()))
        else:
            return redirect(url_for("lobbies"))

    map_variant = game.map_variant or "usa"
    if map_variant == "europe":
        board_data = {
            "map": "europe",
            "cities": {k: list(v) for k, v in EUROPE_CITIES.items()},
            "routes": EUROPE_ROUTES,
            "route_segments": EUROPE_ROUTE_SEGMENTS,
            "card_colors": CARD_COLOR_HEX,
            "board_w": EUROPE_BOARD_WIDTH,
            "board_h": EUROPE_BOARD_HEIGHT,
            "tickets": EUROPE_DESTINATION_TICKETS,
        }
    else:
        board_data = {
            "map": "usa",
            "cities": {k: list(v) for k, v in CITIES.items()},
            "routes": ROUTES,
            "route_segments": ROUTE_SEGMENTS,
            "card_colors": CARD_COLOR_HEX,
            "board_w": BOARD_WIDTH,
            "board_h": BOARD_HEIGHT,
            "tickets": DESTINATION_TICKETS,
        }
    music_dir = os.path.join(app.static_folder, "music")
    music_files = sorted(
        f for f in os.listdir(music_dir) if f.lower().endswith(".mp3")
    ) if os.path.isdir(music_dir) else []
    guest_name = session.get("guest_name") if not user else None
    return render_template("game.html", game=game, player=player,
                           board_data=board_data, music_files=music_files,
                           is_spectator=is_spectator, user=user, guest_name=guest_name,
                           git_version_name=GIT_VERSION_NAME, git_commit_url=GIT_COMMIT_URL,
                           map_variant=map_variant)


# ---------------------------------------------------------------------------
# Socket.IO Events
# ---------------------------------------------------------------------------

_chat_history: dict[str, list] = {}  # game_code -> [{name, msg, ts}, …] max 100
_online_users: dict[int, str] = {}   # user_id -> socket_sid

# Bot chat reactions (see bot_chat.py). Per-game state for cooldown + once-only
# triggers (opening line per bot, final-round panic, endgame lines).
_bot_chat_meta: dict[str, dict] = {}
BOT_CHAT_COOLDOWN_S   = 2.5    # min seconds between two bot lines in a game (idle/banter)
BOT_CHAT_IDLE_CHANCE  = 0.03   # chance a normal bot turn produces idle banter
BOT_CHAT_MAX_PER_GAME = 5      # hard cap on total bot chat lines per game


def _is_shitter_player(p):
    """Only shitter-bot has chat personality (per user)."""
    return "bot_shitter_bot_" in (getattr(p, "session_key", "") or "")


def _bot_say(code, bot_name, trigger, force=False):
    """Post a bot chat line for `trigger` (random from bot_chat.PHRASES) into the
    game's chat. `force` bypasses the time cooldown for reactive/event lines.
    Best-effort: never raises into the turn loop."""
    try:
        import time as _t
        import bot_chat
        msg = bot_chat.pick(trigger)
        if not msg:
            return
        meta = _bot_chat_meta.setdefault(code, {"last_ts": 0.0})
        # Hard cap: the bot barely talks — only a handful of lines per game total
        # (applies to forced/reactive lines too, so it never exceeds the cap).
        if meta.get("said_count", 0) >= BOT_CHAT_MAX_PER_GAME:
            return
        now = _t.time()
        if not force and now - meta.get("last_ts", 0.0) < BOT_CHAT_COOLDOWN_S:
            return
        meta["last_ts"] = now
        meta["said_count"] = meta.get("said_count", 0) + 1
        chat_msg = {"name": bot_name, "msg": msg}
        hist = _chat_history.setdefault(code, [])
        hist.append(chat_msg)
        if len(hist) > 100:
            del hist[0]
        socketio.emit("chat_message", chat_msg, to=code)
    except Exception:
        pass


def _bot_chat_announce_endgame(game, state, code):
    """Once a game ends: the winning bot gloats, a losing bot copes, and any bot
    that grabbed the longest-path bonus brags. Fires at most once per game."""
    try:
        if state.get("phase") != "ended":
            return
        meta = _bot_chat_meta.setdefault(code, {"last_ts": 0.0})
        if meta.get("ended_said"):
            return
        meta["ended_said"] = True
        scores = state.get("scores", {})
        if not scores:
            return
        bots = {str(p.id): p for p in game.players if _is_shitter_player(p)}
        if not bots:
            return
        winner_pid = max(scores, key=lambda pid: scores[pid].get("total", 0))
        # longest-path brag (one bot that earned the bonus)
        for pid, p in bots.items():
            if scores.get(pid, {}).get("longest_path_bonus"):
                _bot_say(code, p.name, "longest_path", force=True)
                break
        if winner_pid in bots:                      # a bot won -> gloat
            _bot_say(code, bots[winner_pid].name, "win", force=True)
        else:                                       # a human won -> a bot copes
            any_bot = next(iter(bots.values()))
            _bot_say(code, any_bot.name, "lose", force=True)
    except Exception:
        pass


def _bot_chat_react_to_human(game, state, code, kind, route_id=None):
    """React to a human move: salt if they blocked a bot's route; suspicion when
    they draw tickets; panic when the final round triggers."""
    try:
        bots = [p for p in game.players if _is_shitter_player(p)]
        if not bots:
            return
        import bot_chat
        if kind == "claim" and route_id is not None:
            for p in bots:
                if bot_chat.route_on_bot_plan(state, str(p.id), route_id):
                    _bot_say(code, p.name, "route_blocked", force=True)
                    break
        elif kind == "draw_tickets":
            _bot_say(code, bots[0].name, "opp_draws_tickets")
        # Final-round panic (whoever triggered it) — once per game.
        if state.get("phase") == "final_round":
            meta = _bot_chat_meta.setdefault(code, {"last_ts": 0.0})
            if not meta.get("final_said"):
                meta["final_said"] = True
                _bot_say(code, bots[0].name, "final_round_panic", force=True)
    except Exception:
        pass


def _bot_chat_opening(code, name, pid):
    """One greeting/trash-talk line at the start of the game (once per game, not
    per bot — keeps the bot from spamming when several are in the lobby)."""
    meta = _bot_chat_meta.setdefault(code, {"last_ts": 0.0})
    if meta.get("opened"):
        return
    meta["opened"] = True
    _bot_say(code, name, "opening", force=True)


def _bot_chat_after_bot_claim(code, name, state, pid, route_id, before_done):
    """After a bot claims: celebrate a completed ticket (or all tickets), else
    hype a long route."""
    try:
        import bot_chat
        if bot_chat.completed_count(state, pid) > before_done:
            if bot_chat.all_tickets_complete(state, pid):
                _bot_say(code, name, "all_tickets_complete", force=True)
            else:
                _bot_say(code, name, "ticket_complete", force=True)
        elif bot_chat.route_length(state, route_id) >= 5:
            _bot_say(code, name, "big_route", force=True)
    except Exception:
        pass


@socketio.on("connect")
def on_connect():
    user = get_current_user()
    if user:
        _online_users[user.id] = request.sid


@socketio.on("disconnect")
def on_disconnect():
    user = get_current_user()
    if user:
        _online_users.pop(user.id, None)


@socketio.on("join_lobbies_room")
def on_join_lobbies_room(data=None):
    join_room("global_lobby")
    emit("lobbies_update", _get_lobbies_payload())


@socketio.on("join_lobby")
def on_join_lobby(data):
    code = data.get("code", "").upper()
    game = Game.query.filter_by(code=code).first()
    if not game:
        return
    join_room(code)
    if game.status != "waiting":
        emit("game_started", {"code": code})
        return
    emit("lobby_state", game.to_lobby_dict())


@socketio.on("leave_lobby")
def on_leave_lobby(data):
    code = data.get("code", "").upper()
    sk = get_session_key()
    game = Game.query.filter_by(code=code).first()
    if not game or game.status != "waiting":
        return
    player = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if not player:
        return
    if player.is_host:
        # Host leaves → close the lobby
        socketio.emit("lobby_closed", {"reason": "Host left the lobby."}, to=code)
        for p in game.players:
            db.session.delete(p)
        db.session.delete(game)
        db.session.commit()
    else:
        db.session.delete(player)
        db.session.commit()
        socketio.emit("player_joined", game.to_lobby_dict(), to=code)
    _emit_lobbies_update()


@socketio.on("start_game")
def on_start_game(data):
    code = data.get("code", "").upper()
    sk = get_session_key()
    game = Game.query.filter_by(code=code).first()
    if not game:
        return
    player = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if not player or not player.is_host:
        emit("error", {"message": "Only the host can start the game."})
        return
    if len(game.players) < 2:
        emit("error", {"message": "Need at least 2 players."})
        return
    if game.status != "waiting":
        return

    players_list = list(game.players)
    random.shuffle(players_list)
    for i, p in enumerate(players_list):
        p.turn_order = i
    game.status = "playing"
    game.last_activity_at = datetime.utcnow()

    players_data = [{"id": p.id, "name": p.name, "color": p.color, "turn_order": p.turn_order}
                    for p in players_list]
    state = logic.init_game_state(players_data, map_variant=game.map_variant or "usa")
    game.state = state
    db.session.commit()

    socketio.emit("game_started", {"code": code}, to=code)
    _emit_lobbies_update()
    # Run bots in the background so the game_started broadcast flushes immediately
    # and every player is redirected to the game page; running bots inline here can
    # block the eventlet hub and delay/drop that delivery, stranding players in the
    # lobby.
    _kickoff_bots(game, code)


@socketio.on("join_game_room")
def on_join_game_room(data):
    code = data.get("code", "").upper()
    sk = get_session_key()
    game = Game.query.filter_by(code=code).first()
    if not game:
        return
    player = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if not player:
        # The session key can drift (cookie rotated/expired/re-login) since the
        # player first joined, which would leave this socket out of the personal
        # room _broadcast_state targets (to=player.session_key) — so they would
        # never receive game_state and the board renders blank. Re-resolve a
        # logged-in player by their stable, authenticated user_id.
        uid = session.get("user_id")
        if uid:
            player = Player.query.filter_by(game_id=game.id, user_id=uid).first()
    join_room(code)
    if player:
        # Join the room that personal game_state is actually broadcast to (keyed by
        # the session_key stored on the row), regardless of the current cookie key.
        join_room(player.session_key)
    state = game.state
    bot_ids = [str(p.id) for p in game.players if p.session_key.startswith("bot_")]
    host_id = next((str(p.id) for p in game.players if p.is_host), None)
    if player:
        pub = logic.get_public_state(state, str(player.id))
        pub["my_player_id"] = str(player.id)
        pub["my_color"] = player.color
        pub["is_host"] = player.is_host
        pub["host_player_id"] = host_id
        pub["bot_player_ids"] = bot_ids
        emit("game_state", pub)
    else:
        pub = logic.get_public_state(state, "")
        pub["is_spectator"] = True
        pub["host_player_id"] = host_id
        pub["bot_player_ids"] = bot_ids
        emit("game_state", pub)
        spectator_name = data.get("spectator_name", "").strip()
        if spectator_name:
            socketio.emit("spectator_joined", {"name": spectator_name}, to=code)

    emit("chat_history", _chat_history.get(code, []))


def _get_bot_user(slug: str) -> User | None:
    """Return the persistent synthetic User backing a bot personality, creating it
    on first use. Each personality gets one account so its ELO is tracked across
    games. Best-effort: returns None if it can't be resolved (bot just goes
    unranked, as before)."""
    username = f"bot:{slug}"
    try:
        u = User.query.filter_by(username=username, is_bot=True).first()
        if u is None:
            u = User(username=username, email=f"{slug}@bots.local", is_bot=True, elo=1000)
            db.session.add(u)
            db.session.commit()
        return u
    except Exception:
        db.session.rollback()
        return User.query.filter_by(username=username, is_bot=True).first()


@socketio.on("add_bot")
def on_add_bot(data):
    code = data.get("code", "").upper()
    sk = get_session_key()
    game = Game.query.filter_by(code=code).first()
    if not game or game.status != "waiting":
        emit("error", {"message": "Cannot add bot now."})
        return
    player = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if not player or not player.is_host:
        emit("error", {"message": "Only the host can add bots."})
        return
    if len(game.players) >= game.max_players:
        emit("error", {"message": "Game is full."})
        return

    import bot as bot_module
    import random as _random

    used_colors = {p.color for p in game.players}
    available = [c for c in PLAYER_COLORS if c not in used_colors]
    if not available:
        emit("error", {"message": "No colors available."})
        return

    # The lobby only offers shitter-bot now, so default to it. A specific bot_type
    # is still honored if explicitly requested (other personalities stay fully
    # functional for tests / future use).
    requested = data.get("bot_type")
    chosen = None
    if requested:
        for dn, sl in bot_module.BOT_TYPES:
            if requested in (dn, sl):
                chosen = (dn, sl)
                break
    if chosen is None:
        chosen = next(((dn, sl) for dn, sl in bot_module.BOT_TYPES if sl == "shitter_bot"),
                      bot_module.BOT_TYPES[0])
    display_name, slug = chosen

    bot_user = _get_bot_user(slug)
    bot = Player(
        game_id=game.id,
        session_key=f"bot_{slug}_{uuid.uuid4()}",
        name=display_name,
        color=available[0],
        turn_order=len(game.players),
        is_host=False,
        user_id=bot_user.id if bot_user else None,
    )
    db.session.add(bot)
    db.session.commit()
    socketio.emit("player_joined", game.to_lobby_dict(), to=code)


@socketio.on("kick_player")
def on_kick_player(data):
    code = data.get("code", "").upper()
    target_id = data.get("player_id")
    sk = get_session_key()

    game = Game.query.filter_by(code=code).first()
    if not game:
        return

    host = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if not host or not host.is_host:
        emit("error", {"message": "Only the host can kick players."})
        return

    target = Player.query.filter_by(game_id=game.id, id=target_id).first()
    if not target or target.is_host:
        return

    # Notify all clients before state changes so kicked player can redirect
    socketio.emit("player_kicked", {"player_id": target_id}, to=code)

    if game.status == "waiting":
        db.session.delete(target)
        db.session.commit()
        socketio.emit("player_joined", game.to_lobby_dict(), to=code)
    else:
        target.session_key = f"bot_fish_bot_{uuid.uuid4()}"
        db.session.commit()
        _run_bots(game, code)


@socketio.on("rematch")
def on_rematch(data):
    code = data.get("code", "").upper()
    game = Game.query.filter_by(code=code).first()
    if not game or game.status != "ended":
        return emit("error", {"message": "Game not ended."})
    sid_key = get_session_key()
    player = Player.query.filter_by(game_id=game.id, session_key=sid_key).first()
    if not player or not player.is_host:
        return emit("error", {"message": "Only the host can rematch."})

    new_code = _make_game_code()
    new_game = Game(code=new_code, status="waiting", max_players=game.max_players,
                    is_private=game.is_private, passcode=game.passcode,
                    map_variant=game.map_variant or "usa")
    db.session.add(new_game)
    db.session.flush()

    old_players = list(game.players)
    colors = [p.color for p in old_players]
    random.shuffle(colors)
    for i, old_p in enumerate(old_players):
        new_p = Player(
            game_id=new_game.id,
            name=old_p.name,
            color=colors[i],
            session_key=old_p.session_key,
            is_host=(old_p.id == player.id),
            user_id=old_p.user_id,
            turn_order=i,
        )
        db.session.add(new_p)
    db.session.commit()
    socketio.emit("rematch_created", {"new_code": new_code}, to=code)


@socketio.on("keep_initial_tickets")
def on_keep_initial_tickets(data):
    code = data.get("code", "").upper()
    keep_ids = data.get("keep_ids", [])
    sk = get_session_key()
    game = Game.query.filter_by(code=code).first()
    if not game:
        return
    player = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if not player:
        return

    state = game.state
    offered = list(state["player_states"].get(str(player.id), {}).get("pending_tickets", []))
    result = logic.keep_initial_tickets(state, str(player.id), keep_ids)
    if not result["ok"]:
        emit("error", {"message": result["error"]})
        return

    _log_ticket_decision(state, str(player.id), offered, keep_ids, is_bot=False)
    game.state = state
    db.session.commit()
    _broadcast_state(game, code)
    _run_bots(game, code)


@socketio.on("draw_face_up")
def on_draw_face_up(data):
    code = data.get("code", "").upper()
    slot = int(data.get("slot", 0))
    _player_action(code, lambda state, pid: logic.draw_face_up(state, pid, slot))


@socketio.on("draw_blind")
def on_draw_blind(data):
    code = data.get("code", "").upper()
    _player_action(code, lambda state, pid: logic.draw_blind(state, pid))


@socketio.on("claim_route")
def on_claim_route(data):
    code = data.get("code", "").upper()
    route_id = int(data.get("route_id", 0))
    cards = data.get("cards", {})
    _player_action(code, lambda state, pid: logic.claim_route(state, pid, route_id, cards),
                   react=lambda game, state: _bot_chat_react_to_human(game, state, code, "claim", route_id))


@socketio.on("draw_destination_tickets")
def on_draw_destination_tickets(data):
    code = data.get("code", "").upper()
    _player_action(code, lambda state, pid: logic.draw_destination_tickets(state, pid),
                   react=lambda game, state: _bot_chat_react_to_human(game, state, code, "draw_tickets"))


@socketio.on("keep_drawn_tickets")
def on_keep_drawn_tickets(data):
    code = data.get("code", "").upper()
    keep_ids = data.get("keep_ids", [])

    def _act(state, pid):
        offered = list(state["player_states"].get(pid, {}).get("pending_tickets", []))
        r = logic.keep_drawn_tickets(state, pid, keep_ids)
        if r.get("ok"):
            _log_ticket_decision(state, pid, offered, keep_ids, is_bot=False)
        return r

    _player_action(code, _act)


@socketio.on("resolve_tunnel")
def on_resolve_tunnel(data):
    code = data.get("code", "").upper()
    proceed = bool(data.get("proceed", False))
    extra_cards = data.get("extra_cards", {})
    _player_action(code, lambda state, pid: logic.resolve_tunnel(state, pid, proceed, extra_cards))


@socketio.on("place_station")
def on_place_station(data):
    code = data.get("code", "").upper()
    city = data.get("city", "")
    cards = data.get("cards", {})
    _player_action(code, lambda state, pid: logic.place_station(state, pid, city, cards))


def _replace_player_with_bot(game: Game, player: Player, code: str):
    """Convert a leaving player's slot to a bot. Works in any game phase."""
    state = game.state
    if state.get("phase") == "ended":
        return
    state.setdefault("action_log", []).append(f"{player.name} has left the game.")
    game.state = state
    player.session_key = f"bot_fish_bot_{uuid.uuid4()}"
    db.session.commit()
    _broadcast_state(game, code)
    _run_bots(game, code)


@app.route("/resign/<code>", methods=["POST"])
def resign_game_http(code):
    code = code.upper()
    sk = get_session_key()
    game = Game.query.filter_by(code=code).first()
    if not game or game.status != "playing":
        return jsonify({"ok": True})  # already ended or not started — just let them navigate away
    player = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if not player:
        return jsonify({"ok": True})  # spectator or already left — nothing to resign
    _replace_player_with_bot(game, player, code)
    return jsonify({"ok": True})


@socketio.on("resign_game")
def on_resign_game(data):
    code = data.get("code", "").upper()
    sk = get_session_key()
    game = Game.query.filter_by(code=code).first()
    if not game or game.status != "playing":
        return
    player = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if not player:
        return
    _replace_player_with_bot(game, player, code)


@socketio.on("send_chat")
def on_send_chat(data):
    code = data.get("code", "").upper()
    msg = data.get("msg", "").strip()
    if not msg or len(msg) > 200:
        return
    game = Game.query.filter_by(code=code).first()
    if not game:
        return
    sk = get_session_key()
    player = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if player:
        sender_name = player.name
    else:
        sender_name = (data.get("spectator_name") or "").strip() or "Spectator"
    chat_msg = {"name": sender_name, "msg": msg}
    history = _chat_history.setdefault(code, [])
    history.append(chat_msg)
    if len(history) > 100:
        del history[0]
    socketio.emit("chat_message", chat_msg, to=code)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _player_action(code: str, action_fn, react=None):
    sk = get_session_key()
    game = Game.query.filter_by(code=code).first()
    if not game:
        emit("error", {"message": "Game not found."})
        return
    player = Player.query.filter_by(game_id=game.id, session_key=sk).first()
    if not player:
        emit("error", {"message": "You are not in this game."})
        return

    state = game.state
    result = action_fn(state, str(player.id))
    if not result["ok"]:
        emit("error", {"message": result.get("error", "Action failed.")})
        return

    game.state = state

    # Record slim replay snapshot
    import time as _time
    snap = {
        "t": int(_time.time()),
        "routes": dict(state.get("claimed_routes", {})),
        "scores": {pid: pdata.get("route_score", 0)
                   for pid, pdata in state["player_states"].items()},
        "face_up": state.get("face_up", []),
        "action": state.get("action_log", [""])[-1] if state.get("action_log") else "",
    }
    try:
        replay = json_mod.loads(game.replay_json or "[]")
        replay.append(snap)
        game.replay_json = json_mod.dumps(replay[-500:])
    except Exception:
        pass

    db.session.commit()
    _broadcast_state(game, code)
    # Bot chat reactions to this human move (block salt, ticket-draw suspicion,
    # final-round panic) and endgame lines if the move ended the game.
    if react:
        try:
            react(game, state)
        except Exception:
            pass
    _bot_chat_announce_endgame(game, state, code)
    # Spawn bots in background so the state update reaches the client immediately.
    _kickoff_bots(game, code)


def _kickoff_bots(game: Game, code: str):
    """Start the bot turns. In production this is a detached background greenlet so
    the just-emitted state/`game_started` flushes to clients immediately. Under
    TESTING we run synchronously: a detached greenlet would outlive the test, then
    commit on a stale DB session (StaleDataError) and pollute later tests."""
    if app.config.get("TESTING"):
        _run_bots(game, code)
    else:
        eventlet.spawn_n(_run_bots_bg, game.id, code)


def _run_bots_bg(game_id: int, code: str):
    """Background greenlet: yield to deliver state update, then run bots with delay."""
    import random as _rand
    eventlet.sleep(0)  # yield so emitted state is delivered before bot acts
    with app.app_context():
        game = db.session.get(Game, game_id)
        if not game:
            return
        state = game.state
        phase = state.get("phase")
        if phase in ("main", "final_round"):
            cur_pid = state.get("current_player_id")
            cur_player = next((p for p in game.players if str(p.id) == cur_pid), None)
            if cur_player and cur_player.session_key.startswith("bot_"):
                # Fast heuristic bots move near-instantly, so add a human-like
                # pacing delay. claude_bot's ISMCTS already takes a couple seconds
                # to "think", so skip the extra delay for it — it's slow enough.
                import bot as _bot_module
                _personality = _bot_module._extract_personality(cur_player.session_key)
                if _personality != "claude_bot":
                    # In bigger games (4+ players) bots move fast (0.5s) so the game
                    # doesn't drag; smaller games keep the human-like 1-4s pacing.
                    _n_players = len(state.get("turn_order", [])) or len(game.players)
                    _delay = 0.5 if _n_players > 3 else _rand.uniform(1.0, 4.0)
                    eventlet.sleep(_delay)
                    game = db.session.get(Game, game_id)  # re-fetch after sleep
                    if not game:
                        return
        _run_bots(game, code)


def _finalize_game_stats(game: Game, state: dict):
    """Called once when game phase transitions to ended. Updates per-user stats and ELO."""
    game.status = "ended"

    scores = state.get("scores", {})
    winner_id = state.get("winner_id")
    if not scores:
        db.session.commit()
        return

    # Map player-state pid -> Player record
    pid_to_player = {str(p.id): p for p in game.players}

    # Gather every player with a linked account — humans AND bots (each bot
    # personality has its own synthetic User, so bots earn/lose ELO too).
    pid_to_user: dict[str, User] = {}
    for pid, p in pid_to_player.items():
        if p.user_id:
            u = db.session.get(User, p.user_id)
            if u:
                pid_to_user[pid] = u

    if not pid_to_user:
        db.session.commit()
        return

    # Build ranking (0 = best) from scores for ELO
    ranked_pids = sorted(scores.keys(), key=lambda pid: scores[pid]["total"], reverse=True)
    rank_of = {pid: i for i, pid in enumerate(ranked_pids)}

    # Compute ELO deltas (pairwise, then averaged)
    elo_deltas: dict[str, int] = {}
    real_pids = [pid for pid in ranked_pids if pid in pid_to_user]
    for pid in real_pids:
        user = pid_to_user[pid]
        K = 32 if (user.games_played or 0) < 10 else 16
        my_elo = user.elo or 1000
        my_rank = rank_of[pid]
        delta = 0.0
        opponents = [opid for opid in real_pids if opid != pid]
        for opid in opponents:
            opp_elo = pid_to_user[opid].elo or 1000
            expected = 1 / (1 + 10 ** ((opp_elo - my_elo) / 400))
            opp_rank = rank_of[opid]
            actual = 1.0 if my_rank < opp_rank else (0.5 if my_rank == opp_rank else 0.0)
            delta += K * (actual - expected)
        if opponents:
            delta /= len(opponents)
        elo_deltas[pid] = round(delta)

    # Apply stats updates and record match history, grouped by user so a single
    # personality occupying multiple seats (e.g. two shitter-bots) updates once.
    agg_by_user: dict[int, dict] = {}
    for pid, user in pid_to_user.items():
        if pid not in scores:
            continue
        ps = state["player_states"].get(pid, {})
        sc = scores[pid]
        placement = ranked_pids.index(pid) + 1
        agg = agg_by_user.setdefault(user.id, {
            "user": user, "delta": 0, "won": False, "trains": 0,
            "tickets": 0, "points": 0, "best_pid": pid, "best_placement": placement,
        })
        agg["delta"]   += elo_deltas.get(pid, 0)
        agg["won"]      = agg["won"] or (pid == winner_id)
        agg["trains"]  += max(0, 45 - ps.get("trains", 45))
        agg["tickets"] += len(ps.get("tickets", []))
        agg["points"]  += max(0, sc.get("total", 0))
        if placement < agg["best_placement"]:
            agg["best_placement"] = placement
            agg["best_pid"] = pid

    for agg in agg_by_user.values():
        user = agg["user"]
        elo_before = user.elo or 1000
        user.games_played = (user.games_played or 0) + 1
        if agg["won"]:
            user.games_won = (user.games_won or 0) + 1
        user.trains_placed = (user.trains_placed or 0) + agg["trains"]
        user.tickets_drawn = (user.tickets_drawn or 0) + agg["tickets"]
        user.total_points  = (user.total_points or 0) + agg["points"]
        user.elo = max(100, elo_before + agg["delta"])

        # Record per-game result. Humans show their account username (as before);
        # bots show their in-game display name (not the internal "bot:slug").
        best_pid = agg["best_pid"]
        opponent_list = [
            {"name": (pid_to_user[opid].username
                      if (opid in pid_to_user and not pid_to_user[opid].is_bot)
                      else pid_to_player[opid].name),
             "elo": scores[opid].get("total", 0),
             "placement": ranked_pids.index(opid) + 1}
            for opid in ranked_pids if opid != best_pid
        ]
        db.session.add(GameResult(
            user_id    = user.id,
            game_code  = game.code,
            placement  = agg["best_placement"],
            score      = scores[best_pid].get("total", 0),
            elo_before = elo_before,
            elo_after  = user.elo,
            opponents  = json_mod.dumps(opponent_list),
        ))

    db.session.commit()


def _broadcast_state(game: Game, code: str):
    game.last_activity_at = datetime.utcnow()
    db.session.commit()
    state = game.state

    # Finalize stats exactly once when the game first ends
    if state.get("phase") == "ended" and game.status == "playing":
        _finalize_game_stats(game, state)
    bot_ids = [str(p.id) for p in game.players if p.session_key.startswith("bot_")]
    host_id = next((str(p.id) for p in game.players if p.is_host), None)
    for p in game.players:
        if p.session_key.startswith("bot_"):
            continue
        pub = logic.get_public_state(state, str(p.id))
        pub["my_player_id"] = str(p.id)
        pub["my_color"] = p.color
        pub["is_host"] = p.is_host
        pub["host_player_id"] = host_id
        pub["bot_player_ids"] = bot_ids
        socketio.emit("game_state", pub, to=p.session_key)

    generic = logic.get_public_state(state, "")
    generic["host_player_id"] = host_id
    generic["bot_player_ids"] = bot_ids
    socketio.emit("game_state_update", generic, to=code)


def _bot_decide(bot_module, state, pid, personality):
    """
    Run a bot's decision OFF the eventlet hub.

    claude_bot's ISMCTS is ~2s of pure-Python CPU work that never yields. Run
    directly on the eventlet greenlet, it blocks the single hub for that whole
    time — the WebSocket can't send/receive and the client appears to hang.
    eventlet.tpool.execute runs it in a native thread so the hub stays
    responsive. bot_turn is read-only on `state` (ISMCTS deep-copies internally),
    so this is thread-safe. Falls back to a direct call if tpool is unavailable
    (e.g. under the pytest test client with no real eventlet hub).
    """
    try:
        from eventlet import tpool as _tpool
        return _tpool.execute(bot_module.bot_turn, state, pid, personality)
    except Exception:
        return bot_module.bot_turn(state, pid, personality)


# Bot build tag — bump when shitter/claude bot logic changes so accumulated human
# games can be A/B'd by version. Stamped onto every bot ticket decision below.
BOT_BUILD = os.environ.get("BOT_BUILD", "shitter-2026-06-26-overlap-continuity")


def _log_ticket_decision(state, pid, offered, kept, is_bot=False, bot_type=None):
    """Record a ticket-selection decision into state['ticket_decisions'].

    Captures what was OFFERED, what was kept, and crucially what was REJECTED,
    plus the decision context (hand, trains, turn, network size). The replay log
    never stored ticket choices, so rejected tickets — the key signal for learning
    human ticket selection — were invisible. Persists inside state_json (the caller
    saves game.state afterward); best-effort, never breaks the turn on error.
    """
    try:
        offered = [int(t) for t in offered]
        if not offered:
            return
        kept_set = {int(t) for t in kept}
        ps = state["player_states"].get(pid, {})
        _, ticket_by_id, _, _ = logic._map_data(state.get("map", "usa"))

        def _tk(tid):
            t = ticket_by_id.get(tid, {})
            return {"id": tid, "start": t.get("city1"), "end": t.get("city2"),
                    "points": t.get("points")}

        state.setdefault("ticket_decisions", []).append({
            "pid": pid,
            "name": ps.get("name"),
            "is_bot": bool(is_bot),
            "bot_type": bot_type,
            "build": BOT_BUILD if is_bot else None,
            "phase": state.get("phase"),
            "turn": state.get("turns_taken", 0),
            "trains": ps.get("trains"),
            "hand": dict(ps.get("hand", {})),
            "n_owned_routes": sum(1 for o in state.get("claimed_routes", {}).values() if o == pid),
            "n_tickets_held": len(ps.get("tickets", [])),
            "offered":  [_tk(t) for t in offered],
            "kept":     [_tk(t) for t in offered if t in kept_set],
            "rejected": [_tk(t) for t in offered if t not in kept_set],
        })
    except Exception:
        pass


def _run_bots(game: Game, code: str):
    import bot as bot_module
    _no_progress = 0

    for _ in range(100):
        state = game.state
        phase = state.get("phase")

        if phase == "initial_tickets":
            acted = False
            for p in game.players:
                if not p.session_key.startswith("bot_"):
                    continue
                pid = str(p.id)
                ps = state["player_states"].get(pid, {})
                pending = ps.get("pending_tickets", [])
                if pending:
                    personality = bot_module._extract_personality(p.session_key)
                    keep = bot_module.bot_keep_initial_tickets(state, pid, pending, personality)
                    _log_ticket_decision(state, pid, list(pending), keep,
                                         is_bot=True, bot_type=personality)
                    logic.keep_initial_tickets(state, pid, keep)
                    game.state = state
                    db.session.commit()
                    acted = True
                    break
            if not acted:
                break

        elif phase in ("main", "final_round"):
            cur_pid = state["current_player_id"]
            cur_player = next((p for p in game.players if str(p.id) == cur_pid), None)
            if not (cur_player and cur_player.session_key.startswith("bot_")):
                break

            personality = bot_module._extract_personality(cur_player.session_key)

            # Resolve pending tunnel first
            if state.get("pending_tunnel") and state["pending_tunnel"].get("player_id") == cur_pid:
                proceed, extra_cards = bot_module.bot_resolve_tunnel(state, cur_pid, personality)
                logic.resolve_tunnel(state, cur_pid, proceed=proceed,
                                     extra_cards=extra_cards if proceed else None)
                game.state = state
                db.session.commit()
                continue

            ps = state["player_states"].get(cur_pid, {})

            # Stuck with pending tickets (e.g. draw_tickets kept none) — clear them now
            if ps.get("pending_tickets"):
                pending = ps["pending_tickets"]
                keep = pending[:max(1, len(pending))]  # keep all of them
                logic.keep_drawn_tickets(state, cur_pid, keep)
                game.state = state
                db.session.commit()
                continue

            draw_step = state.get("draw_step", 0)
            turn_order = state.get("turn_order", [])

            def _force_advance_bot():
                """Advance to next player when the bot is completely stuck."""
                if turn_order:
                    idx = (turn_order.index(cur_pid) + 1) % len(turn_order)
                    state["draw_step"] = 0
                    state["current_player_id"] = turn_order[idx]
                    state["turns_taken"] = state.get("turns_taken", 0) + 1

            # Stuck mid-draw (draw_step=1) — complete the second draw
            if draw_step == 1:
                r = logic.draw_blind(state, cur_pid)
                if not r.get("ok"):
                    _force_advance_bot()
                game.state = state
                db.session.commit()
                continue

            def _safe_draw_blind():
                r = logic.draw_blind(state, cur_pid)
                return r.get("ok", False)

            def _do_second_draw():
                try:
                    action2, params2 = _bot_decide(bot_module, state, cur_pid, personality)
                except Exception:
                    action2 = "draw_blind"
                    params2 = {}
                if action2 == "draw_face_up":
                    r2 = logic.draw_face_up(state, cur_pid, params2["slot"])
                    if not r2.get("ok"):
                        _safe_draw_blind()
                else:
                    _safe_draw_blind()

            _chatty = personality in ("shitter_bot", "shitter_bot_2")
            if _chatty:
                _bot_chat_opening(code, cur_player.name, cur_pid)

            try:
                action, params = _bot_decide(bot_module, state, cur_pid, personality)
            except Exception as e:
                app.logger.error(f"bot_turn error ({personality}): {e}")
                action, params = "draw_blind", {}

            advanced = False

            if action == "claim":
                before_done = None
                if _chatty:
                    import bot_chat as _bc
                    before_done = _bc.completed_count(state, cur_pid)
                result = logic.claim_route(state, cur_pid, params["route_id"], params["cards"])
                if result.get("ok"):
                    advanced = True
                    if before_done is not None:
                        _bot_chat_after_bot_claim(code, cur_player.name, state, cur_pid,
                                                  params["route_id"], before_done)
                elif _safe_draw_blind():
                    _do_second_draw()
                    advanced = True

            elif action == "draw_tickets":
                result = logic.draw_destination_tickets(state, cur_pid)
                if result.get("ok"):
                    fresh_ps = state["player_states"].get(cur_pid, {})
                    pending = fresh_ps.get("pending_tickets", [])
                    keep = bot_module.bot_keep_initial_tickets(state, cur_pid, pending, personality)
                    if not keep:
                        keep = pending[:1]
                    _log_ticket_decision(state, cur_pid, list(pending), keep,
                                         is_bot=True, bot_type=personality)
                    logic.keep_drawn_tickets(state, cur_pid, keep)
                    advanced = True
                elif _safe_draw_blind():
                    _do_second_draw()
                    advanced = True

            elif action == "draw_face_up":
                slot = params["slot"]
                _fu = state.get("face_up", [])
                drew_loco = 0 <= slot < len(_fu) and _fu[slot] == "locomotive"
                result = logic.draw_face_up(state, cur_pid, slot)
                if result.get("ok"):
                    if drew_loco and _chatty:
                        _bot_say(code, cur_player.name, "drew_loco")
                    _do_second_draw()
                    advanced = True
                elif _safe_draw_blind():
                    _do_second_draw()
                    advanced = True

            else:  # draw_blind
                if _safe_draw_blind():
                    if _chatty and random.random() < BOT_CHAT_IDLE_CHANCE:
                        _bot_say(code, cur_player.name, "idle")
                    _do_second_draw()
                    advanced = True

            # If nothing worked (deck exhausted + routes blocked), force-advance
            if not advanced and str(state.get("current_player_id")) == cur_pid:
                _force_advance_bot()
                _no_progress += 1
                if _no_progress >= len(turn_order) * 4:
                    logic._end_game(state)
                    game.state = state
                    db.session.commit()
                    break
            else:
                _no_progress = 0

            game.state = state
            db.session.commit()
        else:
            break

    _broadcast_state(game, code)
    _bot_chat_announce_endgame(game, game.state, code)


@socketio.on("register_session")
def on_register_session(data=None):
    sk = get_session_key()
    join_room(sk)


@socketio.on("get_all_tickets")
def on_get_all_tickets(data=None):
    code = (data or {}).get("code", "").upper()
    game = Game.query.filter_by(code=code).first() if code else None
    if game and (game.map_variant or "usa") == "europe":
        emit("all_tickets", EUROPE_DESTINATION_TICKETS)
    else:
        emit("all_tickets", DESTINATION_TICKETS)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Background: end games inactive for >20 minutes
# ---------------------------------------------------------------------------

def _stale_game_cleanup():
    PLAYING_LIMIT = timedelta(minutes=20)
    WAITING_LIMIT = timedelta(minutes=30)

    def _run_cleanup():
        with app.app_context():
            now = datetime.utcnow()

            # End playing games inactive for >20 minutes
            playing_cutoff = now - PLAYING_LIMIT
            stale_playing = Game.query.filter(
                Game.status == "playing",
                db.or_(
                    Game.last_activity_at == None,   # noqa: E711
                    Game.last_activity_at < playing_cutoff,
                ),
            ).all()
            for game in stale_playing:
                game.status = "ended"
                db.session.commit()
                socketio.emit("game_over", {
                    "reason": "Game ended due to inactivity.",
                    "scores": {},
                }, to=game.code)

            # Delete waiting lobbies older than 2 hours
            waiting_cutoff = now - WAITING_LIMIT
            stale_waiting = Game.query.filter(
                Game.status == "waiting",
                Game.created_at < waiting_cutoff,
            ).all()
            for game in stale_waiting:
                socketio.emit("lobby_closed", {
                    "reason": "Lobby expired.",
                }, to=game.code)
                for player in game.players:
                    db.session.delete(player)
                db.session.delete(game)
            if stale_waiting:
                db.session.commit()
                _emit_lobbies_update()

    _run_cleanup()  # immediate pass on startup
    while True:
        eventlet.sleep(5 * 60)  # then every 5 minutes
        _run_cleanup()

eventlet.spawn(_stale_game_cleanup)


# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_ENV") == "development"
    socketio.run(app, host="0.0.0.0", port=port, debug=debug, use_reloader=False, log_output=True)

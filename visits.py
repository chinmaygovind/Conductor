"""Who is here, and who has been here - the one copy, shared by five services.

Two tables, both in the database every service already shares:

* ``site_visits`` is the log: one row per request that was a *visit* rather
  than a piece of furniture, across cgovind.com and all four games. It is the
  only place in the application that has ever recorded an IP address; before
  this, answering "who is this account" meant reading nginx's logs and matching
  timestamps by hand against the database, which works and does not scale past
  the fourteen days nginx keeps.
* ``user_presence`` is one row per account: where they are and when they were
  last seen. It is what the green dot on a profile reads.

**This file is copied verbatim into each service** (``drive/visits.py``,
``ers/``, ``kot/`` and TTR's own repo), which is this repo's convention for
things five separately-deployed processes all need - the same reason each owns
a copy of ``User``. ``tests/test_no_drift.py`` asserts the copies are
byte-identical, so the duplication cannot rot: there is nothing to keep in step
by hand, only a file to copy. That is also why nothing here imports a model or
a service-specific name. It is handed the ``db`` it should use and reads
``flask.session`` for the columns it needs, so the text of the file has no idea
which service it is running in.

Three rules it must never break, since it runs on *every* request:

1. **It cannot fail a request.** Every entry point is wrapped, and a database
   that is missing, locked or unmigrated costs a log line and nothing else.
2. **It cannot be slow.** One INSERT, and an UPSERT at most every
   ``PRESENCE_EVERY`` seconds per person. Session stitching reads from an
   in-process cache and only falls back to a query when that misses.
3. **It never stores text somebody else chose.** A status line is drawn on a
   public page, so the detail is looked up from a whitelist by the caller and
   what arrives from a browser is a key, never a sentence. See ``seen``.
"""

import os
import re
import uuid
from datetime import datetime, timedelta

from flask import g, request, session
from sqlalchemy import text

# How long a gap ends a session. Thirty minutes is the convention every
# analytics tool uses, and the point of it is that closing the tab and coming
# back after lunch is two visits, while reading one page for ten minutes is
# one.
SESSION_GAP = timedelta(minutes=30)

# A visit counts as "online now" for this long after it. It has to be longer
# than the heartbeat interval or a tab that is behaving perfectly would flicker
# offline between two pings.
ONLINE_FOR = timedelta(minutes=2)

# The floor on how often one person's presence row is rewritten. Without it a
# player posting poses and lap times would rewrite the same row several times a
# second for no gain: the dot cannot be more accurate than the heartbeat.
PRESENCE_EVERY = 20            # seconds

# The visitor cookie. Not the session cookie - that one is login, this one is
# "the same browser as last time", and it exists for the anonymous majority who
# never log in at all. Set on the parent domain so a person who reads the
# landing page and then drives is one visitor rather than two.
COOKIE = "cgv"
COOKIE_MAX_AGE = 60 * 60 * 24 * 730          # two years

# What is furniture rather than a visit. Everything under /static, the
# websocket transport, the heartbeat itself (it would double the table and say
# nothing the presence row does not), the latency probe behind Drive's ping
# readout (polled every couple of seconds by any tab showing it, and it exists
# precisely because it does nothing - logging it would be several hundred rows
# per session saying a browser was still connected), and anything that is
# plainly an asset.
# **PDFs are deliberately not in this list**: the resume is the one file on the
# site whose downloads are worth counting.
SKIP_PREFIXES = ("/static/", "/socket.io/", "/api/presence", "/api/ping")
ASSET_RE = re.compile(
    r"\.(css|js|mjs|map|json|png|jpe?g|gif|svg|webp|avif|ico|bmp"
    r"|woff2?|ttf|otf|eot|mp3|wav|ogg|m4a|mp4|webm|wasm)$", re.I)

# Enough to tell a crawler from a person. Deliberately not exhaustive - the
# flag is a convenience for querying, and nothing is dropped because of it, so
# a bot this misses is a bot with `is_bot = 0` and not a missing row.
#
# The last three lines are the internet's scanners, and they were added by
# reading this table back after the r/WebGames post on 2026-08-14 rather than
# by imagining what might turn up. `Python-urllib`, `l9scan`, `research-scan`,
# `CensysInspect`, `zgrab`, `Go-http-client`, Netcraft and Palo Alto's Xpanse
# were between them about 600 of that month's "visitors", every one of them a
# single request to `/` or `/.env`. `python-` rather than `python-requests`
# because urllib, urllib3 and requests all wear it and no browser wears any of
# it.
BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|scrape|curl|wget|python-|httpx|okhttp"
    r"|headless|phantom|monitor|uptime|pingdom|facebookexternalhit|preview"
    r"|lighthouse|screaming|semrush|ahrefs|bingpreview|feedfetcher"
    r"|scan|zgrab|nuclei|nmap|censys|leakix|netcraft|shodan|expanse"
    r"|paloaltonetworks|research|go-http-client|java/|axios|node-fetch"
    r"|aiohttp|libwww", re.I)


def is_crawler(agent):
    """Whether a ``User-Agent`` belongs to a machine. Three shapes, one regex.

    **No User-Agent at all is never a browser.** Every engine sends one, so an
    empty header is a script that did not bother; 150 arrived in the thirty
    days around Drive's launch, one request each. **A bare ``Mozilla/5.0`` is
    not one either**: that token is a fossil which every real browser follows
    with a platform, an engine and a version, so alone it is a scanner wearing
    the shortest string it thinks will pass.

    What this deliberately cannot catch is a scanner wearing a *complete and
    plausible* browser string. The commonest single "visitor" on this site is
    an eight-year-old iPhone Safari UA arriving from a different address every
    time, one request, no assets, no second page - 370 of them in that same
    month, more than every signature above put together. Nothing readable from
    one request's headers separates that from a person, which is the whole
    reason `/admin` grew a tile counting people who *drove a lap*: behaviour is
    the only honest denominator, and the visitor count is not one.

    Still a flag and never a filter, per rule 3 at the top of this file: these
    rows are written like any other, and every figure in the console prints the
    crawler count beside it.
    """
    agent = (agent or "").strip()
    if not agent:
        return True
    if agent.lower().rstrip(" /") in ("mozilla", "mozilla/5.0", "mozilla/4.0"):
        return True
    return bool(BOT_RE.search(agent))


# visitor_id -> (session_id, last_seen). Bounded, because it is a cache and not
# a record: losing it costs one SELECT, so it is thrown away wholesale rather
# than evicted cleverly.
_SESSIONS = {}
_SESSIONS_MAX = 4000
# user_id -> (when this process last wrote a presence row, what it said).
_PRESENCE_AT = {}

TS_FMT = "%Y-%m-%d %H:%M:%S.%f"


def now():
    return datetime.utcnow()


def stamp(dt):
    """The format the rest of this database already stores datetimes in.

    Written out by hand rather than handed to the driver: Python 3.12 deprecated
    the implicit datetime adapter, and raw SQL like this is exactly what it
    warns about.
    """
    return dt.strftime(TS_FMT)


def parse(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in (TS_FMT, "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
#
# Raw DDL rather than models, for the reason `accounts/gamestats.py` uses raw
# SQL: this file is copied into five services and must not need five sets of
# imports to agree. CREATE TABLE IF NOT EXISTS also means whichever service
# happens to boot first creates them and the other four find them already
# there - the same way `users` has always worked.

DDL = (
    """
    CREATE TABLE IF NOT EXISTS site_visits (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          TEXT NOT NULL,
        service     TEXT NOT NULL,
        visitor_id  TEXT,
        session_id  TEXT,
        user_id     INTEGER,
        method      TEXT,
        path        TEXT,
        query       TEXT,
        status      INTEGER,
        referrer    TEXT,
        user_agent  TEXT,
        ip          TEXT,
        is_bot      INTEGER DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_visits_ts ON site_visits (ts)",
    "CREATE INDEX IF NOT EXISTS ix_visits_user ON site_visits (user_id, ts)",
    "CREATE INDEX IF NOT EXISTS ix_visits_visitor ON site_visits (visitor_id, ts)",
    "CREATE INDEX IF NOT EXISTS ix_visits_session ON site_visits (session_id)",
    "CREATE INDEX IF NOT EXISTS ix_visits_ip ON site_visits (ip, ts)",
    """
    CREATE TABLE IF NOT EXISTS user_presence (
        user_id     INTEGER PRIMARY KEY,
        service     TEXT,
        detail      TEXT,
        last_seen   TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_presence_seen ON user_presence (last_seen)",
)


def ensure_tables(db):
    try:
        with db.engine.begin() as conn:
            for statement in DDL:
                conn.execute(text(statement))
        return True
    except Exception:                                    # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# The hook
# ---------------------------------------------------------------------------

def init_app(app, db, service):
    """Log every visit to ``app`` and keep its players' presence up to date.

    ``service`` is the short name that ends up in both tables and decides what
    a profile says somebody is playing: ``site``, ``drive``, ``ers``, ``kot``
    or ``ttr``.
    """
    app.config["VISITS_SERVICE"] = service

    with app.app_context():
        if not ensure_tables(db):
            app.logger.info("visits: no usable database, tracking is off")

    @app.before_request
    def _visits_before():                                # pragma: no cover - hook
        g.visit_started = True
        g.visitor_id = request.cookies.get(COOKIE) or uuid.uuid4().hex
        g.visitor_is_new = COOKIE not in request.cookies

    @app.after_request
    def _visits_after(response):                         # pragma: no cover - hook
        try:
            _record(db, service, response)
        except Exception:                                # noqa: BLE001
            try:
                db.session.rollback()
            except Exception:                            # noqa: BLE001
                pass
        return response

    return app


def _record(db, service, response):
    visitor = getattr(g, "visitor_id", None) or uuid.uuid4().hex

    # The cookie goes out even on a request that is not itself logged, or the
    # first thing a visitor loads (usually a page, sometimes an asset) would
    # hand out a second id on the very next request.
    if getattr(g, "visitor_is_new", False):
        # `SameSite=None; Partitioned` wherever the cookie is already Secure,
        # and `Lax` where it is not.
        #
        # **Drive is framed on other people's pages now** (a game portal embeds
        # it rather than hosting it), and a `Lax` cookie is not sent at all when
        # the top-level site is somebody else's - so every request from a framed
        # player arrived with no visitor id, was handed a fresh one, and counted
        # as a brand new person. Not a small error: it is one new "visitor" per
        # page view, which is the shape of a traffic spike, and there is no way
        # to tell afterwards which numbers it touched.
        #
        # Two things make this safe for the four services that are *not* framed.
        # `None` needs `Secure`, so it hangs off the same env flag the secure
        # cookie already did and a plain-http dev box keeps the cookie it always
        # had. And the CHIPS partition key is the top-level *site* - the
        # registrable domain - so `cgovind.com` and `drive.cgovind.com` share one
        # partition and the cross-subdomain visitor id survives exactly as
        # before. A portal gets a partition of its own, which is the point: the
        # id is stable inside that portal and cannot be joined to this one.
        secure = bool(os.environ.get("SESSION_COOKIE_SECURE", "").lower()
                      in ("1", "true", "yes"))
        response.set_cookie(
            COOKIE, visitor, max_age=COOKIE_MAX_AGE, httponly=True,
            samesite="None" if secure else "Lax",
            partitioned=secure,
            secure=secure,
            domain=os.environ.get("SESSION_COOKIE_DOMAIN") or None)
        g.visitor_is_new = False

    user_id = session.get("user_id")
    at = now()

    if _skip(request.path):
        # Still a sign of life: somebody dragging a track's textures down is
        # somebody who is here. It moves `last_seen` and never the detail.
        if user_id:
            touch(db, user_id, service, at=at)
        return

    agent = request.headers.get("User-Agent", "") or ""
    is_bot = 1 if is_crawler(agent) else 0
    row = {
        "ts": stamp(at),
        "service": service,
        "visitor_id": visitor,
        "session_id": _session_id(db, visitor, at),
        "user_id": user_id,
        "method": request.method,
        "path": request.path[:512],
        "query": (request.query_string.decode("utf-8", "replace") or None),
        "status": getattr(response, "status_code", None),
        "referrer": (request.headers.get("Referer") or None),
        "user_agent": agent[:400] or None,
        "ip": client_ip(),
        "is_bot": is_bot,
    }
    if row["query"]:
        row["query"] = row["query"][:512]

    db.session.execute(text(
        "INSERT INTO site_visits (ts, service, visitor_id, session_id, user_id,"
        " method, path, query, status, referrer, user_agent, ip, is_bot)"
        " VALUES (:ts, :service, :visitor_id, :session_id, :user_id,"
        " :method, :path, :query, :status, :referrer, :user_agent, :ip, :is_bot)"
    ), row)
    db.session.commit()

    if user_id and not is_bot:
        touch(db, user_id, service, at=at)


def _skip(path):
    if path.startswith(SKIP_PREFIXES):
        return True
    return bool(ASSET_RE.search(path))


def client_ip():
    """The visitor's address, from behind nginx.

    Every one of these services listens on 127.0.0.1 with nginx in front, so
    ``remote_addr`` is always the proxy and the real address is the first hop
    in ``X-Forwarded-For``. Taking the *first* is right here and would be wrong
    on an open internet-facing app, where the client can prepend whatever it
    likes - nginx sets this header itself and there is exactly one proxy.
    """
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.remote_addr or "")[:64]


def _session_id(db, visitor, at):
    """Which visit this request belongs to.

    A session is a run of requests from one browser with no gap longer than
    ``SESSION_GAP``. The last-seen time lives in a process-local cache, so the
    usual case costs nothing; a cache miss (a restart, or a second worker) asks
    the table, which is what makes the answer survive both.
    """
    hit = _SESSIONS.get(visitor)
    if hit is None:
        hit = _last_session(db, visitor)
    if hit and at - hit[1] < SESSION_GAP:
        sid = hit[0]
    else:
        sid = uuid.uuid4().hex
    if len(_SESSIONS) > _SESSIONS_MAX:
        _SESSIONS.clear()
    _SESSIONS[visitor] = (sid, at)
    return sid


def _last_session(db, visitor):
    try:
        row = db.session.execute(text(
            "SELECT session_id, ts FROM site_visits WHERE visitor_id = :v"
            " ORDER BY id DESC LIMIT 1"), {"v": visitor}).first()
    except Exception:                                    # noqa: BLE001
        return None
    if not row or not row[0]:
        return None
    ts = parse(row[1])
    return (row[0], ts) if ts else None


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------

def touch(db, user_id, service, at=None):
    """"Still here", without claiming to know what they are doing.

    Moving between services clears the detail, because "Sunrise Circuit" is
    false the moment somebody opens King of Tokyo, and the next heartbeat is up
    to a minute away. Within one service the detail is left alone: the page
    they are on will say so within a second of loading, and until then the last
    thing they told us is the best thing we have.
    """
    _write(db, user_id, service, detail=None, keep_detail=True, at=at)


def seen(db, user_id, service, detail, at=None):
    """"Here, doing this." ``detail`` must come from the caller's whitelist.

    Nothing in this file turns a browser's words into a status: the heartbeat
    routes take a key, look the name up in their own table of tracks or phases,
    and pass the result here. A profile page is public, so a free-text status
    would be a billboard anybody could write on.
    """
    _write(db, user_id, service, detail=detail, keep_detail=False, at=at)


def _write(db, user_id, service, detail, keep_detail, at=None):
    if not user_id:
        return
    at = at or now()
    last = _PRESENCE_AT.get(user_id)
    # Throttled only while there is nothing new to say. **Moving between games
    # is something new**, and an earlier version checked the clock alone: open
    # King of Tokyo ten seconds after a lap and the write was skipped, so the
    # profile went on claiming you were driving until some later request
    # happened to get through. A heartbeat is never throttled at all - it is
    # once a minute and it is the thing that carries the detail.
    if (keep_detail and last and last[1] == service
            and (at - last[0]).total_seconds() < PRESENCE_EVERY):
        return
    try:
        db.session.execute(text(
            "INSERT INTO user_presence (user_id, service, detail, last_seen, updated_at)"
            " VALUES (:u, :s, :d, :t, :t)"
            " ON CONFLICT(user_id) DO UPDATE SET"
            "   service = excluded.service,"
            "   detail = CASE WHEN :keep AND user_presence.service = excluded.service"
            "                 THEN user_presence.detail ELSE excluded.detail END,"
            "   last_seen = excluded.last_seen,"
            "   updated_at = excluded.updated_at"
        ), {"u": user_id, "s": service, "d": detail, "t": stamp(at),
            "keep": 1 if keep_detail else 0})
        db.session.commit()
        _PRESENCE_AT[user_id] = (at, service)
    except Exception:                                    # noqa: BLE001
        try:
            db.session.rollback()
        except Exception:                                # noqa: BLE001
            pass


def presence_for(conn, user_ids):
    """``{user_id: {"service", "detail", "last_seen", "online"}}``.

    Takes a connection rather than a session because its callers are the
    accounts pages, which read every other game's figures the same way - one
    query for a whole page of people, never one per row.
    """
    ids = [int(u) for u in user_ids if u]
    if not ids:
        return {}
    marks = ",".join(str(i) for i in ids)
    try:
        rows = conn.execute(text(
            "SELECT user_id, service, detail, last_seen FROM user_presence"
            " WHERE user_id IN (%s)" % marks)).fetchall()
    except Exception:                                    # noqa: BLE001
        return {}
    cutoff = now() - ONLINE_FOR
    out = {}
    for user_id, service, detail, last_seen in rows:
        ts = parse(last_seen)
        out[user_id] = {"service": service, "detail": detail, "last_seen": ts,
                        "online": bool(ts and ts > cutoff)}
    return out


def online_now(conn, limit=50):
    """Everybody currently online, most recently seen first."""
    try:
        rows = conn.execute(text(
            "SELECT p.user_id, u.username, p.service, p.detail, p.last_seen"
            " FROM user_presence p JOIN users u ON u.id = p.user_id"
            " WHERE p.last_seen > :cut AND (u.is_bot IS NULL OR u.is_bot = 0)"
            " ORDER BY p.last_seen DESC LIMIT :lim"),
            {"cut": stamp(now() - ONLINE_FOR), "lim": limit}).fetchall()
    except Exception:                                    # noqa: BLE001
        return []
    return [{"user_id": r[0], "username": r[1], "service": r[2],
             "detail": r[3], "last_seen": parse(r[4])} for r in rows]

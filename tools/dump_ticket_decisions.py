"""Flatten ticket-selection decisions out of a Conductor SQLite DB.

Each finished/active game's state_json carries a `ticket_decisions` list (see
app._log_ticket_decision): every ticket OFFER with what was kept/rejected and the
context (hand, trains, turn, network size, human vs which bot build). This script
pulls them all into one CSV/JSONL for analysis — the data needed to learn human
ticket selection (rejected tickets included).

Usage:
    python tools/dump_ticket_decisions.py prod.db                 # -> stdout summary
    python tools/dump_ticket_decisions.py prod.db --csv out.csv
    python tools/dump_ticket_decisions.py prod.db --jsonl out.jsonl --humans-only

To grab the live DB first:
    scp -i <key> ubuntu@52.54.184.133:/home/ubuntu/TicketToRide/instance/tickettoride.db prod.db
"""
import argparse
import csv
import json
import sqlite3
import sys


def iter_decisions(db_path, humans_only=False):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    games = con.execute(
        "SELECT id, code, status, map_variant, state_json FROM games"
    ).fetchall()
    for g in games:
        try:
            state = json.loads(g["state_json"] or "{}")
        except Exception:
            continue
        for d in state.get("ticket_decisions", []):
            if humans_only and d.get("is_bot"):
                continue
            kept = {t["id"] for t in d.get("kept", [])}
            for t in d.get("offered", []):
                yield {
                    "game_id": g["id"],
                    "code": g["code"],
                    "status": g["status"],
                    "map": g["map_variant"] or "usa",
                    "actor": d.get("name"),
                    "is_bot": d.get("is_bot"),
                    "bot_type": d.get("bot_type"),
                    "build": d.get("build"),
                    "phase": d.get("phase"),
                    "turn": d.get("turn"),
                    "trains": d.get("trains"),
                    "n_owned_routes": d.get("n_owned_routes"),
                    "n_tickets_held": d.get("n_tickets_held"),
                    "ticket_id": t["id"],
                    "start": t.get("start"),
                    "end": t.get("end"),
                    "points": t.get("points"),
                    "kept": int(t["id"] in kept),
                }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--csv")
    ap.add_argument("--jsonl")
    ap.add_argument("--humans-only", action="store_true")
    args = ap.parse_args()

    rows = list(iter_decisions(args.db, humans_only=args.humans_only))
    if not rows:
        print("No ticket_decisions found (older games predate telemetry).", file=sys.stderr)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {len(rows)} offered-ticket rows -> {args.csv}")
    if args.jsonl:
        with open(args.jsonl, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"wrote {len(rows)} offered-ticket rows -> {args.jsonl}")

    # Quick summary: keep rate by actor type.
    offers = len(rows)
    kept = sum(r["kept"] for r in rows)
    humans = [r for r in rows if not r["is_bot"]]
    hk = sum(r["kept"] for r in humans)
    print(f"offered tickets: {offers}  kept: {kept} ({kept/offers:.0%})" if offers else "no rows")
    if humans:
        print(f"  human offers: {len(humans)}  kept: {hk} ({hk/len(humans):.0%})  "
              f"avg kept-ticket points: "
              f"{sum(r['points'] for r in humans if r['kept'])/max(1,hk):.1f}  "
              f"avg rejected-ticket points: "
              f"{sum(r['points'] for r in humans if not r['kept'])/max(1,len(humans)-hk):.1f}")


if __name__ == "__main__":
    main()

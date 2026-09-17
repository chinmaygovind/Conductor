# Europe board image is 2400x1596 (displayed scaled to 1024x681).
# City coords are (x, y) pixels on the 1024x681 display canvas.
# Routes add "tunnel" (bool) and "ferry" (int = required locomotives) fields.
# NOTE: These city/route positions are APPROXIMATE — use scripts/europe_debug.html
# to click-place accurate coords, then paste the exports back here.

EUROPE_BOARD_WIDTH  = 1024
EUROPE_BOARD_HEIGHT = 681

# ── Cities ────────────────────────────────────────────────────────────────────
# 47 cities.  All coords in 1024×681 space.
EUROPE_CITIES = {
    "Edinburgh":      (170,  62),
    "London":         (232, 207),
    "Amsterdam":      (326, 210),
    "Bruxelles":      (305, 258),
    "Dieppe":         (225, 295),
    "Brest":          (134, 323),
    "Paris":          (272, 337),
    "Pamplona":       (210, 489),
    "Madrid":         (113, 568),
    "Lisboa":         ( 47, 587),
    "Cadiz":          (112, 638),
    "Barcelona":      (220, 578),
    "Marseille":      (358, 483),
    "Essen":          (407, 219),
    "Kobenhavn":      (477, 117),
    "Frankfurt":      (392, 288),
    "Zurich":         (384, 393),
    "Munchen":        (448, 330),
    "Berlin":         (503, 233),
    "Wien":           (557, 347),
    "Venezia":        (464, 424),
    "Roma":           (473, 512),
    "Brindisi":       (556, 537),
    "Palermo":        (508, 640),
    "Stockholm":      (577,  41),
    "Danzic":         (615, 157),
    "Warszawa":       (661, 225),
    "Riga":           (695,  70),
    "Petrograd":      (860,  64),
    "Wilno":          (771, 200),
    "Smolensk":       (870, 206),
    "Moskva":         (952, 182),
    "Kharkov":        (940, 327),
    "Budapest":       (606, 370),
    "Zagreb":         (546, 436),
    "Sarajevo":       (628, 492),
    "Bucuresti":      (754, 439),
    "Sofia":          (693, 501),
    "Kyiv":           (810, 277),
    "Sevastopol":     (887, 452),
    "Rostov":         (980, 381),
    "Sochi":          (975, 468),
    "Athina":         (677, 613),
    "Constantinople": (802, 561),
    "Smyrna":         (759, 639),
    "Angora":         (877, 612),
    "Erzurum":        (956, 589),
}

# ── Route scoring (same as USA) ────────────────────────────────────────────────
EUROPE_ROUTE_SCORING = {1: 1, 2: 2, 3: 4, 4: 7, 5: 10, 6: 15, 7: 18, 8: 21}

# ── Routes ───────────────────────────────────────────────────────────────────
# id, city1, city2, length, color, double_group, side, tunnel, ferry
# tunnel: True = tunnel route (draw 3 extra blind cards when claiming)
# ferry:  N    = N locomotives required (rest any color); 0 = normal route
# gray routes can be claimed with any single color.
# Double routes: same city pair, different colors/sides; group name is shared.
EUROPE_ROUTES = [
    # ── UK & North Sea ──────────────────────────────────────────────────────
    {"id":101,"city1":"Edinburgh",    "city2":"London",        "length":4,"color":"orange","double_group":"EDI-LON",     "side":0,"tunnel":False,"ferry":0},
    {"id":102,"city1":"Edinburgh",    "city2":"London",        "length":4,"color":"black", "double_group":"EDI-LON",     "side":1,"tunnel":False,"ferry":0},
    {"id":103,"city1":"London",       "city2":"Amsterdam",     "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":1,"ferry_segments":[0,1]},
    {"id":104,"city1":"London",       "city2":"Dieppe",        "length":2,"color":"gray",  "double_group":"LON-DIE",     "side":0,"tunnel":False,"ferry":1,"ferry_segments":[0]},
    {"id":205,"city1":"London",       "city2":"Dieppe",        "length":2,"color":"gray",  "double_group":"LON-DIE",     "side":1,"tunnel":False,"ferry":1,"ferry_segments":[0]},

    # ── Benelux & Germany ───────────────────────────────────────────────────
    {"id":105,"city1":"Amsterdam",    "city2":"Bruxelles",     "length":1,"color":"black", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":106,"city1":"Amsterdam",    "city2":"Frankfurt",     "length":2,"color":"white", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":107,"city1":"Amsterdam",    "city2":"Essen",         "length":3,"color":"yellow","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":206,"city1":"Dieppe",       "city2":"Brest",         "length":2,"color":"orange","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":207,"city1":"Dieppe",       "city2":"Bruxelles",     "length":2,"color":"green", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":109,"city1":"Bruxelles",    "city2":"Frankfurt",     "length":2,"color":"blue",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":111,"city1":"Bruxelles",    "city2":"Paris",         "length":2,"color":"red",   "double_group":"BRX-PAR",     "side":0,"tunnel":False,"ferry":0},
    {"id":112,"city1":"Bruxelles",    "city2":"Paris",         "length":2,"color":"yellow","double_group":"BRX-PAR",     "side":1,"tunnel":False,"ferry":0},
    {"id":113,"city1":"Dieppe",       "city2":"Paris",         "length":1,"color":"pink",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":114,"city1":"Essen",        "city2":"Berlin",        "length":2,"color":"blue",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":115,"city1":"Essen",        "city2":"Frankfurt",     "length":2,"color":"green", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":117,"city1":"Essen",        "city2":"Kobenhavn",     "length":3,"color":"gray",  "double_group":"ESS-KOB",     "side":0,"tunnel":False,"ferry":1,"ferry_segments":[0]},
    {"id":118,"city1":"Essen",        "city2":"Kobenhavn",     "length":3,"color":"gray",  "double_group":"ESS-KOB",     "side":1,"tunnel":False,"ferry":1,"ferry_segments":[0]},
    {"id":119,"city1":"Frankfurt",    "city2":"Berlin",        "length":3,"color":"black", "double_group":"FRA-BER",     "side":0,"tunnel":False,"ferry":0},
    {"id":120,"city1":"Frankfurt",    "city2":"Berlin",        "length":3,"color":"red",   "double_group":"FRA-BER",     "side":1,"tunnel":False,"ferry":0},
    {"id":121,"city1":"Frankfurt",    "city2":"Munchen",       "length":2,"color":"pink",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},

    # ── France & Iberia ─────────────────────────────────────────────────────
    {"id":122,"city1":"Brest",        "city2":"Paris",         "length":3,"color":"black", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":123,"city1":"Brest",        "city2":"Pamplona",      "length":4,"color":"pink",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":125,"city1":"Paris",        "city2":"Frankfurt",     "length":3,"color":"white", "double_group":"PAR-FRA",     "side":0,"tunnel":False,"ferry":0},
    {"id":126,"city1":"Paris",        "city2":"Frankfurt",     "length":3,"color":"orange","double_group":"PAR-FRA",     "side":1,"tunnel":False,"ferry":0},
    {"id":127,"city1":"Paris",        "city2":"Zurich",        "length":3,"color":"gray",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":128,"city1":"Paris",        "city2":"Marseille",     "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":129,"city1":"Paris",        "city2":"Pamplona",      "length":4,"color":"blue",  "double_group":"PAR-PAM",     "side":0,"tunnel":False,"ferry":0},
    {"id":208,"city1":"Paris",        "city2":"Pamplona",      "length":4,"color":"green", "double_group":"PAR-PAM",     "side":1,"tunnel":False,"ferry":0},
    {"id":130,"city1":"Pamplona",     "city2":"Madrid",        "length":3,"color":"white", "double_group":"PAM-MAD",     "side":0,"tunnel":True, "ferry":0},
    {"id":131,"city1":"Pamplona",     "city2":"Madrid",        "length":3,"color":"black", "double_group":"PAM-MAD",     "side":1,"tunnel":True, "ferry":0},
    {"id":132,"city1":"Pamplona",     "city2":"Barcelona",     "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":133,"city1":"Madrid",       "city2":"Lisboa",        "length":3,"color":"pink",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":134,"city1":"Madrid",       "city2":"Cadiz",         "length":3,"color":"orange","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":135,"city1":"Madrid",       "city2":"Barcelona",     "length":2,"color":"yellow","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":136,"city1":"Lisboa",       "city2":"Cadiz",         "length":2,"color":"blue",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":137,"city1":"Barcelona",    "city2":"Marseille",     "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":209,"city1":"Marseille",    "city2":"Pamplona",      "length":4,"color":"red",   "double_group":None,          "side":0,"tunnel":False,"ferry":0},

    # ── Switzerland & Alps (Tunnels!) ────────────────────────────────────────
    {"id":138,"city1":"Marseille",    "city2":"Zurich",        "length":2,"color":"pink",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":140,"city1":"Zurich",       "city2":"Munchen",       "length":2,"color":"yellow","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":141,"city1":"Zurich",       "city2":"Venezia",       "length":2,"color":"green", "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":142,"city1":"Munchen",      "city2":"Venezia",       "length":2,"color":"blue",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":143,"city1":"Munchen",      "city2":"Wien",          "length":3,"color":"orange","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":210,"city1":"Marseille",    "city2":"Roma",          "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},

    # ── Austria, Hungary & Adriatic ──────────────────────────────────────────
    {"id":145,"city1":"Wien",         "city2":"Budapest",      "length":1,"color":"red",   "double_group":"WIE-BUD",     "side":0,"tunnel":False,"ferry":0},
    {"id":146,"city1":"Wien",         "city2":"Budapest",      "length":1,"color":"white", "double_group":"WIE-BUD",     "side":1,"tunnel":False,"ferry":0},
    {"id":147,"city1":"Wien",         "city2":"Zagreb",        "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":148,"city1":"Wien",         "city2":"Warszawa",      "length":4,"color":"blue",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":211,"city1":"Wien",         "city2":"Berlin",        "length":3,"color":"green", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":150,"city1":"Budapest",     "city2":"Zagreb",        "length":2,"color":"orange","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":151,"city1":"Budapest",     "city2":"Sarajevo",      "length":3,"color":"pink",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":152,"city1":"Budapest",     "city2":"Bucuresti",     "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":212,"city1":"Kyiv",         "city2":"Budapest",      "length":6,"color":"gray",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":154,"city1":"Zagreb",       "city2":"Venezia",       "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":155,"city1":"Zagreb",       "city2":"Sarajevo",      "length":3,"color":"red",   "double_group":None,          "side":0,"tunnel":False,"ferry":0},

    # ── Italy ────────────────────────────────────────────────────────────────
    {"id":156,"city1":"Venezia",      "city2":"Roma",          "length":2,"color":"black", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":158,"city1":"Roma",         "city2":"Brindisi",      "length":2,"color":"white", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":159,"city1":"Roma",         "city2":"Palermo",       "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":1,"ferry_segments":[0]},
    {"id":160,"city1":"Brindisi",     "city2":"Palermo",       "length":3,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":1,"ferry_segments":[0]},
    {"id":161,"city1":"Brindisi",     "city2":"Athina",        "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":1,"ferry_segments":[0]},
    {"id":218,"city1":"Athina",       "city2":"Smyrna",        "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":1,"ferry_segments":[0]},
    {"id":213,"city1":"Athina",       "city2":"Sarajevo",      "length":4,"color":"green", "double_group":None,          "side":0,"tunnel":False,"ferry":0},

    # ── Scandinavia & Baltics ────────────────────────────────────────────────
    {"id":163,"city1":"Kobenhavn",    "city2":"Stockholm",     "length":3,"color":"yellow","double_group":"KOB-STO",     "side":0,"tunnel":False,"ferry":0},
    {"id":164,"city1":"Kobenhavn",    "city2":"Stockholm",     "length":3,"color":"white", "double_group":"KOB-STO",     "side":1,"tunnel":False,"ferry":0},
    {"id":165,"city1":"Stockholm",    "city2":"Petrograd",     "length":8,"color":"gray",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":167,"city1":"Berlin",       "city2":"Danzic",        "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":168,"city1":"Berlin",       "city2":"Warszawa",      "length":4,"color":"pink",  "double_group":"BER-WAR",     "side":0,"tunnel":False,"ferry":0},
    {"id":169,"city1":"Berlin",       "city2":"Warszawa",      "length":4,"color":"yellow","double_group":"BER-WAR",     "side":1,"tunnel":False,"ferry":0},
    {"id":170,"city1":"Danzic",       "city2":"Riga",          "length":3,"color":"black", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":171,"city1":"Danzic",       "city2":"Warszawa",      "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":172,"city1":"Riga",         "city2":"Petrograd",     "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":173,"city1":"Riga",         "city2":"Wilno",         "length":4,"color":"green", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":174,"city1":"Petrograd",    "city2":"Wilno",         "length":4,"color":"blue",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":175,"city1":"Petrograd",    "city2":"Moskva",        "length":4,"color":"white", "double_group":None,          "side":0,"tunnel":False,"ferry":0},

    # ── Poland & Russia ──────────────────────────────────────────────────────
    {"id":177,"city1":"Warszawa",     "city2":"Wilno",         "length":3,"color":"red",   "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":214,"city1":"Warszawa",     "city2":"Kyiv",          "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":179,"city1":"Wilno",        "city2":"Smolensk",      "length":3,"color":"yellow","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":180,"city1":"Wilno",        "city2":"Kyiv",          "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":182,"city1":"Smolensk",     "city2":"Moskva",        "length":2,"color":"orange","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":183,"city1":"Moskva",       "city2":"Kharkov",       "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":184,"city1":"Kyiv",         "city2":"Kharkov",       "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":186,"city1":"Kyiv",         "city2":"Smolensk",      "length":3,"color":"red",   "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":187,"city1":"Kharkov",      "city2":"Rostov",        "length":2,"color":"green", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":219,"city1":"Rostov",       "city2":"Sochi",         "length":2,"color":"yellow","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":220,"city1":"Rostov",       "city2":"Sevastopol",    "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},

    # ── Balkans & Eastern Europe ─────────────────────────────────────────────
    {"id":188,"city1":"Sarajevo",     "city2":"Sofia",         "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":189,"city1":"Bucuresti",    "city2":"Sofia",         "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":190,"city1":"Bucuresti",    "city2":"Constantinople","length":3,"color":"yellow","double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":191,"city1":"Bucuresti",    "city2":"Sevastopol",    "length":4,"color":"white", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":192,"city1":"Sevastopol",   "city2":"Constantinople","length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":2,"ferry_segments":[0,1]},
    {"id":196,"city1":"Sofia",        "city2":"Constantinople","length":3,"color":"blue",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":197,"city1":"Sofia",        "city2":"Athina",        "length":3,"color":"pink",  "double_group":None,          "side":0,"tunnel":False,"ferry":0},

    # ── Greece & Turkey ──────────────────────────────────────────────────────
    {"id":199,"city1":"Constantinople","city2":"Smyrna",       "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":200,"city1":"Constantinople","city2":"Angora",       "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":201,"city1":"Smyrna",       "city2":"Angora",        "length":3,"color":"orange","double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":202,"city1":"Angora",       "city2":"Erzurum",       "length":3,"color":"black", "double_group":None,          "side":0,"tunnel":False,"ferry":0},
    {"id":203,"city1":"Erzurum",      "city2":"Sochi",         "length":3,"color":"red",   "double_group":None,          "side":0,"tunnel":True, "ferry":0},
    {"id":215,"city1":"Sochi",        "city2":"Sevastopol",    "length":2,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":1,"ferry_segments":[0]},
    {"id":216,"city1":"Erzurum",      "city2":"Sevastopol",    "length":4,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":2,"ferry_segments":[0,1]},
    {"id":217,"city1":"Smyrna",       "city2":"Palermo",       "length":6,"color":"gray",  "double_group":None,          "side":0,"tunnel":False,"ferry":2,"ferry_segments":[0,1]},
]

# ── Destinations ───────────────────────────────────────────────────────
# 40 short tickets + 6 long tickets (separate decks).
# long=True tickets are dealt 1 per player at game start and MUST be kept.

EUROPE_DESTINATION_TICKETS = [
    # Short tickets
    {"id":101,"city1":"Athina",       "city2":"Angora",        "points": 5, "long":False},
    {"id":102,"city1":"Budapest",     "city2":"Sofia",         "points": 5, "long":False},
    {"id":103,"city1":"Frankfurt",    "city2":"Kobenhavn",     "points": 5, "long":False},
    {"id":104,"city1":"Rostov",       "city2":"Erzurum",       "points": 5, "long":False},
    {"id":105,"city1":"Sofia",        "city2":"Smyrna",        "points": 5, "long":False},
    {"id":106,"city1":"Kyiv",         "city2":"Petrograd",     "points": 6, "long":False},
    {"id":107,"city1":"Zurich",       "city2":"Brindisi",      "points": 6, "long":False},
    {"id":108,"city1":"Zurich",       "city2":"Budapest",      "points": 6, "long":False},
    {"id":109,"city1":"Warszawa",     "city2":"Smolensk",      "points": 6, "long":False},
    {"id":110,"city1":"Zagreb",       "city2":"Brindisi",      "points": 6, "long":False},
    {"id":111,"city1":"Paris",        "city2":"Zagreb",        "points": 7, "long":False},
    {"id":112,"city1":"Brest",        "city2":"Marseille",     "points": 7, "long":False},
    {"id":113,"city1":"London",       "city2":"Berlin",        "points": 7, "long":False},
    {"id":114,"city1":"Edinburgh",    "city2":"Paris",         "points": 7, "long":False},
    {"id":115,"city1":"Amsterdam",    "city2":"Pamplona",      "points": 7, "long":False},
    {"id":116,"city1":"Roma",         "city2":"Smyrna",        "points": 8, "long":False},
    {"id":117,"city1":"Palermo",      "city2":"Constantinople","points": 8, "long":False},
    {"id":118,"city1":"Sarajevo",     "city2":"Sevastopol",    "points": 8, "long":False},
    {"id":119,"city1":"Madrid",       "city2":"Dieppe",        "points": 8, "long":False},
    {"id":120,"city1":"Barcelona",    "city2":"Bruxelles",     "points": 8, "long":False},
    {"id":121,"city1":"Paris",        "city2":"Wien",          "points": 8, "long":False},
    {"id":122,"city1":"Barcelona",    "city2":"Munchen",       "points": 8, "long":False},
    {"id":123,"city1":"Brest",        "city2":"Venezia",       "points": 8, "long":False},
    {"id":124,"city1":"Smolensk",     "city2":"Rostov",        "points": 8, "long":False},
    {"id":125,"city1":"Marseille",    "city2":"Essen",         "points": 8, "long":False},
    {"id":126,"city1":"Kyiv",         "city2":"Sochi",         "points": 8, "long":False},
    {"id":127,"city1":"Madrid",       "city2":"Zurich",        "points": 8, "long":False},
    {"id":128,"city1":"Berlin",       "city2":"Bucuresti",     "points": 8, "long":False},
    {"id":129,"city1":"Bruxelles",    "city2":"Danzic",        "points": 9, "long":False},
    {"id":130,"city1":"Berlin",       "city2":"Roma",          "points": 9, "long":False},
    {"id":131,"city1":"Angora",       "city2":"Kharkov",       "points":10, "long":False},
    {"id":132,"city1":"Riga",         "city2":"Bucuresti",     "points":10, "long":False},
    {"id":133,"city1":"Essen",        "city2":"Kyiv",          "points":10, "long":False},
    {"id":134,"city1":"Venezia",      "city2":"Constantinople","points":10, "long":False},
    {"id":135,"city1":"London",       "city2":"Wien",          "points":10, "long":False},
    {"id":136,"city1":"Athina",       "city2":"Wilno",         "points":11, "long":False},
    {"id":137,"city1":"Stockholm",    "city2":"Wien",          "points":11, "long":False},
    {"id":138,"city1":"Berlin",       "city2":"Moskva",        "points":12, "long":False},
    {"id":139,"city1":"Amsterdam",    "city2":"Wilno",         "points":12, "long":False},
    {"id":140,"city1":"Frankfurt",    "city2":"Smolensk",      "points":13, "long":False},
    # Long tickets (dealt 1 per player, must keep)
    {"id":141,"city1":"Lisboa",       "city2":"Danzic",        "points":20, "long":True},
    {"id":142,"city1":"Brest",        "city2":"Petrograd",     "points":20, "long":True},
    {"id":143,"city1":"Palermo",      "city2":"Moskva",        "points":20, "long":True},
    {"id":144,"city1":"Kobenhavn",    "city2":"Erzurum",       "points":21, "long":True},
    {"id":145,"city1":"Edinburgh",    "city2":"Athina",        "points":21, "long":True},
    {"id":146,"city1":"Cadiz",        "city2":"Stockholm",     "points":21, "long":True},
]

# ── Build lookup helpers ──────────────────────────────────────────────────────
EUROPE_ROUTE_BY_ID    = {r["id"]: r for r in EUROPE_ROUTES}
EUROPE_TICKET_BY_ID   = {t["id"]: t for t in EUROPE_DESTINATION_TICKETS}

EUROPE_DOUBLE_ROUTE_GROUPS: dict[str, list[int]] = {}
for _r in EUROPE_ROUTES:
    if _r["double_group"]:
        EUROPE_DOUBLE_ROUTE_GROUPS.setdefault(_r["double_group"], []).append(_r["id"])

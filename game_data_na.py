# Board image is 1024x683. City coords are (x, y) pixels on that image.
# Routes connect pairs of cities with a color and length.
# DOUBLE_ROUTES groups route IDs that share the same city pair.

BOARD_WIDTH = 1024
BOARD_HEIGHT = 683

PLAYER_COLORS = ["red", "blue", "green", "yellow", "pink", "orange"]

PLAYER_COLOR_HEX = {
    "red":    "#EF4444",
    "blue":   "#3B82F6",
    "green":  "#22C55E",
    "yellow": "#EAB308",
    "pink":   "#EC4899",
    "orange": "#F97316",
}

# Train card colors (8 types + locomotive wild)
CARD_COLORS = ["pink", "blue", "orange", "white", "green", "yellow", "black", "red", "locomotive"]
CARD_COUNTS = {
    "pink": 12, "blue": 12, "orange": 12, "white": 12,
    "green": 12, "yellow": 12, "black": 12, "red": 12,
    "locomotive": 14,
}
CARD_COLOR_HEX = {
    "pink":       "#EC4899",
    "blue":       "#3B82F6",
    "orange":     "#F97316",
    "white":      "#F1F5F9",
    "green":      "#22C55E",
    "yellow":     "#EAB308",
    "black":      "#374151",
    "red":        "#EF4444",
    "locomotive": "#F59E0B",
}

# (x, y) pixel coords on 1024x683 board image
CITIES = {
    "Vancouver":           (108, 106),
    "Seattle":             (106, 162),
    "Portland":            ( 85, 213),
    "San Francisco":       ( 69, 409),
    "Los Angeles":         (145, 514),
    "Las Vegas":           (213, 457),
    "Salt Lake City":      (269, 344),
    "Helena":              (341, 220),
    "Calgary":             (240,  88),
    "Winnipeg":            (465,  99),
    "Denver":              (400, 376),
    "Omaha":               (547, 306),
    "Duluth":              (576, 215),
    "Sault St. Marie":     (704, 148),
    "Kansas City":         (569, 359),
    "Chicago":             (701, 276),
    "Saint Louis":         (654, 358),
    "Oklahoma City":       (548, 444),
    "Dallas":              (568, 532),
    "Houston":             (608, 573),
    "Little Rock":         (639, 450),
    "New Orleans":         (700, 561),
    "Nashville":           (746, 399),
    "Atlanta":             (799, 433),
    "Raleigh":             (864, 373),
    "Charleston":          (893, 439),
    "Miami":               (924, 596),
    "Washington":          (922, 307),
    "Pittsburgh":          (832, 263),
    "New York":            (914, 216),
    "Boston":              (969, 143),
    "Montreal":            (897,  83),
    "Toronto":             (816, 170),
    "Santa Fe":            (392, 467),
    "Phoenix":             (267, 520),
    "El Paso":             (387, 557),
}

ROUTE_SCORING = {1: 1, 2: 2, 3: 4, 4: 7, 5: 10, 6: 15}

# Routes: id, city1, city2, length, color, double_group (None = unique, str = paired)
# side: 0=first route in pair, 1=second (used for perpendicular offset in rendering)
ROUTES = [
    # --- Pacific Northwest ---
    {"id":  1, "city1": "Vancouver",      "city2": "Seattle",        "length": 1, "color": "gray",   "double_group": "VAN-SEA", "side": 0},
    {"id":  2, "city1": "Vancouver",      "city2": "Seattle",        "length": 1, "color": "gray",   "double_group": "VAN-SEA", "side": 1},
    {"id":  3, "city1": "Vancouver",      "city2": "Calgary",        "length": 3, "color": "gray",   "double_group": None,       "side": 0},
    {"id":  4, "city1": "Seattle",        "city2": "Portland",       "length": 1, "color": "gray",   "double_group": "SEA-POR", "side": 0},
    {"id":  5, "city1": "Seattle",        "city2": "Portland",       "length": 1, "color": "gray",   "double_group": "SEA-POR", "side": 1},
    {"id":  6, "city1": "Seattle",        "city2": "Helena",         "length": 6, "color": "yellow", "double_group": None,       "side": 0},
    {"id":  7, "city1": "Portland",       "city2": "San Francisco",  "length": 5, "color": "green",  "double_group": "POR-SF",  "side": 0},
    {"id":  8, "city1": "Portland",       "city2": "San Francisco",  "length": 5, "color": "pink",   "double_group": "POR-SF",  "side": 1},
    {"id":  9, "city1": "Portland",       "city2": "Salt Lake City", "length": 6, "color": "blue",   "double_group": None,       "side": 0},
    # --- California ---
    {"id": 10, "city1": "San Francisco",  "city2": "Los Angeles",    "length": 3, "color": "yellow", "double_group": "SF-LA",   "side": 0},
    {"id": 11, "city1": "San Francisco",  "city2": "Los Angeles",    "length": 3, "color": "pink",   "double_group": "SF-LA",   "side": 1},
    {"id": 12, "city1": "San Francisco",  "city2": "Salt Lake City", "length": 5, "color": "orange", "double_group": "SF-SLC",  "side": 0},
    {"id": 13, "city1": "San Francisco",  "city2": "Salt Lake City", "length": 5, "color": "white",  "double_group": "SF-SLC",  "side": 1},
    {"id": 14, "city1": "Los Angeles",    "city2": "Las Vegas",      "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 15, "city1": "Los Angeles",    "city2": "Phoenix",        "length": 3, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 16, "city1": "Los Angeles",    "city2": "El Paso",        "length": 6, "color": "black",  "double_group": None,       "side": 0},
    # --- Mountain West ---
    {"id": 17, "city1": "Las Vegas",      "city2": "Salt Lake City", "length": 3, "color": "orange", "double_group": None,       "side": 0},
    {"id": 18, "city1": "Salt Lake City", "city2": "Denver",         "length": 3, "color": "red",    "double_group": "SLC-DEN", "side": 0},
    {"id": 19, "city1": "Salt Lake City", "city2": "Denver",         "length": 3, "color": "yellow", "double_group": "SLC-DEN", "side": 1},
    {"id": 20, "city1": "Salt Lake City", "city2": "Helena",         "length": 3, "color": "pink",   "double_group": None,       "side": 0},
    {"id": 21, "city1": "Denver",         "city2": "Helena",         "length": 4, "color": "green",  "double_group": None,       "side": 0},
    {"id": 22, "city1": "Denver",         "city2": "Omaha",          "length": 4, "color": "pink",   "double_group": None,       "side": 0},
    {"id": 23, "city1": "Denver",         "city2": "Kansas City",    "length": 4, "color": "black",  "double_group": "DEN-KC",  "side": 0},
    {"id": 24, "city1": "Denver",         "city2": "Kansas City",    "length": 4, "color": "orange", "double_group": "DEN-KC",  "side": 1},
    {"id": 25, "city1": "Denver",         "city2": "Oklahoma City",  "length": 4, "color": "red",    "double_group": None,       "side": 0},
    {"id": 26, "city1": "Denver",         "city2": "Santa Fe",       "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    # --- Helena / Calgary / Winnipeg ---
    {"id": 27, "city1": "Helena",         "city2": "Calgary",        "length": 4, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 28, "city1": "Helena",         "city2": "Winnipeg",       "length": 4, "color": "blue",   "double_group": None,       "side": 0},
    {"id": 29, "city1": "Helena",         "city2": "Duluth",         "length": 6, "color": "orange", "double_group": None,       "side": 0},
    {"id": 30, "city1": "Helena",         "city2": "Omaha",          "length": 5, "color": "red",    "double_group": None,       "side": 0},
    {"id": 31, "city1": "Calgary",        "city2": "Winnipeg",       "length": 6, "color": "white",  "double_group": None,       "side": 0},
    # --- Great Plains ---
    {"id": 32, "city1": "Winnipeg",       "city2": "Duluth",         "length": 4, "color": "black",  "double_group": None,       "side": 0},
    {"id": 33, "city1": "Winnipeg",       "city2": "Sault St. Marie","length": 6, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 34, "city1": "Duluth",         "city2": "Omaha",          "length": 2, "color": "gray",   "double_group": "DUL-OMA", "side": 0},
    {"id": 35, "city1": "Duluth",         "city2": "Chicago",        "length": 3, "color": "red",    "double_group": None,       "side": 0},
    {"id": 36, "city1": "Duluth",         "city2": "Toronto",        "length": 6, "color": "pink",   "double_group": None,       "side": 0},
    {"id": 37, "city1": "Duluth",         "city2": "Sault St. Marie","length": 3, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 38, "city1": "Omaha",          "city2": "Kansas City",    "length": 1, "color": "gray",   "double_group": "OMA-KC",  "side": 0},
    {"id": 39, "city1": "Omaha",          "city2": "Kansas City",    "length": 1, "color": "gray",   "double_group": "OMA-KC",  "side": 1},
    {"id": 40, "city1": "Omaha",          "city2": "Chicago",        "length": 4, "color": "blue",   "double_group": None,       "side": 0},
    # --- Midwest ---
    {"id": 41, "city1": "Kansas City",    "city2": "Saint Louis",    "length": 2, "color": "blue",   "double_group": "KC-STL",  "side": 0},
    {"id": 42, "city1": "Kansas City",    "city2": "Saint Louis",    "length": 2, "color": "pink",   "double_group": "KC-STL",  "side": 1},
    {"id": 43, "city1": "Kansas City",    "city2": "Oklahoma City",  "length": 2, "color": "gray",   "double_group": "KC-OKC",  "side": 0},
    {"id": 44, "city1": "Kansas City",    "city2": "Oklahoma City",  "length": 2, "color": "gray",   "double_group": "KC-OKC",  "side": 1},
    {"id": 45, "city1": "Chicago",        "city2": "Saint Louis",    "length": 2, "color": "green",  "double_group": "CHI-STL", "side": 0},
    {"id": 46, "city1": "Chicago",        "city2": "Saint Louis",    "length": 2, "color": "white",  "double_group": "CHI-STL", "side": 1},
    {"id": 47, "city1": "Chicago",        "city2": "Pittsburgh",     "length": 3, "color": "orange", "double_group": None,       "side": 0},
    # --- Southwest ---
    {"id": 48, "city1": "Santa Fe",       "city2": "Oklahoma City",  "length": 3, "color": "blue",   "double_group": None,       "side": 0},
    {"id": 49, "city1": "Santa Fe",       "city2": "El Paso",        "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 50, "city1": "Phoenix",        "city2": "Denver",         "length": 5, "color": "white",  "double_group": None,       "side": 0},
    {"id": 51, "city1": "Phoenix",        "city2": "El Paso",        "length": 3, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 52, "city1": "El Paso",        "city2": "Dallas",         "length": 4, "color": "red",    "double_group": None,       "side": 0},
    {"id": 53, "city1": "El Paso",        "city2": "Houston",        "length": 6, "color": "green",  "double_group": None,       "side": 0},
    # --- South Central ---
    {"id": 54, "city1": "Oklahoma City",  "city2": "Dallas",         "length": 2, "color": "gray",   "double_group": "OKC-DAL", "side": 0},
    {"id": 55, "city1": "Oklahoma City",  "city2": "Dallas",         "length": 2, "color": "gray",   "double_group": "OKC-DAL", "side": 1},
    {"id": 56, "city1": "Oklahoma City",  "city2": "Little Rock",    "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 57, "city1": "Dallas",         "city2": "Little Rock",    "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 58, "city1": "Dallas",         "city2": "Houston",        "length": 1, "color": "gray",   "double_group": "DAL-HOU", "side": 0},
    {"id": 59, "city1": "Dallas",         "city2": "Houston",        "length": 1, "color": "gray",   "double_group": "DAL-HOU", "side": 1},
    {"id": 60, "city1": "Houston",        "city2": "New Orleans",    "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 61, "city1": "Little Rock",    "city2": "Saint Louis",    "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 62, "city1": "Little Rock",    "city2": "Nashville",      "length": 3, "color": "white",  "double_group": None,       "side": 0},
    {"id": 63, "city1": "Little Rock",    "city2": "New Orleans",    "length": 3, "color": "green",  "double_group": None,       "side": 0},
    # --- South ---
    {"id": 64, "city1": "New Orleans",    "city2": "Atlanta",        "length": 4, "color": "yellow", "double_group": "NO-ATL",  "side": 0},
    {"id": 65, "city1": "New Orleans",    "city2": "Atlanta",        "length": 4, "color": "orange", "double_group": "NO-ATL",  "side": 1},
    {"id": 66, "city1": "New Orleans",    "city2": "Miami",          "length": 6, "color": "red",    "double_group": None,       "side": 0},
    {"id": 67, "city1": "Nashville",      "city2": "Saint Louis",    "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 68, "city1": "Nashville",      "city2": "Atlanta",        "length": 1, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 69, "city1": "Nashville",      "city2": "Pittsburgh",     "length": 4, "color": "yellow", "double_group": None,       "side": 0},
    {"id": 70, "city1": "Nashville",      "city2": "Raleigh",        "length": 3, "color": "black",  "double_group": None,       "side": 0},
    {"id": 71, "city1": "Atlanta",        "city2": "Raleigh",        "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 72, "city1": "Atlanta",        "city2": "Charleston",     "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 73, "city1": "Atlanta",        "city2": "Miami",          "length": 5, "color": "blue",   "double_group": None,       "side": 0},
    {"id": 74, "city1": "Raleigh",        "city2": "Charleston",     "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    # --- East Coast ---
    {"id": 75, "city1": "Raleigh",        "city2": "Washington",     "length": 2, "color": "gray",   "double_group": "RAL-WAS", "side": 0},
    {"id": 76, "city1": "Raleigh",        "city2": "Washington",     "length": 2, "color": "gray",   "double_group": "RAL-WAS", "side": 1},
    {"id": 77, "city1": "Raleigh",        "city2": "Pittsburgh",     "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 78, "city1": "Washington",     "city2": "Pittsburgh",     "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 80, "city1": "Washington",     "city2": "New York",       "length": 2, "color": "orange", "double_group": "WAS-NY",  "side": 0},
    {"id": 81, "city1": "Washington",     "city2": "New York",       "length": 2, "color": "black",  "double_group": "WAS-NY",  "side": 1},
    {"id": 82, "city1": "Pittsburgh",     "city2": "New York",       "length": 2, "color": "white",  "double_group": "PIT-NY",  "side": 0},
    {"id": 83, "city1": "Pittsburgh",     "city2": "New York",       "length": 2, "color": "green",  "double_group": "PIT-NY",  "side": 1},
    {"id": 84, "city1": "Pittsburgh",     "city2": "Toronto",        "length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 85, "city1": "Pittsburgh",     "city2": "Saint Louis",    "length": 5, "color": "green",  "double_group": None,       "side": 0},
    {"id": 86, "city1": "New York",       "city2": "Boston",         "length": 2, "color": "yellow", "double_group": "NY-BOS",  "side": 0},
    {"id": 87, "city1": "New York",       "city2": "Boston",         "length": 2, "color": "red",    "double_group": "NY-BOS",  "side": 1},
    {"id": 88, "city1": "New York",       "city2": "Montreal",       "length": 3, "color": "blue",   "double_group": None,       "side": 0},
    # --- Northeast ---
    {"id": 89, "city1": "Boston",         "city2": "Montreal",       "length": 2, "color": "gray",   "double_group": "BOS-MON", "side": 0},
    {"id": 90, "city1": "Boston",         "city2": "Montreal",       "length": 2, "color": "gray",   "double_group": "BOS-MON", "side": 1},
    {"id": 91, "city1": "Montreal",       "city2": "Toronto",        "length": 3, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 92, "city1": "Montreal",       "city2": "Sault St. Marie","length": 5, "color": "black",  "double_group": None,       "side": 0},
    {"id": 93, "city1": "Toronto",        "city2": "Sault St. Marie","length": 2, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 94, "city1": "Toronto",        "city2": "Chicago",        "length": 4, "color": "white",  "double_group": None,       "side": 0},
    {"id": 95, "city1": "Duluth",         "city2": "Omaha",          "length": 2, "color": "gray",   "double_group": "DUL-OMA", "side": 1},
    {"id": 96, "city1": "Seattle",        "city2": "Calgary",        "length": 4, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 97, "city1": "Phoenix",        "city2": "Santa Fe",       "length": 3, "color": "gray",   "double_group": None,       "side": 0},
    {"id": 98, "city1": "El Paso",        "city2": "Oklahoma City",  "length": 5, "color": "yellow", "double_group": None,       "side": 0},
    {"id": 99, "city1": "Charleston",     "city2": "Miami",          "length": 4, "color": "pink",   "double_group": None,       "side": 0},
]

# 30 Destinations
DESTINATION_TICKETS = [
    {"id":  1, "city1": "Denver",         "city2": "El Paso",         "points":  4},
    {"id":  2, "city1": "Kansas City",    "city2": "Houston",         "points":  5},
    {"id":  3, "city1": "New York",       "city2": "Atlanta",         "points":  6},
    {"id":  4, "city1": "Chicago",        "city2": "New Orleans",     "points":  7},
    {"id":  5, "city1": "Calgary",        "city2": "Salt Lake City",  "points":  7},
    {"id":  6, "city1": "Helena",         "city2": "Los Angeles",     "points":  8},
    {"id":  7, "city1": "Duluth",         "city2": "Houston",         "points":  8},
    {"id":  8, "city1": "Sault St. Marie","city2": "Nashville",       "points":  8},
    {"id":  9, "city1": "Montreal",       "city2": "Atlanta",         "points":  9},
    {"id": 10, "city1": "Sault St. Marie","city2": "Oklahoma City",   "points":  9},
    {"id": 11, "city1": "Seattle",        "city2": "Los Angeles",     "points":  9},
    {"id": 12, "city1": "Chicago",        "city2": "Santa Fe",        "points":  9},
    {"id": 13, "city1": "Duluth",         "city2": "El Paso",         "points": 10},
    {"id": 14, "city1": "Toronto",        "city2": "Miami",           "points": 10},
    {"id": 15, "city1": "Portland",       "city2": "Phoenix",         "points": 11},
    {"id": 16, "city1": "Denver",         "city2": "Pittsburgh",      "points": 11},
    {"id": 17, "city1": "Winnipeg",       "city2": "Little Rock",     "points": 11},
    {"id": 18, "city1": "Dallas",         "city2": "New York",        "points": 11},
    {"id": 19, "city1": "Winnipeg",       "city2": "Houston",         "points": 12},
    {"id": 20, "city1": "Boston",         "city2": "Miami",           "points": 12},
    {"id": 21, "city1": "Vancouver",      "city2": "Santa Fe",        "points": 13},
    {"id": 22, "city1": "Calgary",        "city2": "Phoenix",         "points": 13},
    {"id": 23, "city1": "Montreal",       "city2": "New Orleans",     "points": 13},
    {"id": 24, "city1": "Los Angeles",    "city2": "Chicago",         "points": 16},
    {"id": 25, "city1": "Portland",       "city2": "Nashville",       "points": 17},
    {"id": 26, "city1": "San Francisco",  "city2": "Atlanta",         "points": 17},
    {"id": 27, "city1": "Vancouver",      "city2": "Montreal",        "points": 20},
    {"id": 28, "city1": "Los Angeles",    "city2": "Miami",           "points": 20},
    {"id": 29, "city1": "Los Angeles",    "city2": "New York",        "points": 21},
    {"id": 30, "city1": "Seattle",        "city2": "New York",        "points": 22},
]

# Build lookup helpers
ROUTE_BY_ID = {r["id"]: r for r in ROUTES}
TICKET_BY_ID = {t["id"]: t for t in DESTINATION_TICKETS}

# Groups of double-route IDs: group_name -> [route_id, route_id]
DOUBLE_ROUTE_GROUPS: dict[str, list[int]] = {}
for r in ROUTES:
    if r["double_group"]:
        DOUBLE_ROUTE_GROUPS.setdefault(r["double_group"], []).append(r["id"])

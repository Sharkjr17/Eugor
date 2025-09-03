# =========================
# ======= IMPORTS =========
# =========================
import time
import random
import sys, subprocess
import math
import json
import collections, html, copy
from prompt_toolkit import print_formatted_text as print, HTML, prompt as input
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.validation import Validator, ValidationError
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition

# =========================
# ======= DATA LOAD =======
# =========================
with open('data.json', 'r') as file:
    data = json.load(file)
with open('enemy.json', 'r') as file:
    enemy = json.load(file)
with open('item.json', 'r') as file:
    item = json.load(file)
with open('level.json', 'r') as file:
    level = json.load(file)
with open('dungeon.json', 'r') as file:
    dungeon = json.load(file)

# =========================
# ======= GLOBALS =========
# =========================

bindings = KeyBindings()

# Game state
crawl_mode = False
current_room_grid = None
player_pos = None
current_room_type = None
current_level_name = None
enemies = []  # list of (row, col) for all 'E' in current room
Stats = {}
inv = []

# =========================
# ======= TILE SET ========
# =========================
# Player & Entities
PLAYER_TILE = "@"
ENEMY_TILE = "E"

# Doors
TWO_WAY_DOOR = "&"   # can go both directions (matches updated JSON)
ONE_WAY_DOOR = ">"   # entrance or final exit

# Terrain
WALL_VERT = "|"
WALL_HORZ = "="
FLOOR_TILE = " "
WATER_TILE = "≈"     # water tile — impassable unless special rules added

# Optional: for future traps, loot, etc.
LOOT_TILE = "$"
TRAP_TILE = "^"

# Tile categories for quick checks
TILE_TYPES = {
    "walkable": {FLOOR_TILE, TWO_WAY_DOOR, ONE_WAY_DOOR},
    "blocking": {WALL_VERT, WALL_HORZ, WATER_TILE},
    "entity": {PLAYER_TILE, ENEMY_TILE}
}


# =========================
# ======= HELPERS =========
# =========================

def load_room(room_dict):
    """Convert a dict of numbered strings into a mutable 2D grid."""
    return [list(room_dict[str(i)]) for i in range(len(room_dict))]

def place_player(grid, pos):
    """Place the player character at the given (row, col) position in the grid."""
    grid[pos[0]][pos[1]] = PLAYER_TILE

def draw_room(grid):
    """Clear the screen and print the dungeon with colored tiles."""
    subprocess.run('clear', shell=True)

    color_map = {
        PLAYER_TILE: '<ansigreen>{}</ansigreen>',       # @ green
        ENEMY_TILE: '<ansired>{}</ansired>',           # E red
        TRAP_TILE: '<ansidarkgray>{}</ansidarkgray>',  # ^ dark gray
        WATER_TILE: '<ansiblue>{}</ansiblue>'          # ≈ blue
    }

    for row in grid:
        styled_row = []
        for ch in row:
            safe_ch = html.escape(ch)
            if ch in color_map:
                styled_row.append(color_map[ch].format(safe_ch))
            else:
                styled_row.append(safe_ch)
        print(HTML("".join(styled_row)))

def get_side(pos, grid):
    """Return which wall a position is on."""
    r, c = pos
    max_r = len(grid) - 1
    max_c = len(grid[0]) - 1
    if c == 0:
        return "left"
    if c == max_c:
        return "right"
    if r == 0:
        return "top"
    if r == max_r:
        return "bottom"
    return "unknown"

def opposite_side(side):
    """Return the opposite wall name."""
    return {
        "left": "right",
        "right": "left",
        "top": "bottom",
        "bottom": "top"
    }.get(side, "unknown")

def door_positions_on_side(grid, side, door_char=TWO_WAY_DOOR):
    """Find all door tiles of a given type on a specific wall."""
    max_r = len(grid) - 1
    max_c = len(grid[0]) - 1
    pos = []
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch != door_char:
                continue
            if side == "left" and c == 0:
                pos.append((r, c))
            elif side == "right" and c == max_c:
                pos.append((r, c))
            elif side == "top" and r == 0:
                pos.append((r, c))
            elif side == "bottom" and r == max_r:
                pos.append((r, c))
    if side in ("left", "right"):
        pos.sort(key=lambda x: x[0])
    else:
        pos.sort(key=lambda x: x[1])
    return pos

def get_spawn_in_front_of(door_pos, grid, side):
    """Spawn just inside the room from the given side; clamp and avoid walls."""
    r, c = door_pos
    max_r = len(grid) - 1
    max_c = len(grid[0]) - 1

    if side == "left":
        c = min(c + 1, max_c)
    elif side == "right":
        c = max(c - 1, 0)
    elif side == "top":
        r = min(r + 1, max_r)
    elif side == "bottom":
        r = max(r - 1, 0)

    if grid[r][c] in TILE_TYPES["blocking"]:
        return door_pos
    return (r, c)

def scan_for_enemies():
    """Find all enemy positions in the current room."""
    global enemies
    enemies = [(r, c) for r, row in enumerate(current_room_grid) for c, ch in enumerate(row) if ch == ENEMY_TILE]

def move_enemies():
    """Move each enemy one step toward the player, avoiding blocking tiles."""
    global enemies, player_pos, current_room_grid, crawl_mode

    new_positions = []
    for (er, ec) in enemies:
        dr = player_pos[0] - er
        dc = player_pos[1] - ec
        step_r, step_c = 0, 0
        if abs(dr) > abs(dc):
            step_r = 1 if dr > 0 else -1
        elif dc != 0:
            step_c = 1 if dc > 0 else -1

        target_r = er + step_r
        target_c = ec + step_c

        if (target_r, target_c) == tuple(player_pos):
            print("Enemy attacks!")
            crawl_mode = False
            return

        if current_room_grid[target_r][target_c] in TILE_TYPES["walkable"]:
            current_room_grid[er][ec] = FLOOR_TILE
            current_room_grid[target_r][target_c] = ENEMY_TILE
            new_positions.append((target_r, target_c))
        else:
            new_positions.append((er, ec))
    enemies = new_positions

def build_random_dungeon():
    """
    Build a random dungeon layout from handcrafted rooms in dungeon.json.
    - Start with a random 'enter' room.
    - Add random connector rooms while the current room has a right-side door.
    - Doors in connectors are coin-flipped, but the left entry side is preserved.
    - Place a final one-way exit on the last room that actually has a right-side door.
    Returns: list of (category, name, room_dict) tuples.
    """
    layout = []

    # 1) Starting room
    enter_name = random.choice(list(dungeon["enter"].keys()))
    current = copy.deepcopy(dungeon["enter"][enter_name])
    layout.append(("enter", enter_name, current))

    # 2) Grow the chain to the right only
    while has_right_door(current):
        connector_name = random.choice(list(dungeon["rooms"].keys()))
        connector = copy.deepcopy(dungeon["rooms"][connector_name])

        # Randomize doors but guarantee a left-side door to accept entry
        randomize_doors(connector, preserve_side="left")

        layout.append(("rooms", connector_name, connector))
        current = connector

    # 3) Ensure an exit exists on the last room that has a right-side door
    place_exit_in_last_right_door(layout)

    return layout

def has_right_door(room_dict):
    """True if any row has a two-way door at the rightmost column."""
    right_idx = max(len(v) for v in room_dict.values()) - 1
    return any(row[right_idx] == TWO_WAY_DOOR for row in room_dict.values())

def place_exit_in_last_right_door(layout):
    """Walk layout backwards and convert the last right-side & into a >."""
    for i in range(len(layout) - 1, -1, -1):
        _, _, room = layout[i]
        right_idx = max(len(v) for v in room.values()) - 1
        for k in room:
            row = room[k]
            if row[right_idx] == TWO_WAY_DOOR:
                room[k] = row[:-1] + ONE_WAY_DOOR
                return


    """Check if any tile in the rightmost column is a two-way door."""
    for row in room_dict.values():
        if row[-1] == TWO_WAY_DOOR:
            return True
    return False

def randomize_doors(room_dict, preserve_side=None):
    """
    50% chance to remove each two-way door in the room.
    If preserve_side is provided ('left', 'right', 'top', 'bottom'),
    a door on that wall is guaranteed to exist after randomization.
    """
    # First pass: flip coins on all & tiles
    for key, row in room_dict.items():
        row_list = list(row)
        for i, ch in enumerate(row_list):
            if ch == TWO_WAY_DOOR and random.random() < 0.5:
                # Replace with wall if on an edge, otherwise floor
                if i == 0 or i == len(row_list) - 1:
                    row_list[i] = WALL_VERT
                else:
                    row_list[i] = FLOOR_TILE
        room_dict[key] = "".join(row_list)

    if preserve_side is None:
        return

    # Second pass: ensure at least one door exists on the preserved side
    if preserve_side in ("left", "right"):
        # Column index to enforce
        enforce_idx = 0 if preserve_side == "left" else max(len(v) for v in room_dict.values()) - 1
        # If any row already has &, we're good
        if any(room_dict[k][enforce_idx] == TWO_WAY_DOOR for k in room_dict):
            return
        # Otherwise, place a door near the vertical middle on that edge
        mid = str(len(room_dict) // 2)
        if mid in room_dict:
            row = list(room_dict[mid])
            row[enforce_idx] = TWO_WAY_DOOR
            room_dict[mid] = "".join(row)
        else:
            # Fallback: first row
            first = str(0)
            row = list(room_dict[first])
            row[enforce_idx] = TWO_WAY_DOOR
            room_dict[first] = "".join(row)

def replace_right_door_with_exit(room_dict):
    """Find a right-side two-way door and replace it with a one-way exit."""
    for key, row in room_dict.items():
        if row[-1] == TWO_WAY_DOOR:
            room_dict[key] = row[:-1] + ONE_WAY_DOOR
            return

# =========================
# ======= MOVEMENT ========
# =========================
def grid_has_side_door(grid, side, door_char=TWO_WAY_DOOR):
    """Check a list-of-lists grid for a door on a true edge column/row."""
    max_r = len(grid) - 1
    max_c = len(grid[0]) - 1
    if side == "left":
        return any(grid[r][0] == door_char for r in range(len(grid)))
    if side == "right":
        return any(grid[r][max_c] == door_char for r in range(len(grid)))
    if side == "top":
        return any(ch == door_char for ch in grid[0])
    if side == "bottom":
        return any(ch == door_char for ch in grid[max_r])
    return False

def player_move(dr, dc):
    global player_pos, current_room_grid, current_room_type, current_level_name, crawl_mode, dungeon_sequence

    new_r = player_pos[0] + dr
    new_c = player_pos[1] + dc

    # Bounds
    if not (0 <= new_r < len(current_room_grid) and 0 <= new_c < len(current_room_grid[0])):
        return

    target = current_room_grid[new_r][new_c]

    # Blockers
    if target in TILE_TYPES["blocking"]:
        return

    # Enemy
    if target == ENEMY_TILE:
        print("You engage the enemy!")
        crawl_mode = False
        return

    # Two-way door
    if target == TWO_WAY_DOOR:
        exit_side = get_side((new_r, new_c), current_room_grid)

        # Only the right-side door advances the chain
        if exit_side != "right":
            print("The door leads nowhere.")
            return

        if not dungeon_sequence:
            print("The way forward is sealed.")
            return

        # Peek next room (don’t pop until validated)
        _, next_room_type, room_dict = dungeon_sequence[0]
        next_grid = load_room(room_dict)

        # Must have a left-side door to accept entry
        if not grid_has_side_door(next_grid, "left", TWO_WAY_DOOR):
            print("The door is bricked shut.")
            return

        # Valid: commit transition
        dungeon_sequence.pop(0)
        current_room_grid = next_grid

        # Spawn just inside the left door
        next_wall_doors = door_positions_on_side(current_room_grid, "left", TWO_WAY_DOOR)
        spawn_door = next_wall_doors[0]
        spawn_pos = get_spawn_in_front_of(spawn_door, current_room_grid, "left")

        # Move player
        current_room_grid[player_pos[0]][player_pos[1]] = FLOOR_TILE
        player_pos = list(spawn_pos)
        place_player(current_room_grid, player_pos)
        scan_for_enemies()
        draw_room(current_room_grid)
        return

    # One-way exit
    if target == ONE_WAY_DOOR:
        print("You exit the dungeon!")
        crawl_mode = False
        return

    # Regular movement
    current_room_grid[player_pos[0]][player_pos[1]] = FLOOR_TILE
    player_pos = [new_r, new_c]
    place_player(current_room_grid, player_pos)
    move_enemies()
    draw_room(current_room_grid)

# =========================
# ======= KEYBINDS ========
# =========================
@Condition
def is_crawl():
    return crawl_mode

@bindings.add("w", filter=is_crawl)
def _(event):
    player_move(-1, 0)

@bindings.add("s", filter=is_crawl)
def _(event):
    player_move(1, 0)

@bindings.add("a", filter=is_crawl)
def _(event):
    player_move(0, -1)

@bindings.add("d", filter=is_crawl)
def _(event):
    player_move(0, 1)

# =========================
# ======= GAME FLOW =======
# =========================
def dung(alevel):
    """
    Build and enter a random dungeon layout for the given level type.
    Uses handcrafted rooms from dungeon.json, randomizes door presence,
    and ends with a one-way exit.
    """
    global crawl_mode, current_room_grid, player_pos, current_room_type, current_level_name, dungeon_sequence

    current_level_name = alevel

    # Build a randomized sequence of rooms (deep copies)
    dungeon_sequence = build_random_dungeon()

    # Start with the first room in the sequence
    _, current_room_type, room_dict = dungeon_sequence.pop(0)
    current_room_grid = load_room(room_dict)  # convert dict -> list of lists

    # Find the player start position (look for '@' or default to row 4, col 1)
    start_pos = None
    for r, row in enumerate(current_room_grid):
        if PLAYER_TILE in row:
            start_pos = [r, row.index(PLAYER_TILE)]
            break
    if not start_pos:
        start_pos = [4, 1]

    player_pos = start_pos
    place_player(current_room_grid, player_pos)

    scan_for_enemies()
    crawl_mode = True

    while crawl_mode:
        draw_room(current_room_grid)
        input("", key_bindings=bindings)


def move():
    """
    Overworld path selection.
    Picks a random set of level options, shows descriptions,
    and routes to the correct handler. Dungeon levels are loaded
    from dungeon.json based on the chosen level type.
    """
    # Randomly choose between 2 and 5 paths
    pathChoices = random.randint(2, 5)
    pathWeight = [level[i]["weight"] for i in level]
    pathView = random.choices(list(level.keys()), weights=pathWeight, k=pathChoices)

    # Display available paths
    for i in range(pathChoices):
        print(f"{i+1}.) {pathView[i]}: {level[pathView[i]]['description']}\n")

    # Get player choice
    valid = False
    while not valid:
        choice = input(f"Select path (1-{pathChoices}) --> ")
        if choice.isdigit():
            choice_num = int(choice)
            if 1 <= choice_num <= pathChoices:
                valid = True

    chosen_level = pathView[int(choice) - 1]
    subprocess.run('clear', shell=True)

    # Route to correct handler
    match level[chosen_level]["type"]:
        case "dung":
            dung(chosen_level)
        case "buff":
            buff(chosen_level)
        case "shop":
            shop(chosen_level)
        case "boss":
            boss(chosen_level)

# =========================
# ======= PLACEHOLDERS ====
# =========================
def buff(alevel):
    print(f"Buff location: {alevel}")

def shop(alevel):
    print(f"Shop location: {alevel}")

def boss(alevel):
    print(f"Boss location: {alevel}")

# =========================
# ======= GAME START ======
# =========================
def run():
    global Stats, inv
    _ = input("|--Press Enter to Continue--|")
    subprocess.run('clear', shell=True)

    difficulty = None
    while difficulty is None:
        i = input(HTML(data["Difficulty Prompt"]), bottom_toolbar=HTML(data["Difficulty Prompt Toolbar"]))
        match i.upper():
            case "A":
                difficulty = "easy"
                Stats.update([("maxHP", 500), ("HP", 500), ("strengthMult", 2)])
                inv.append(item["Copper Sword"])
            case "B":
                difficulty = "intermediate"
                Stats.update([("maxHP", 500), ("HP", 500), ("strengthMult", 1.25)])
                inv.append(item["Copper Sword"])
            case "C":
                difficulty = "hard"
                Stats.update([("maxHP", 250), ("HP", 250), ("strengthMult", 1)])
                inv.append(item["Copper Sword"])
            case "D":
                difficulty = "impossible"
                Stats.update([("maxHP", 100), ("HP", 100), ("strengthMult", 0.5)])
                inv.append(item["Copper Dagger"])
        subprocess.run('clear', shell=True)

    print(HTML(f"<b>{data['Intro Text 1'][difficulty]}</b>"))
    print(Stats)
    print(inv)

    # Start overworld
    move()

# =========================
# ======= ENTRY POINT =====
# =========================
if __name__ == "__main__":
    run()

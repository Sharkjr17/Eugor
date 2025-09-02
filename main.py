# =========================
# ======= IMPORTS =========
# =========================
import time
import random
import sys, subprocess
import math
import json
import collections, html
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

# =========================
# ======= GLOBALS =========
# =========================
bindings = KeyBindings()
crawl_mode = False
current_room_grid = None
player_pos = None
current_room_type = None
current_level_name = None
enemies = []  # list of (row, col) for all 'E' in current room
Stats = {}
inv = []
dungeon = {}

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

# ===== Procedural Dungeon Generation with Connections =====
DIRS = {
    "N": (0, -1),
    "S": (0, 1),
    "W": (-1, 0),
    "E": (1, 0)
}
OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}

def generate_dungeon(level_name):
    """Generate a dungeon layout using parameters from level.json."""
    global dungeon, dungeon_connections
    dungeon[level_name] = {}
    dungeon_connections = {level_name: {}}

    params = level[level_name]
    enemy_range = tuple(params.get("enemy_range", (1, 2)))
    trap_chance = params.get("trap_chance", 0.05)
    pond_chance = params.get("pond_chance", 0.2)
    num_rooms = params.get("num_rooms", 6)
    deadend_chance = params.get("deadend_chance", 0.3)

    placed = {}
    start_pos = (0, 0)
    placed[start_pos] = ("enter", make_room(enemy_range, trap_chance, pond_chance, is_entrance=True))
    dungeon_connections[level_name]["enter"] = {}

    frontier = [start_pos]

    while len(placed) < num_rooms and frontier:
        pos = random.choice(frontier)
        dirs = list(DIRS.keys())
        random.shuffle(dirs)
        expanded = False

        for d in dirs:
            dx, dy = DIRS[d]
            new_pos = (pos[0] + dx, pos[1] + dy)
            if new_pos in placed:
                continue
            room_name = f"room{len(placed)}"
            new_room = make_room(enemy_range, trap_chance, pond_chance)
            connect_rooms(placed[pos][1], new_room, d)
            placed[new_pos] = (room_name, new_room)

            dungeon_connections[level_name].setdefault(placed[pos][0], {})[d] = room_name
            dungeon_connections[level_name][room_name] = {OPPOSITE[d]: placed[pos][0]}

            if random.random() > deadend_chance and len(placed) < num_rooms:
                frontier.append(new_pos)
            expanded = True
            break

        if not expanded:
            frontier.remove(pos)

    farthest_pos = find_farthest_room(start_pos, placed)
    place_exit(placed[farthest_pos][1])

    for name, grid in placed.values():
        dungeon[level_name][name] = grid_to_room_dict(grid)

def make_room(enemy_range, trap_chance, pond_chance, is_entrance=False):
    shape_type = random.choice(["square", "rect", "circle"])
    if shape_type == "square":
        grid = blank_grid(random.randint(15, 20), random.randint(15, 20))
    elif shape_type == "rect":
        grid = blank_grid(random.randint(18, 24), random.randint(12, 16))
    else:
        grid = circle_room(random.randint(8, 10))

    add_ponds(grid, pond_chance)
    add_enemies(grid, enemy_range)
    add_traps(grid, trap_chance)

    if is_entrance:
        grid[len(grid)//2][0] = ONE_WAY_DOOR
    return grid

def blank_grid(width, height):
    grid = [[FLOOR_TILE for _ in range(width)] for _ in range(height)]
    for r in range(height):
        for c in range(width):
            if r == 0 or r == height - 1:
                grid[r][c] = WALL_HORZ
            elif c == 0 or c == width - 1:
                grid[r][c] = WALL_VERT
    return grid

def circle_room(radius):
    size = radius * 2 + 1
    grid = [[FLOOR_TILE for _ in range(size)] for _ in range(size)]
    center = radius
    for r in range(size):
        for c in range(size):
            dist = math.sqrt((r - center) ** 2 + (c - center) ** 2)
            if dist > radius + 0.3:  # loosened to keep more floor
                grid[r][c] = " "
    for r in range(size):
        for c in range(size):
            if grid[r][c] == FLOOR_TILE:
                for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    rr, cc = r+dr, c+dc
                    if 0 <= rr < size and 0 <= cc < size and grid[rr][cc] == " ":
                        grid[rr][cc] = WALL_VERT if dc == 0 else WALL_HORZ
    return grid

def add_ponds(grid, pond_chance):
    ponds = 0
    while ponds < 2 and random.random() < pond_chance:
        pr = random.randint(1, len(grid)-2)
        pc = random.randint(1, len(grid[0])-2)
        if grid[pr][pc] == FLOOR_TILE:
            grid[pr][pc] = WATER_TILE
            ponds += 1

def add_enemies(grid, enemy_range):
    count = random.randint(*enemy_range)
    placed = 0
    while placed < count:
        er = random.randint(1, len(grid)-2)
        ec = random.randint(1, len(grid[0])-2)
        if grid[er][ec] == FLOOR_TILE:
            grid[er][ec] = ENEMY_TILE
            placed += 1

def add_traps(grid, trap_chance):
    door_positions = [(r, c) for r, row in enumerate(grid) for c, ch in enumerate(row) if ch in (TWO_WAY_DOOR, ONE_WAY_DOOR)]
    for r in range(1, len(grid)-1):
        for c in range(1, len(grid[0])-1):
            if grid[r][c] == FLOOR_TILE and random.random() < trap_chance:
                # Skip doors and adjacent tiles
                if any(abs(r-dr) <= 1 and abs(c-dc) <= 1 for dr, dc in door_positions):
                    continue
                grid[r][c] = TRAP_TILE

def connect_rooms(grid_a, grid_b, direction):
    if direction == "E":
        grid_a[len(grid_a)//2][-1] = TWO_WAY_DOOR
        grid_b[len(grid_b)//2][0] = TWO_WAY_DOOR
    elif direction == "W":
        grid_a[len(grid_a)//2][0] = TWO_WAY_DOOR
        grid_b[len(grid_b)//2][-1] = TWO_WAY_DOOR
    elif direction == "N":
        grid_a[0][len(grid_a[0])//2] = TWO_WAY_DOOR
        grid_b[-1][len(grid_b[0])//2] = TWO_WAY_DOOR
    elif direction == "S":
        grid_a[-1][len(grid_a[0])//2] = TWO_WAY_DOOR
        grid_b[0][len(grid_b[0])//2] = TWO_WAY_DOOR

def find_farthest_room(start_pos, placed):
    """BFS to find farthest room coordinate from start."""
    visited = {start_pos}
    queue = collections.deque([(start_pos, 0)])
    farthest = start_pos
    max_dist = 0
    while queue:
        pos, dist = queue.popleft()
        if dist > max_dist:
            max_dist = dist
            farthest = pos
        for d in DIRS.values():
            neighbor = (pos[0] + d[0], pos[1] + d[1])
            if neighbor in placed and neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))
    return farthest

def place_exit(grid):
    """Replace a right wall door with a one-way exit door."""
    for r in range(len(grid)):
        if grid[r][-1] == TWO_WAY_DOOR:
            grid[r][-1] = ONE_WAY_DOOR
            break

def grid_to_room_dict(grid):
    """Convert a 2D grid into the dict format used by load_room()."""
    return {str(i): "".join(row) for i, row in enumerate(grid)}

def find_connected_room(level_name, current_room, exit_side):
    """
    Look up the connected room name from the stored dungeon_connections map.
    """
    if level_name in dungeon_connections:
        if current_room in dungeon_connections[level_name]:
            return dungeon_connections[level_name][current_room].get(exit_side)
    return None


# =========================
# ======= MOVEMENT ========
# =========================
def player_move(dr, dc):
    global player_pos, current_room_grid, current_room_type, current_level_name, crawl_mode

    new_r = player_pos[0] + dr
    new_c = player_pos[1] + dc

    # Bounds check
    if not (0 <= new_r < len(current_room_grid) and 0 <= new_c < len(current_room_grid[0])):
        return

    target_tile = current_room_grid[new_r][new_c]

    # Block walls, water, and other blocking tiles
    if target_tile in TILE_TYPES["blocking"]:
        return

    # Prevent walking into an enemy unless initiating combat
    if target_tile == ENEMY_TILE:
        print("You engage the enemy!")
        crawl_mode = False  # Placeholder for combat system
        return

    # Handle two-way door (&)
    if target_tile == TWO_WAY_DOOR:
        exit_side = get_side((new_r, new_c), current_room_grid)
        connected_room_name = find_connected_room(current_level_name, current_room_type, exit_side)

        if not connected_room_name:
            print("This door doesn't seem to lead anywhere...")
            return

        enter_side = opposite_side(exit_side)
        next_grid = load_room(dungeon[current_level_name][connected_room_name])

        # Find the matching door in the new room
        next_wall_doors = door_positions_on_side(next_grid, enter_side, TWO_WAY_DOOR)
        if not next_wall_doors:
            next_wall_doors = [(r, c) for r, row in enumerate(next_grid) for c, ch in enumerate(row) if ch == TWO_WAY_DOOR]
            next_wall_doors.sort(key=lambda x: (x[0], x[1]))

        spawn_door = next_wall_doors[0] if next_wall_doors else (0, 0)
        spawn_pos = get_spawn_in_front_of(spawn_door, next_grid, enter_side)

        current_room_grid = next_grid
        current_room_type = connected_room_name
        player_pos = list(spawn_pos)
        place_player(current_room_grid, player_pos)
        scan_for_enemies()
        draw_room(current_room_grid)
        return

    # Handle one-way door (>)
    if target_tile == ONE_WAY_DOOR:
        print("You exit the dungeon!")
        crawl_mode = False
        return

    # Regular movement
    current_room_grid[player_pos[0]][player_pos[1]] = FLOOR_TILE
    player_pos = [new_r, new_c]
    place_player(current_room_grid, player_pos)

    # Enemy AI turn
    move_enemies()

    # Redraw after movement
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
    Enter a dungeon level.
    Procedurally generates the dungeon layout for the given level name
    using parameters from level.json, places the player at the left-side
    one-way door in the entrance room, ensures spawn space, scans for enemies,
    and starts the crawl loop.
    """
    global crawl_mode, current_room_grid, player_pos, current_room_type, current_level_name

    # Generate a fresh dungeon layout for this run using level.json parameters
    generate_dungeon(alevel)

    current_level_name = alevel
    current_room_type = "enter"

    # Load the starting room from the generated dungeon
    current_room_grid = load_room(dungeon[current_level_name][current_room_type])

    # Find the left-side one-way door in the entrance room
    left_doors = door_positions_on_side(current_room_grid, "left", ONE_WAY_DOOR)
    if left_doors:
        spawn_door = left_doors[0]
        player_pos = list(get_spawn_in_front_of(spawn_door, current_room_grid, "left"))
    else:
        # Fallback: center spawn if no left door found
        player_pos = [len(current_room_grid)//2, 2]

    # Place player and ensure at least one adjacent walkable tile
    place_player(current_room_grid, player_pos)
    ensure_spawn_space(current_room_grid, player_pos)

    # Scan for any pre‑placed enemies
    scan_for_enemies()

    # Enable crawl mode so keybinds work
    crawl_mode = True

    # Main dungeon loop
    while crawl_mode:
        draw_room(current_room_grid)
        input("", key_bindings=bindings)


def ensure_spawn_space(grid, spawn_pos):
    """
    Make sure the spawn position has at least one adjacent walkable tile.
    If all adjacent tiles are blocking, carve one into a floor tile.
    """
    r, c = spawn_pos
    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
        rr, cc = r+dr, c+dc
        if 0 <= rr < len(grid) and 0 <= cc < len(grid[0]):
            if grid[rr][cc] not in TILE_TYPES["blocking"]:
                return  # Already has a walkable tile
    # If we got here, all adjacent are blocking — carve one
    rr, cc = r, c+1 if c+1 < len(grid[0]) else c-1
    grid[rr][cc] = FLOOR_TILE

def move():
    """
    Overworld path selection.
    Picks a random set of level options, shows descriptions,
    and routes to the correct handler. Dungeon levels are generated procedurally
    using parameters from level.json.
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
            # Generate and enter dungeon using parameters from level.json
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

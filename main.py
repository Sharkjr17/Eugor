# =========================
# ======= IMPORTS =========
# =========================
import time, random, sys, subprocess, json, math, collections, html, copy
from collections import deque
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
current_dungeon_key = None
enemies = []  # list of (row, col) for all 'E' in current room
Stats = {}
dStats = {}
inv = []

# =========================
# ======= TILE SET ========
# =========================
# Player & Entities
PLAYER_TILE = "@"
ENEMY_TILE = "E"  # Regular enemy

# Doors
EXIT_DOOR = "&"   # can go both directions (matches updated JSON)

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
    "walkable": {FLOOR_TILE, EXIT_DOOR},
    "blocking": {WALL_VERT, WALL_HORZ, WATER_TILE},
    "entity": {PLAYER_TILE, "E", "P", "R", "F"}  # all enemy types + player
}


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
# ======== DUNGEON ========
# =========================
def generate_patrol_path(r, c, etype=None):
    """
    Auto-generate a straight patrol path for an enemy based on its movement rules.
    Currently used for P (Patrolling) enemies, but supports all types.
    """
    rows, cols = len(current_room_grid), len(current_room_grid[0])
    if etype is None:
        etype = "P"

    # Movement rules unified with BFS can_step()
    def can_step(tile):
        if etype in {"E", "P"}:  # Regular & Patrol — avoid traps and water
            return tile in TILE_TYPES["walkable"]
        elif etype == "R":       # Reckless — can step on traps/water
            return tile not in TILE_TYPES["blocking"]
        elif etype == "F":       # Flying — ignores traps/water
            return tile not in {WALL_VERT, WALL_HORZ}
        return False

    best_path = []
    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
        path = []
        nr, nc = r + dr, c + dc
        while 0 <= nr < rows and 0 <= nc < cols:
            tile = current_room_grid[nr][nc]
            # Stop if another entity is in the way
            if tile in TILE_TYPES["entity"]:
                break
            if not can_step(tile):
                break
            path.append((nr, nc))
            nr += dr
            nc += dc
        if len(path) > len(best_path):
            best_path = path

    # Patrol path is forward then backward
    return best_path + list(reversed(best_path))

def draw_room(grid):
    """Clear the screen and print the dungeon grid with basic colors."""
    import os
    subprocess.run('cls' if os.name == 'nt' else 'clear', shell=True)
    color_map = {
        PLAYER_TILE: '<ansigreen>{}</ansigreen>',
        "E": '<ansired>{}</ansired>',
        "P": '<ansiyellow>{}</ansiyellow>',
        "R": '<ansimagenta>{}</ansimagenta>',
        "F": '<ansiblue>{}</ansiblue>',
        TRAP_TILE: '<ansidarkgray>{}</ansidarkgray>',
        WATER_TILE: '<ansiblue>{}</ansiblue>'
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

def player_move(dr, dc):
    global player_pos, current_room_grid, crawl_mode, enemies

    new_r = player_pos[0] + dr
    new_c = player_pos[1] + dc

    # Bounds check
    if not (0 <= new_r < len(current_room_grid) and 0 <= new_c < len(current_room_grid[0])):
        return

    target = current_room_grid[new_r][new_c]

    # Blockers
    if target in TILE_TYPES["blocking"]:
        return

    # Trap handling for player
    if target == TRAP_TILE:
        print("You hit a trap and take X damage!")
        current_room_grid[new_r][new_c] = FLOOR_TILE

        # Enemy encounter
    if target in TILE_TYPES["entity"] and target != PLAYER_TILE:
        crawl_mode = False
        subprocess.run('clear', shell=True)  # clear dungeon view
        print("You engage the enemy!")
        start_encounter(current_dungeon_key)  # prints encounter UI + enemies
        return

    # Exit
    if target == EXIT_DOOR:
        print("You exit the dungeon!")
        crawl_mode = False
        draw_room(current_room_grid)
        return

    # Move player
    current_room_grid[player_pos[0]][player_pos[1]] = FLOOR_TILE
    player_pos = [new_r, new_c]
    current_room_grid[player_pos[0]][player_pos[1]] = PLAYER_TILE

    # BFS pathfinding with E avoiding traps
    def bfs_path(start, goal, etype):
        rows, cols = len(current_room_grid), len(current_room_grid[0])
        queue = deque([(start, [])])
        visited = {start}

        def can_step(tile):
            if etype == "E":  # Regular — only walkable tiles (floor, exit)
                return tile in TILE_TYPES["walkable"]
            elif etype == "P":  # Patrol
                return tile in TILE_TYPES["walkable"]
            elif etype == "R":  # Reckless
                return tile not in TILE_TYPES["blocking"]
            elif etype == "F":  # Flying
                return tile not in {WALL_VERT, WALL_HORZ}
            return False

        while queue:
            (r, c), path = queue.popleft()
            if (r, c) == goal:
                return path
            for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    tile = current_room_grid[nr][nc]
                    if (nr, nc) not in visited and can_step(tile):
                        visited.add((nr, nc))
                        queue.append(((nr, nc), path + [(nr, nc)]))
        return None

    # Enemy movement
    new_positions = []
    for (er, ec, etype, patrol, under_tile) in enemies:
        sees_player = False
        if etype == "P":
            if er == player_pos[0]:
                step = 1 if ec < player_pos[1] else -1
                if all(current_room_grid[er][c] not in TILE_TYPES["blocking"] for c in range(ec+step, player_pos[1], step)):
                    sees_player = True
            elif ec == player_pos[1]:
                step = 1 if er < player_pos[0] else -1
                if all(current_room_grid[r][ec] not in TILE_TYPES["blocking"] for r in range(er+step, player_pos[0], step)):
                    sees_player = True

        if etype == "P" and not sees_player and patrol:
            next_pos = patrol.pop(0)
            patrol.append(next_pos)
            nr, nc = next_pos
            if current_room_grid[nr][nc] == PLAYER_TILE:
                print("Enemy attacks!")
                crawl_mode = False
                draw_room(current_room_grid)
                return
            current_room_grid[er][ec] = under_tile
            new_under = current_room_grid[nr][nc]
            current_room_grid[nr][nc] = etype
            new_positions.append((nr, nc, etype, patrol, new_under))
            continue

        path = bfs_path((er, ec), tuple(player_pos), etype)

        # Wander fallback for E if no path found
        if etype == "E" and not path:
            for dr_f, dc_f in random.sample([(-1,0),(1,0),(0,-1),(0,1)], 4):
                nr, nc = er + dr_f, ec + dc_f
                if 0 <= nr < len(current_room_grid) and 0 <= nc < len(current_room_grid[0]):
                    tile = current_room_grid[nr][nc]
                    if tile in TILE_TYPES["walkable"]:
                        path = [(nr, nc)]
                        break

        if path and len(path) > 0:
            nr, nc = path[0]
            if (nr, nc) == tuple(player_pos):
                crawl_mode = False
                subprocess.run('clear', shell=True)  # hide dungeon
                print("Enemy attacks!")
                start_encounter(current_dungeon_key)  # same encounter UI as player-initiated
                return
            if etype == "R" and current_room_grid[nr][nc] in {TRAP_TILE, WATER_TILE}:
                current_room_grid[er][ec] = under_tile
                print("A reckless enemy perished in a hazard!")
                continue
            current_room_grid[er][ec] = under_tile
            new_under = current_room_grid[nr][nc]
            current_room_grid[nr][nc] = etype
            new_positions.append((nr, nc, etype, patrol, new_under))
        else:
            new_positions.append((er, ec, etype, patrol, under_tile))
    enemies = new_positions
    
    draw_room(current_room_grid)

def dung(alevel):
    global crawl_mode, current_room_grid, player_pos, enemies, current_dungeon_key

    # Remember the current dungeon key (e.g., "paved")
    current_dungeon_key = alevel

    room_name = random.choice(list(dungeon[alevel].keys()))
    room_dict = copy.deepcopy(dungeon[alevel][room_name])
    current_room_grid = [list(room_dict[str(i)]) for i in sorted(map(int, room_dict.keys()))]


    player_pos = None
    for r, row in enumerate(current_room_grid):
        if PLAYER_TILE in row:
            player_pos = [r, row.index(PLAYER_TILE)]
            break
    if not player_pos:
        player_pos = [4, 1]
        current_room_grid[player_pos[0]][player_pos[1]] = PLAYER_TILE

    enemies = []
    for r, row in enumerate(current_room_grid):
        for c, ch in enumerate(row):
            if ch in TILE_TYPES["entity"] and ch != PLAYER_TILE:
                patrol_path = generate_patrol_path(r, c, ch) if ch == "P" else None
                # Store the tile underneath — assume floor unless you track it in JSON
                under_tile = FLOOR_TILE
                enemies.append((r, c, ch, patrol_path, under_tile))

    crawl_mode = True
    draw_room(current_room_grid)
    while crawl_mode:
        input("", key_bindings=bindings)

# =========================
# ======= ENCOUNTER =======
# =========================

def start_encounter(dungeon_key):
    """
    Minimal encounter picker with difficulty scaling from dStats:
    - Adjusts max threat by dStats["threatBonus"].
    - Adjusts enemy count by dStats["enemyBonus"].
    - Filters enemy.json by enemy.threat <= adjusted threat.
    - Prints a header and the encounter list with enemy health.
    - Stores encounter enemies in dStats["enemies"] for combat tracking.
    """

    threat = level[dungeon_key].get("threat", 1) + dStats.get("threatBonus", 0)

    print(f"\n{dungeon_key}: Threat {threat}\n" + "-" * 30)

    # Base enemy count logic
    if threat == 1:
        num_enemies = random.randint(1, 2)
    else:
        num_enemies = 1

    # Apply difficulty enemy bonus
    num_enemies += dStats.get("enemyBonus", 0)

    # Filter valid enemies by adjusted threat
    valid = [name for name, stats in enemy.items() if stats.get("threat", 1) <= threat]
    if not valid:
        print(f"No valid enemies for threat {threat}.")
        return []

    chosen = [random.choice(valid) for _ in range(num_enemies)]

    # Store encounter enemies in dStats for combat
    dStats["enemies"] = []
    print("Enemies:")
    for name in chosen:
        hp = enemy[name].get("Health", "?")
        dStats["enemies"].append({"name": name, "hp": hp})
        print(f" - {name} ({hp} HP)")

    return chosen


# =========================
# ======= GAME FLOW =======
# =========================

def move():
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
    global Stats, inv, difficulty
    _ = input("|--Press Enter to Continue--|")
    subprocess.run('clear', shell=True)

    difficulty = None
    while difficulty is None:
        i = input(HTML(data["Difficulty Prompt"]), bottom_toolbar=HTML(data["Difficulty Prompt Toolbar"]))
        match i.upper():
            case "A":
                difficulty = "easy"
                dStats.update([("threatBonus", 0), ("enemyBonus", 0)])
                Stats.update([("maxHP", 500), ("HP", 500), ("strengthMult", 2)])
                inv.append(item["Copper Sword"])
            case "B":
                difficulty = "intermediate"
                dStats.update([("threatBonus", 0), ("enemyBonus", 0)])
                Stats.update([("maxHP", 500), ("HP", 500), ("strengthMult", 1.25)])
                inv.append(item["Copper Sword"])
            case "C":
                difficulty = "hard"
                dStats.update([("threatBonus", 1), ("enemyBonus", 0)])
                Stats.update([("maxHP", 250), ("HP", 250), ("strengthMult", 1)])
                inv.append(item["Copper Sword"])
            case "D":
                difficulty = "impossible"
                dStats.update([("threatBonus", 3), ("enemyBonus", 1)])
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


import random
import sys
from collections import deque

import pygame

# ============================================================
# 1. GAME SETTINGS
# ============================================================

pygame.init()

TILE = 32
COLS = 20
ROWS = 15

HUD_HEIGHT = 65
SIDEBAR_WIDTH = 220
MARGIN = 20

WORLD_WIDTH = COLS * TILE
WORLD_HEIGHT = ROWS * TILE

SCREEN_WIDTH = WORLD_WIDTH + SIDEBAR_WIDTH + MARGIN * 3
SCREEN_HEIGHT = WORLD_HEIGHT + HUD_HEIGHT + MARGIN * 2

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Treasure Hunt - Escape the Guard")

clock = pygame.time.Clock()

FONT = pygame.font.SysFont("arial", 18)
SMALL_FONT = pygame.font.SysFont("arial", 14)
BIG_FONT = pygame.font.SysFont("arial", 34, bold=True)

# Colours
BLACK = (20, 22, 30)
WHITE = (245, 245, 245)
WALL_COLOR = (55, 62, 75)
FLOOR_COLOR = (105, 125, 91)
FLOOR_ALT = (113, 133, 98)
GRID_COLOR = (80, 95, 70)
GOLD = (255, 205, 55)
RED = (225, 65, 65)
DARK_RED = (135, 30, 35)
BLUE = (70, 155, 245)
GREEN = (65, 210, 120)
PURPLE = (175, 110, 240)
PANEL_COLOR = (35, 39, 51)

WALL = 0
FLOOR = 1
TRAP = 2

NUM_TRAPS = 18

# Player and guard movement intervals
PLAYER_MOVE_DELAY = 0.14
GUARD_MOVE_DELAY = 0.45

# The guard detects the player within this path distance.
GUARD_DETECTION_RANGE = 4

# ============================================================
# 2. MAP GENERATION
# ============================================================

def room_center(room):
    x, y, width, height = room
    return (x + width // 2, y + height // 2)


def generate_world():
    """Generate a connected map with randomly positioned rooms."""

    rooms = []

    # Generate six non-overlapping rooms.
    for attempt in range(10000):
        width = random.randint(4, 6)
        height = random.randint(3, 5)

        x = random.randint(1, COLS - width - 1)
        y = random.randint(1, ROWS - height - 1)

        new_room = pygame.Rect(x, y, width, height)

        overlaps = False

        for rx, ry, rw, rh in rooms:
            existing_room = pygame.Rect(rx, ry, rw, rh)

            if new_room.inflate(1, 1).colliderect(existing_room):
                overlaps = True
                break

        if not overlaps:
            rooms.append((x, y, width, height))

        if len(rooms) == 6:
            break

    if len(rooms) < 5:
        raise RuntimeError(
            "Could not generate enough rooms. Please restart the game."
        )

    random.shuffle(rooms)

    grid = [[WALL for _ in range(COLS)] for _ in range(ROWS)]

    # Carve out each room.
    for x, y, width, height in rooms:
        for row in range(y, y + height):
            for col in range(x, x + width):
                grid[row][col] = FLOOR

    centers = [room_center(room) for room in rooms]

    # Connect every room to the next using L-shaped corridors.
    for index in range(len(centers) - 1):
        x1, y1 = centers[index]
        x2, y2 = centers[index + 1]

        if random.choice([True, False]):
            for x in range(min(x1, x2), max(x1, x2) + 1):
                grid[y1][x] = FLOOR

            for y in range(min(y1, y2), max(y1, y2) + 1):
                grid[y][x2] = FLOOR
        else:
            for y in range(min(y1, y2), max(y1, y2) + 1):
                grid[y][x1] = FLOOR

            for x in range(min(x1, x2), max(x1, x2) + 1):
                grid[y2][x] = FLOOR

    # First room = player start.
    # Second-last room = key.
    # Last room = treasure.
    start_position = centers[0]
    key_position = centers[-2]
    chest_position = centers[-1]

    # The guard starts beside the treasure, not on top of it.
    chest_room = rooms[-1]
    cx, cy, cw, ch = chest_room

    guard_start = None

    for row in range(cy + 1, cy + ch - 1):
        for col in range(cx + 1, cx + cw - 1):
            if (col, row) != chest_position:
                guard_start = (col, row)
                break

        if guard_start is not None:
            break

    if guard_start is None:
        guard_start = chest_position

    # Build trap candidates from walkable tiles outside the
    # start, key and treasure rooms.
    protected_room_indexes = {0, len(rooms) - 2, len(rooms) - 1}
    candidates = []

    for index, room in enumerate(rooms):
        if index in protected_room_indexes:
            continue

        x, y, width, height = room

        for row in range(y, y + height):
            for col in range(x, x + width):
                if grid[row][col] != FLOOR:
                    continue

                if (col, row) in (
                    start_position,
                    key_position,
                    chest_position,
                    guard_start,
                ):
                    continue

                candidates.append((col, row))

    # Add safe corridor tiles as extra trap positions if needed.
    if len(candidates) < NUM_TRAPS:
        for row in range(1, ROWS - 1):
            for col in range(1, COLS - 1):
                position = (col, row)

                if grid[row][col] != FLOOR:
                    continue

                if position in (
                    start_position,
                    key_position,
                    chest_position,
                    guard_start,
                ):
                    continue

                # Keep traps away from the immediate starting area.
                if abs(col - start_position[0]) <= 1 and (
                    abs(row - start_position[1]) <= 1
                ):
                    continue

                if position not in candidates:
                    candidates.append(position)

    random.shuffle(candidates)

    # Place as many traps as possible, up to NUM_TRAPS.
    for col, row in candidates[:NUM_TRAPS]:
        grid[row][col] = TRAP

    return grid, start_position, key_position, chest_position, guard_start


# ============================================================
# 3. PATHFINDING FOR THE GUARD
# ============================================================

def find_path(grid, start, target):
    """Use breadth-first search to find a shortest walkable path."""

    if start == target:
        return []

    queue = deque([(start, [])])
    visited = {start}

    directions = [
        (0, -1),
        (0, 1),
        (-1, 0),
        (1, 0),
    ]

    while queue:
        (x, y), path = queue.popleft()

        for dx, dy in directions:
            nx = x + dx
            ny = y + dy

            if not (0 <= nx < COLS and 0 <= ny < ROWS):
                continue

            if grid[ny][nx] == WALL:
                continue

            if (nx, ny) in visited:
                continue

            new_path = path + [(nx, ny)]

            if (nx, ny) == target:
                return new_path

            visited.add((nx, ny))
            queue.append(((nx, ny), new_path))

    return None


def distance_between(grid, start, target):
    """Return shortest path distance, or a large value if unreachable."""

    path = find_path(grid, start, target)

    if path is None:
        return 999

    return len(path)


# ============================================================
# 4. PLAYER
# ============================================================

class Player:
    def __init__(self, position):
        self.x, self.y = position
        self.has_key = False
        self.move_timer = 0

    @property
    def position(self):
        return (self.x, self.y)

    def update(self, dt, grid):
        self.move_timer -= dt

        if self.move_timer > 0:
            return

        keys = pygame.key.get_pressed()

        dx, dy = 0, 0

        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx = -1
        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx = 1
        elif keys[pygame.K_UP] or keys[pygame.K_w]:
            dy = -1
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            dy = 1

        if dx == 0 and dy == 0:
            return

        nx = self.x + dx
        ny = self.y + dy

        if (
            0 <= nx < COLS
            and 0 <= ny < ROWS
            and grid[ny][nx] != WALL
        ):
            self.x = nx
            self.y = ny
            self.move_timer = PLAYER_MOVE_DELAY


# ============================================================
# 5. GUARD
# ============================================================

class Guard:
    def __init__(self, position, patrol_room):
        self.x, self.y = position
        self.start_position = position
        self.patrol_room = patrol_room
        self.move_timer = 0
        self.chasing = False
        self.target = position

    @property
    def position(self):
        return (self.x, self.y)

    def reset(self):
        self.x, self.y = self.start_position
        self.move_timer = 0
        self.chasing = False
        self.target = self.start_position

    def choose_patrol_target(self, grid):
        """Choose a random walkable position near the treasure."""

        x, y, width, height = self.patrol_room
        options = []

        for row in range(y, y + height):
            for col in range(x, x + width):
                if grid[row][col] != WALL:
                    options.append((col, row))

        if options:
            self.target = random.choice(options)

    def update(self, dt, grid, player):
        self.move_timer -= dt

        if self.move_timer > 0:
            return

        player_distance = distance_between(
            grid, self.position, player.position
        )

        # CHASE: detect and follow the player within range.
        if player_distance <= GUARD_DETECTION_RANGE:
            self.chasing = True
            self.target = player.position

        else:
            # If the player escapes, resume guarding the treasure.
            if self.chasing:
                self.chasing = False
                self.choose_patrol_target(grid)

            # Continue patrolling if the guard has reached its target.
            if self.position == self.target:
                self.choose_patrol_target(grid)

        path = find_path(grid, self.position, self.target)

        if path:
            self.x, self.y = path[0]

        self.move_timer = GUARD_MOVE_DELAY


# ============================================================
# 6. GAME ENGINE
# ============================================================

class GameEngine:
    def __init__(self):
        self.reset()

    def reset(self):
        (
            self.grid,
            self.start_position,
            self.key_position,
            self.chest_position,
            self.guard_start,
        ) = generate_world()

        self.player = Player(self.start_position)

        chest_room = None

        for room in self._get_rooms():
            x, y, width, height = room

            if (
                x <= self.chest_position[0] < x + width
                and y <= self.chest_position[1] < y + height
            ):
                chest_room = room
                break

        if chest_room is None:
            chest_room = (1, 1, 5, 4)

        self.guard = Guard(self.guard_start, chest_room)

        self.won = False
        self.status_message = "Find the key and reach the treasure!"
        self.status_timer = 4.0

    def _get_rooms(self):
        """Find the room containing the treasure for guard patrol."""

        # The generator stores the final room for the guard.
        # The guard is given a small walkable area around the chest.
        cx, cy = self.chest_position

        for y in range(max(0, cy - 3), min(ROWS, cy + 4)):
            for x in range(max(0, cx - 3), min(COLS, cx + 4)):
                if self.grid[y][x] == FLOOR:
                    pass

        # A compact patrol area around the treasure.
        return [(max(0, cx - 2), max(0, cy - 2), 5, 5)]

    def set_message(self, message, duration=2.5):
        self.status_message = message
        self.status_timer = duration

    def return_to_start(self, message):
        """Reset the player after touching a trap or the guard."""

        self.player.x, self.player.y = self.start_position

        if self.player.has_key:
            self.player.has_key = False
            self.set_message(message + " You dropped the key!")
        else:
            self.set_message(message)

        self.guard.reset()

    def update(self, dt):
        if self.won:
            return

        self.player.update(dt, self.grid)

        position = self.player.position
        x, y = position

        # Trap collision.
        if self.grid[y][x] == TRAP:
            self.return_to_start("You stepped on a trap!")

        position = self.player.position

        # Pick up the key.
        if position == self.key_position and not self.player.has_key:
            self.player.has_key = True
            self.key_position = None
            self.set_message("You collected the key! Find the treasure.")

        # Guard movement and detection.
        self.guard.update(dt, self.grid, self.player)

        # Catch the player when the guard reaches the same or
        # an adjacent tile.
        gx, gy = self.guard.position
        px, py = self.player.position

        # The guard catches the player only when they occupy
        # exactly the same tile.
        if (gx, gy) == (px, py):
            self.return_to_start("The guard caught you!")

        # Unlock the treasure chest.
        if self.player.position == self.chest_position:
            if self.player.has_key:
                self.won = True
                self.set_message("You unlocked the treasure!", 999)
            else:
                self.set_message("The chest is locked. Find the key!")

        self.status_timer -= dt


# ============================================================
# 7. DRAWING FUNCTIONS
# ============================================================

def draw_text(text, font, color, x, y):
    image = font.render(text, True, color)
    screen.blit(image, (x, y))


def draw_world(game):
    for row in range(ROWS):
        for col in range(COLS):
            rect = pygame.Rect(
                MARGIN + col * TILE,
                MARGIN + HUD_HEIGHT + row * TILE,
                TILE,
                TILE,
            )

            tile = game.grid[row][col]

            if tile == WALL:
                pygame.draw.rect(screen, WALL_COLOR, rect)
            elif tile == TRAP:
                pygame.draw.rect(screen, FLOOR_COLOR, rect)
                pygame.draw.rect(screen, DARK_RED, rect, 2)

                # Spikes.
                center_x, center_y = rect.center
                points = [
                    (center_x, center_y - 10),
                    (center_x + 8, center_y + 7),
                    (center_x - 8, center_y + 7),
                ]
                pygame.draw.polygon(screen, RED, points)

            else:
                if (row + col) % 2 == 0:
                    color = FLOOR_COLOR
                else:
                    color = FLOOR_ALT

                pygame.draw.rect(screen, color, rect)

            pygame.draw.rect(screen, GRID_COLOR, rect, 1)

    # Draw key.
    if game.key_position is not None:
        kx, ky = game.key_position
        px = MARGIN + kx * TILE
        py = MARGIN + HUD_HEIGHT + ky * TILE

        pygame.draw.circle(
            screen, GOLD, (px + 15, py + 14), 7, 3
        )
        pygame.draw.line(
            screen, GOLD, (px + 21, py + 14), (px + 27, py + 14), 3
        )
        pygame.draw.line(
            screen, GOLD, (px + 25, py + 14), (px + 25, py + 19), 3
        )

    # Draw treasure chest.
    cx, cy = game.chest_position
    chest_rect = pygame.Rect(
        MARGIN + cx * TILE + 4,
        MARGIN + HUD_HEIGHT + cy * TILE + 7,
        TILE - 8,
        TILE - 12,
    )

    pygame.draw.rect(screen, (125, 65, 30), chest_rect, border_radius=4)
    pygame.draw.rect(
        screen, GOLD,
        (chest_rect.x, chest_rect.y + 5, chest_rect.width, 5),
    )
    pygame.draw.circle(screen, GOLD, chest_rect.center, 3)

    # Draw player.
    px = MARGIN + game.player.x * TILE + TILE // 2
    py = MARGIN + HUD_HEIGHT + game.player.y * TILE + TILE // 2

    pygame.draw.circle(screen, BLUE, (px, py), 12)
    pygame.draw.circle(screen, WHITE, (px - 4, py - 2), 2)
    pygame.draw.circle(screen, WHITE, (px + 4, py - 2), 2)

    # Draw guard and indicate whether it is chasing.
    gx = MARGIN + game.guard.x * TILE + TILE // 2
    gy = MARGIN + HUD_HEIGHT + game.guard.y * TILE + TILE // 2

    guard_color = RED if game.guard.chasing else PURPLE

    pygame.draw.circle(screen, guard_color, (gx, gy), 12)
    pygame.draw.circle(screen, WHITE, (gx - 4, gy - 2), 2)
    pygame.draw.circle(screen, WHITE, (gx + 4, gy - 2), 2)

    # Alert symbol when the guard is chasing.
    if game.guard.chasing:
        pygame.draw.circle(screen, RED, (gx, gy), 15, 2)
        draw_text("!", FONT, WHITE, gx - 4, gy - 29)


def draw_minimap(game, x, y):
    scale = 6

    draw_text("MINIMAP", FONT, WHITE, x, y - 22)

    pygame.draw.rect(
        screen,
        BLACK,
        (x - 3, y - 3, COLS * scale + 6, ROWS * scale + 6),
    )

    for row in range(ROWS):
        for col in range(COLS):
            tile = game.grid[row][col]

            if tile == WALL:
                color = WALL_COLOR
            elif tile == TRAP:
                color = RED
            else:
                color = FLOOR_COLOR

            pygame.draw.rect(
                screen,
                color,
                (x + col * scale, y + row * scale, scale, scale),
            )

    # Key marker.
    if game.key_position is not None:
        kx, ky = game.key_position
        pygame.draw.rect(
            screen, GOLD,
            (x + kx * scale, y + ky * scale, scale, scale),
        )

    # Treasure marker.
    cx, cy = game.chest_position
    pygame.draw.rect(
        screen, GOLD,
        (x + cx * scale, y + cy * scale, scale, scale),
    )

    # Guard marker.
    gx, gy = game.guard.position
    pygame.draw.rect(
        screen, PURPLE,
        (x + gx * scale, y + gy * scale, scale, scale),
    )

    # Player marker.
    px, py = game.player.position
    pygame.draw.rect(
        screen, BLUE,
        (x + px * scale, y + py * scale, scale, scale),
    )


def draw_sidebar(game):
    x = MARGIN * 2 + WORLD_WIDTH
    y = MARGIN + HUD_HEIGHT

    pygame.draw.rect(
        screen,
        PANEL_COLOR,
        (x, y, SIDEBAR_WIDTH, WORLD_HEIGHT),
        border_radius=10,
    )

    draw_text("INVENTORY", FONT, WHITE, x + 15, y + 15)

    slot = pygame.Rect(x + 15, y + 45, 48, 48)
    pygame.draw.rect(screen, BLACK, slot, border_radius=5)
    pygame.draw.rect(screen, WHITE, slot, 2, border_radius=5)

    if game.player.has_key:
        pygame.draw.circle(
            screen, GOLD, (slot.x + 17, slot.y + 19), 7, 3
        )
        pygame.draw.line(
            screen, GOLD,
            (slot.x + 23, slot.y + 19),
            (slot.x + 36, slot.y + 19),
            3,
        )
        draw_text("Key collected", SMALL_FONT, GREEN, x + 72, y + 60)
    else:
        draw_text("No key yet", SMALL_FONT, WHITE, x + 72, y + 60)

    draw_minimap(game, x + 15, y + 145)

    draw_text("CONTROLS", FONT, WHITE, x + 15, y + 280)
    draw_text("Arrow keys / WASD", SMALL_FONT, WHITE, x + 15, y + 310)
    draw_text("Move the player", SMALL_FONT, WHITE, x + 15, y + 330)
    draw_text("R - New random map", SMALL_FONT, WHITE, x + 15, y + 360)
    draw_text("ESC - Quit", SMALL_FONT, WHITE, x + 15, y + 380)

    draw_text("TRAPS", FONT, RED, x + 15, y + 425)
    draw_text("Avoid the red spikes!", SMALL_FONT, WHITE, x + 15, y + 450)

    draw_text(
        "GUARD: CHASING" if game.guard.chasing else "GUARD: PATROLLING",
        SMALL_FONT,
        RED if game.guard.chasing else PURPLE,
        x + 15,
        y + 485,
    )


def draw_game(game):
    screen.fill(BLACK)

    draw_text(
        "TREASURE HUNT",
        BIG_FONT,
        GOLD,
        MARGIN,
        12,
    )

    draw_text(
        "Collect the key. Avoid traps. Escape the guard!",
        SMALL_FONT,
        WHITE,
        MARGIN + 270,
        30,
    )

    draw_world(game)
    draw_sidebar(game)

    if game.status_timer > 0:
        message_color = GOLD if game.won else WHITE

        pygame.draw.rect(
            screen,
            PANEL_COLOR,
            (MARGIN, SCREEN_HEIGHT - 28, SCREEN_WIDTH - 2 * MARGIN, 24),
            border_radius=5,
        )

        message = FONT.render(
            game.status_message, True, message_color
        )
        screen.blit(message, (MARGIN + 8, SCREEN_HEIGHT - 27))

    if game.won:
        overlay = pygame.Surface(
            (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 190))
        screen.blit(overlay, (0, 0))

        title = BIG_FONT.render("YOU FOUND THE TREASURE!", True, GOLD)
        subtitle = FONT.render(
            "Congratulations! Press R to play a new map.",
            True,
            WHITE,
        )

        screen.blit(
            title,
            title.get_rect(
                center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 25)
            ),
        )
        screen.blit(
            subtitle,
            subtitle.get_rect(
                center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 25)
            ),
        )

    pygame.display.flip()


# ============================================================
# 8. MAIN GAME LOOP
# ============================================================

def main():
    game = GameEngine()
    running = True

    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                elif event.key == pygame.K_r:
                    game.reset()

        game.update(dt)
        draw_game(game)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

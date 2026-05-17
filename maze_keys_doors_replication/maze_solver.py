import collections

maze = [
    [0, 'a', 0, 1, 0, 1, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0],
    [1, 1, 'A', 0, 0, 0, 0, 0],
    [0, 1, 0, 1, 1, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0],
]

start = (0, 0)
end = (7, 7)
rows = len(maze)
cols = len(maze[0])

def solve_maze(maze, start, end):
    q = collections.deque([(start[0], start[1], frozenset(), [start])])
    visited = set([(start[0], start[1], frozenset())])

    while q:
        r, c, keys_collected, path = q.popleft()

        if (r, c) == end:
            return path

        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]: # Up, Down, Left, Right
            nr, nc = r + dr, c + dc

            if not (0 <= nr < rows and 0 <= nc < cols):
                continue

            cell = maze[nr][nc]

            if cell == 1: # Wall
                continue

            new_keys_collected = set(keys_collected)
            can_pass = True

            if isinstance(cell, str) and cell.islower(): # Key
                new_keys_collected.add(cell)

            if isinstance(cell, str) and cell.isupper(): # Door
                if cell.lower() not in keys_collected:
                    can_pass = False
            
            if not can_pass:
                continue

            new_keys_collected_frozen = frozenset(new_keys_collected)

            if (nr, nc, new_keys_collected_frozen) not in visited:
                visited.add((nr, nc, new_keys_collected_frozen))
                q.append((nr, nc, new_keys_collected_frozen, path + [(nr, nc)]))
    return None

path = solve_maze(maze, start, end)
if path:
    print(f'FINAL PATH: {path}')
else:
    print('No path found.')

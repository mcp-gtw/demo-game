# Authoring maps in Tiled

The world is a real [Tiled](https://www.mapeditor.org) map:
`src/app/web/assets/map/island.tmj`. Open it directly in the Tiled editor, edit, save, and the game
loads it — no export step. `maps/loader.py::load_tiled` reads it and validates it, raising a clear
`MapError` (not a crash) when a map breaks a rule below.

## The one map the game loads

`default_map()` loads `island.tmj`. To ship a different map, edit that file or replace it (same path).

## Map settings (File ▸ Map Properties)

- **Orientation** orthogonal, **Tile size** 64×64, **fixed size** (an *infinite* map is rejected).
- One **embedded** tileset built from `terrain/tileset.png` (an external `.tsx` is rejected). Its image
  path in the `.tmj` is `../terrain/tileset.png` so Tiled resolves it; the game ignores that path and
  serves the tileset from the web root, so you never need to fix it.
- A custom map property **`foodCap`** (int) — how many food pickups the map keeps topped up. Stored as
  a Tiled map property, so it survives a save.

## Layers (names matter — they are matched exactly)

| Layer | Type | Holds |
| --- | --- | --- |
| `ground` | Tile layer | The terrain. `gid 0` (empty) is **sea** and blocks movement. |
| `objects` | Object layer | Static art and interactables (see below). |
| `spawns` | Object layer | NPC spawn areas. |

All objects must be **rectangle** objects (drawn with the Rectangle tool), **not** tile/stamp objects —
a tile object anchors its `y` at the bottom and would land one tile too low. Positions and sizes are in
pixels; the loader divides by 64, so keep objects snapped to the 64px grid. An object's **Name** (not
its Class) selects what it is.

### `objects` layer — Name ▸ required properties

| Name | Behaviour | Required property |
| --- | --- | --- |
| `building` | solid; the rectangle is its width×height footprint, but collision blocks only its bottom rows (capped at 2), so a taller building's back row stays walkable (pass behind) | `sprite` |
| `rock` | solid | `sprite` |
| `bush` | decoration, non-solid | `sprite` |
| `tree` | choppable | — |
| `item` | collectible (step on it to pick up) | `item` |

- `sprite` (string) — one of: `castle`, `house`, `tower`, `rock1`, `rock2`, `rock3`, `rock4`, `bush1`,
  `bush2`, `bush3`, `bush4`.
- `item` (string) — one of the catalog ids: `heart`, `boots`, `spyglass`, `gauntlet`.

An unknown Name or a missing property fails with a `MapError` naming the offending object.

### `spawns` layer — Name = the NPC id

Each object's **Name** is the enemy id, with properties `range` (int) and `max` (int): NPCs spawn
randomly within `range` cells of the object, up to `max` alive at once. Valid ids: `enemy_warrior`,
`enemy_archer`, `enemy_lancer`, `enemy_monk`, `sheep_shy`, `sheep_flighty`, `sheep_calm`.

## What the loader rejects (each with a friendly `MapError`)

- an infinite map, or a missing/wrong-sized `ground` layer;
- non-square tiles (`tilewidth` must equal `tileheight` — the engine works in square cells);
- no tileset, an external `.tsx` tileset, or a tileset missing `columns`/`tilecount`/`firstgid`;
- an `objects` or `spawns` layer that is not an object group;
- an object whose Name is not one of the kinds above, missing a required property, an `item` object
  whose `item` is not a catalog id, carrying a non-numeric `foodCap`/spawn `range`/`max`/coordinate, or
  placed outside the map bounds.

Everything else (solid footprints, the blocked-cell grid, spawn areas) is derived by the loader — you
only place and name objects in Tiled.

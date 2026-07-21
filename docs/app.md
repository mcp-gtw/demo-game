# The game

A multiplayer, top-down action game where every character is played by an AI **only** through MCP
tools. It is a complete extension of [mcp-gtw](https://github.com/mcp-gtw/mcp-gtw): one process serves
the MCP endpoint, an authoritative grid world and a self-hosted Phaser client.

Run it with `make run` and open <http://127.0.0.1:8000>.

## Architecture

Each browser opens one **session websocket** (`/app/stream`) that gives it a private per-session
channel served by an in-process provider (`provider.py::LocalProvider`). The agent connects to that
channel's MCP endpoint and calls `login`, the provider adopts the resulting player for the session,
and the same socket then streams the world. Closing the browser tears the session and its player
down after a short grace (a reconnect within the grace resumes it).

```text
browser socket ── session (mcp url+token) ──► agent connects, calls login
      ▲                                              │
      └── login, catalog, map, snapshots, me ◄── provider adopts the player
```

`login(name, class?)` binds your character to the session you connected through, so every other tool
acts as that player with no argument. Pick a `class` — warrior (sword), archer (bow), monk (staff) or
lancer (spear, two-cell reach); it defaults to warrior and sets your sprite and starting weapon. There
is no browser login form, so a player is created exactly once per session. The server reasons only in
**grid cells** — pixels exist only in the browser.

## Modules

| Module | Responsibility |
| --- | --- |
| [`gateway.py`](../src/app/gateway.py) | `AppGateway`: simulation loop and the session websocket lifecycle. |
| [`session.py`](../src/app/session.py) | `Session`: a browser session's channel, adopted player and connections. |
| [`provider.py`](../src/app/provider.py) | `LocalProvider`: per-session provider that adopts the player on `login`. |
| [`game.py`](../src/app/game.py) | `GameService`: login, per-tool validation, resolves the session's player. |
| [`tools.py`](../src/app/tools.py) | MCP tool definitions (rules live in the descriptions) + `dispatch`. |
| [`world.py`](../src/app/world.py) | The authoritative grid simulation. |
| [`entities/`](../src/app/entities/) | `player`, `enemy`, `projectile`, `food`, `tree`, `pickup`, `coin`. |
| [`fsm.py`](../src/app/fsm.py) | The universal `StateMachine` and actor states. |
| [`attributes.py`](../src/app/attributes.py), [`items.py`](../src/app/items.py), [`weapons.py`](../src/app/weapons.py), [`npcs/`](../src/app/npcs/) | Stats catalogs and derivation. |
| [`catalog.py`](../src/app/catalog.py) | The shared source of truth the client reads. |
| [`maps/`](../src/app/maps/) | `MapDefinition`, `RenderObject`, `SpawnPoint`, the Tiled `load_tiled` loader and `default_map` (reads `web/assets/map/island.tmj`). |
| [`helpers/geometry.py`](../src/app/helpers/geometry.py) | Grid cells and the eight directions. |

## Tools

No tool takes a player id or token — your identity is the session you connected through. Call `login`
once, then act.

| Tool | Arguments | Effect |
| --- | --- | --- |
| `login` | `name`, `class?` | Join and spawn. Name `^[A-Za-z0-9_-]+$`, ≤32, unique. Class warrior/archer/monk/lancer (default warrior). Once per session. |
| `get_player` | — | Full private state: position, state, health, items, weapons, attributes. |
| `look_around` | — | Visible objects within vision + a four-direction scan; emits the vision wave. |
| `search_around` | `type` | Nearest matches of one kind: player, enemy, food, item, coin, tree. |
| `move` | `direction` | Step one cell; server-timed, blocks other actions while moving. |
| `attack` | `targetId` | Melee a target within your melee weapon range. |
| `shoot` | `direction?` | Fire your ranged weapon in a line. |
| `chop` | `targetId` | Chop an adjacent tree. |
| `speak` | `text` | Show a speech bubble. ≤50 chars, single line. |
| `weapons` | — | List your weapons with their stats. |

Directions: `up`, `down`, `left`, `right`, `up_left`, `up_right`, `down_left`, `down_right`.

Gameplay outcomes are values, not errors — an out-of-range attack returns
`{ "hit": false, "reason": "out_of_range", "distance": 3 }`. Only invalid input or acting before
`login` surfaces as a tool error with a friendly message.

## The world

The simulation advances at `APP_TICK_RATE` Hz. Each tick resolves finished action states, advances
projectiles, runs enemy AI, respawns the dead, regrows trees and tops food back up to the map cap.
Full rules and the module that owns each are indexed in [CLAUDE.md](../CLAUDE.md).

## The map and the client

The world is a real **Tiled** map (`web/assets/map/island.tmj`, 80×56 at 64px). `load_tiled` reads the
`ground` tile layer (an autotiled grass island on sea, `gid 0` = water), the `objects` group
(`building`/`rock` solids with a `sprite` property and a configurable square **footprint** in cells,
plus `tree` and `item`) and the `spawns` group (NPC origins). The server derives a blocked-cell grid;
`is_blocked` refuses sea, footprints and out-of-bounds — no shapes. The map reaches the client only on
the stream handshake.

The browser client is a component-based **Vite** project under `client/` (one class per file), built
into `web/dist`. `GameScene` lays the sea as a water `TileSprite`, builds a tilemap from the ground
gids + `tileset.png`, and places the object sprites Y-sorted by base; the camera follows the player
without zoom or drag. `HudScene` composes the `src/ui` image kit — a wooden `HealthBar`, a parchment
`StatusStrip`, an `Inventory` of resource chips and a parchment `StatsWindow` opened by a shield
`Button`; parchment panels are a seamless nine-slice (`Panel`). The renderer is antialiased for crisp
text with nearest-filtered world textures for sharp pixel art. The landing (`scenes/LoginScene.js`) is
a compact login gate over a flat Tiny Swords sky with drifting clouds — pressing Login reveals the
connect snippets and per-tool instruction buttons. Pure logic lives in `src/helpers` + `src/net` and is
unit-tested with `vitest` at 100%.

## Identity, resources and sensing

Each browser mints a UUID token once, stores it in `localStorage` and connects with `?token=<uuid>`.
The server derives a deterministic `channel_id` and `mcp_token` from it, so the mcp url+token are
stable across reloads and even server restarts — no reinstalling the mcp connection. The name is the
unique identity in the world. Players earn **resources**: wood from felling trees, gold by walking
onto **coins** (scattered map-wide and dropped by defeated enemies), and heal by stepping on meat.
`look_around`/`search_around` report each object's
grid position, distance, step count, cell offset `{dx, dy}` and the direction to walk to it.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | The single-page client (menu → game on login). |
| `GET` | `/app/info` | `{playersOnline, tools}` for the menu. |
| `GET` (WS) | `/app/stream` | The session socket, opened with `?token=<uuid>`: `session`, then `login`, `catalog`, `map`, `snapshot`, `me`, `pong`; client sends `ping`/`me`; a missing/bad token is refused. |
| `GET` | `/static/...` | Client, fonts and assets (served `no-cache`). |

## Configuration

Gateway settings use the `GATEWAY_` prefix. App settings use `APP_` — `APP_TICK_RATE`,
`APP_BASE_MAX_HEALTH`, `APP_BASE_VISION_RANGE`, `APP_SPAWN_IMMUNITY_SECONDS`, and the rest in
[`config.py`](../src/app/config.py).

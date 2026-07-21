# CLAUDE.md

Guidance for working in this repository.

## What this is

`mcp-gateway-demo` is a multiplayer, top-down action game where every agent is controlled **only**
through [MCP](https://modelcontextprotocol.io) tools. It is the reference extension of
[`mcp-gtw`](https://github.com/mcp-gtw/mcp-gtw): one `AppGateway(Gateway)` subclass adds an
authoritative grid world, its HTTP/WebSocket surface and a self-hosted Phaser client.

The internal package name is intentionally generic (`app`) so the demo is easy to port or reuse.

It depends on `mcp-gtw`. Locally `[tool.uv.sources]` points at the sibling `../mcp-server` checkout.
In Docker/PyPI it resolves from the index.

## Architecture (per-browser session, MCP-only login, camera follows your player)

The gateway is a relay. Each browser opens **one session websocket** (`/app/stream`) that gives it a
**private per-session channel** with an in-process provider (`provider.py`). The agent connects to
that channel's MCP endpoint and calls `login`, the provider **adopts** the resulting player for the
session, and the same websocket then streams the world. Everything after login is via MCP.

There is **no browser login form** — `login` is an MCP tool, so a player is created exactly once per
session, and there is no way to end up with two players. Positions are always **grid cells (1, 2, 3…)**
on the server (pixels exist only in the browser, `tile_size` is a render hint).

Flow: browser opens the socket with its stored token → server derives the stable channel and sends the
MCP url + token → agent connects and calls `login` → provider adopts the player, socket sends `login` +
catalog + map + snapshots → the page drops into the game following **only** that player (fixed zoom, no
picker, no zoom, no drag). Closing the browser tears the session down after a short grace, removing the
player (a reload within the grace keeps the same character; the token stays valid regardless). The
stats panel is fed by `{type: "me"}` over the same socket.

## Layout (`src/app/`)

- `gateway.py` — `AppGateway(Gateway)`: ticks and broadcasts **every room** in `serve`, drives the session
  websocket lifecycle (create/resume, wait-for-login, stream, teardown) and adds `/app/info`,
  `/app/stream`, `/static` and home. `RevalidatingStaticFiles` serves the client `no-cache`.
- `room.py` — `Room`: one isolated game world with its own `World`, `GameService` and `StreamHub`.
- `room_manager.py` — `RoomManager`: holds every room, guarantees a default room (`"world"`) from
  startup and can `create` more; the architecture is multi-room even while one room is in use.
- `session.py` — `Session`: one browser session (its channel, the `room` it plays in, its adopted
  player and live connections).
- `provider.py` — `LocalProvider`: the per-session provider; every tool runs against the session's
  room `GameService`, adopts the player on `login`, rejects a second login, dispatches the rest.
- `game.py` — `GameService`: login, per-tool validation, resolves the session's player by id.
- `tools.py` — MCP tool definitions (AI-facing descriptions carry the rules) + `dispatch`.
- `world.py` — the authoritative grid simulation.
- `entities/` — one file per object: `player.py`, `enemy.py`, `projectile.py`, `food.py`, `tree.py`,
  `pickup.py`, `coin.py`.
- `fsm.py` — the universal `StateMachine` and the actor states/transitions.
- `attributes.py`, `items.py`, `weapons.py` — stats catalogs and derivation. `classes.py` — `ClassSpec`
  and `CLASSES` (warrior/archer/monk/lancer): the sprite and starting weapons each playable class spawns
  with, resolved by `get_class` at login. `colors.py` — `PLAYER_COLORS` (blue/yellow/purple/black) and
  `get_color`: the faction skin a player picks at login (enemies always render red).
- `objects.py` — `ObjectKind`: the shared map-object catalog (`solid`/`choppable`/`collectible`) the map
  loader classifies against and the client reads via the catalog, so a new object type is one entry.
- `npcs/` — the NPC catalog, one class per file: `behavior.py` (`Behavior` = aggressive/skittish/wander),
  `loot_drop.py` (`LootDrop`), `enemy_spec.py` (`EnemySpec`, every stat an NPC is born with — profile,
  ranged, flee params, wander chance, per-NPC `respawn_seconds`, `attack_duration`, loot table) and `registry.py`
  (`ENEMIES` + `get_enemy_spec`). Adding a profile is one `EnemySpec` entry, no engine change.
- `catalog.py` — `build_catalog`: the single shared source of truth (weapons, items, enemies, objects,
  directions, states, search types, limits) the client reads instead of re-declaring game data.
- `maps/` — one class per file: `spawn_point.py` (`SpawnPoint`), `render_object.py` (`RenderObject`),
  `map_definition.py` (`MapDefinition`) and `loader.py` (`load_tiled` + `default_map`, reading
  `web/assets/map/island.tmj`). `MapDefinition` owns the ground gid grid, the render objects, the
  blocked-cell set and `tile_size`.
- `helpers/geometry.py` — grid `Cell` and the eight directions.
- `config.py` — `AppSettings` (env prefix `APP_`). `stream.py` — `StreamHub`: fans a snapshot out to
  every subscriber **concurrently and time-bounded** (`stream_send_timeout_seconds`), dropping any
  consumer whose send stalls, so one blocked socket can never freeze the simulation for everyone.
  `errors.py`.
- `web/` — the served client. `assets/{units,terrain,resources,items,ui,buildings,decor,map,audio}`
  (curated Tiny Swords art, the Tiled map and the background track), `fonts/roboto.woff2`, and `dist/` — the **built** bundle
  (`vite`, gitignored). The server serves `dist/index.html` at `/`, the whole `web/` tree under
  `/static` (so the bundle lives at `/static/dist` and the art stays at `/static/assets`).

## Client (`client/`, built with Vite)

The browser client is a component-based Vite project bundled into `web/dist`. It only reads server
data and draws — it never re-declares game rules or catalogs. **Naming convention** (the JS standard):
a file that exports a **class** is `PascalCase` (`GameSocket.js`, `Panel.js`, `EntityView.js`); a file
that exports **functions or constants** is lowercase (`helpers/format.js`, `constants.js`, `main.js`).

  **Everything the player sees is Phaser** — there is no DOM/CSS interface. `index.html` holds only a
  `#game` div and `style.css` only makes the app fill the browser (fullscreen, no scroll, no text
  selection, no margins) plus the `@font-face` for the crisp Roboto text. The landing, the connect
  windows and the HUD are all Phaser scenes.

- `src/main.js` — boot: creates the store and the `GameSocket`, then the Phaser `Game` with `BootScene`
  active and `LoginScene`/`GameScene`/`HudScene` registered but stopped. On MCP login
  (`store.phase = "game"`, once catalog + map arrived) it starts game + HUD and stops the login. If a
  reconnect **after the grace** adopts a fresh player (a new id while already in game), `onLogin`
  updates `store.playerId` and restarts the game + HUD scenes so the camera and HUD re-bind to the new
  character instead of following a stale one.
- `src/scenes/BootScene.js` — shows the `LoadingWindow` and loads **every static asset once** (all
  texture manifests, the per-unit spritesheets from the `UNITS` catalog — one set per faction colour for
  the coloured classes, via `unitBases` — the tree/foam sheets and the music) so no scene reloads a
  shared key, then starts `LoginScene`. Only the tileset and item icons
  stay dynamic in `GameScene` (their paths arrive with the map and catalog). Scenes that listen for
  `resize` remove the listener on `shutdown`, so a stopped scene never lays out a torn-down nine-slice.
- `src/ui/LoadingWindow.js` — the loading screen drawn entirely with graphics + text (no preloaded
  texture): a parchment panel, a `Loading… N%` label and a progress bar fed by the loader's `progress`
  event. It removes itself when BootScene shuts down.
- `src/constants.js` — shared constants: ui theme (colours, ink, panel border, text dpr), the texture
  manifests (`MENU_TEXTURES`, `WORLD_TEXTURES`, `OBJECT_TEXTURES`, `HUD_TEXTURES`), the `UNITS` catalog
  (one entry per unit sprite — `warrior`, `archer`, `monk`, `lancer`, `sheep`; a player renders as its
  class sprite, an enemy as its `EnemySpec.sprite`) carrying the spritesheet frame size, on-screen scale,
  the vertical `originY` (so the unit stands on its cell), and the idle/run/attack frame rates — the
  sheep animates slower than the humanoids and has no attack. The four humanoid classes are `colored`,
  shipping one spritesheet set per faction under `assets/units/<unit>/<color>/`; `UNIT_COLORS`
  (blue/yellow/purple/black/red) and `unitBases` build the per-colour texture keys, so a player draws in
  its chosen colour and an enemy in `ENEMY_COLOR` (red). `TREES` lists the four choppable-tree
  variants (frame size, scale, origin) picked per tree by its cell. Plus the resource icon map. A
  component's own private layout numbers stay in the component.
- `src/helpers/` — pure functions (no Phaser/canvas): `mcp` (connect snippets), `format`, `clipboard`,
  `store`, `world` (snapshot index), `geometry`, `health`, `interpolate`, plus `animations` (the one
  Phaser-glue helper, excluded from the coverage gate since it only wires Phaser animation configs).
- `src/net/GameSocket.js` — the session socket (connect/resume, ping/latency, reconnect backoff).
- `src/ui/` — the self-sizing Phaser UI kit. Every component **grows to its content** (measure the
  label, then size the background) so text never clips. Built on Phaser's `NineSlice`: `Panel`
  (9-slice parchment), `HealthBar` (3-slice wooden bar), `Button` (icon square), `TextButton` (a
  parchment button sized to its label), `CopyButton` (a `TextButton` that copies to the clipboard and
  confirms — its confirm timer lives on the scene clock, so it is dropped on the button's `destroy`
  and the async copy bails if the button is already gone, so closing the window mid-copy never mutates
  a torn-down text), `Window` (a closable parchment window with a dimming backdrop, a title, an
  optional Copy button and a close button — sized to its content but capped to the viewport, wrapping
  the body with **advanced word wrap** so an unbreakable url or token breaks to fit instead of spilling,
  and when the body is longer than fits it shows one page of wrapped lines and scrolls with the mouse
  wheel, re-centring and re-fitting on resize; clicking the backdrop **outside** the panel closes it,
  clicking the panel does not), `Label`, `StatusStrip`, `Inventory`, `StatsWindow` (its two stat
  columns **scale down to fit** when a short viewport caps the panel, so the rows never spill). Each exposes a
  `.root` container so a scene can nest it under one DPR-scaled layer and lay out in logical
  coordinates. Every layout clamps its wrap width to a positive floor, so a text that re-wraps every
  frame (the landing status line) never gets a zero/negative width that corrupts its canvas.
  (The client targets **Phaser 4**, whose WebGL renderer dropped geometry `setMask`, so scrolling is
  done by paging wrapped lines rather than masking.)
- `src/scenes/` — `BootScene` (asset loader), `LoginScene` (the landing), `GameScene` (world, with the
  drifting `Clouds`), `HudScene` (the UI kit) and `GalleryScene` (a showcase). Render order in game:
  world → HUD.
- `src/scenes/GalleryScene.js` — a scrollable showcase reachable at **`/?gallery`** rendering one of
  each element stacked vertically (Label, TextButton, Button, HealthBar, Panel, the player idle/run/
  attack cycle, the sheep, a tree, the arrow projectile with trail and a particle burst), so every
  component and sprite can be eyeballed at a glance.
- `src/scenes/LoginScene.js` — the Phaser landing: the Tiny Swords sky background (`ui/login_bg.png`)
  cover-fit, drifting `Clouds`, and a parchment card (title, online count, status). Pressing **Login**
  (enabled once the session arrives) reveals three option buttons — Claude Code (CLI), MCP config, and
  Tools — each opening a `Window` explaining it with a Copy button where it helps. The whole card is
  **responsive**: it caps at 440 logical px but shrinks to the screen width, the text word-wraps and the
  buttons resize to fit, so it never clips on a narrow or portrait viewport.
- `src/game/EntityView.js` — one on-screen entity (sprite, name tag, health bar, speech bubble). It
  picks the per-faction texture (`#textureBase`: the player's colour, or red for enemies) and **walks
  actors smoothly** toward their cell over `moveMs`, snapping only on a respawn-sized jump. The name tag
  and speech bubble sit close above the sprite; a fresh collectible (loot, respawned pickup) **hops in**.
  A drop in `health` (or a tree's `hits`) triggers a single quick red fill-tint flash, and projectiles
  leave a short fading golden trail.
- `src/game/DamageNumbers.js` — floating combat numbers: each hit spawns the amount taken, rising and
  fading in a random direction so overlapping hits fan out.
- `src/game/DebugOverlay.js` — a togglable overlay (press **B**) drawing the Tiled cell grid, the
  blocked cells (sea + solid object footprints), the spawn areas and the player's current cell, to
  verify the cell system. It reads `map.objects[].solid` and `map.spawns` from the stream.
- `src/game/Clouds.js` — drifting clouds scattered at random over a bounds rectangle, reassigned a
  random height/size/speed on wrap. In game the bounds are the map plus `CLOUD_MARGIN_CELLS` in world
  space (a depth above the world but below the HUD scene); on the landing the bounds are the screen in a
  DPR layer under the card. `src/game/Music.js` — the looping background track (mute with **M**).
- `tests/` — `vitest` unit tests over `helpers` and `net` at 100% coverage (`vitest.config.js` scopes
  the coverage gate to those two directories). The Phaser view classes (scenes, UI kit, `EntityView`,
  `Clouds`) carry no automated tests: they are guarded by the type/build check (`vite build`) and
  verified manually with headless-Chromium smoke runs during development, not in CI.

## Game rules and where each one lives

Every rule is enforced on the server. This is the index so nothing is duplicated or lost:

- **Login + class + color** — the `login` MCP tool → `provider.py::LocalProvider._login` → `game.py::GameService.login`.
  Name must match `^[A-Za-z0-9_-]+$`, ≤ `name_max_length` (32), and be unique among live players, else
  a friendly `CommandError`. Login also takes an optional **`class`** (`classes.py::CLASSES`: warrior,
  archer, monk, lancer — defaults to `warrior`); `world.add_player` resolves it via `get_class` and the
  `ClassSpec` sets the player's `sprite` and starting `weapons` (warrior→sword, archer→bow, monk→staff,
  lancer→spear). It also takes an optional **`color`** (`colors.py::PLAYER_COLORS`: blue, yellow, purple,
  black — defaults to `blue`, resolved by `get_color`), the player's faction skin; enemies always render
  red. An unknown class or color is a friendly `CommandError`. Success spawns the player and the
  session adopts it. Each session may log in once (a second login is rejected). There is no logout tool —
  leaving is by disconnecting. The chosen class and color ride `get_player` and the render snapshot
  (`sprite` + `color`), so the browser draws the right unit in the right colour.
- **Persistent identity (client-supplied token)** — `gateway.py`. The browser mints a `crypto.randomUUID`
  once, stores it in `localStorage` (`mcp-game-token`) and connects `/app/stream` with `?token=<uuid>`.
  The server validates the UUID and derives a **deterministic** `channel_id = sha256(token)[:16]` and
  `mcp_token = mcp-<token>`, reusing the channel if it exists or creating it via the gateway's token
  injection (`create_channel(channel_id=, mcp_token=)`), catching `ChannelCapacityError` and
  re-resolving so concurrent connects converge on one channel. So the `mcpUrl`+`mcpToken` are **stable
  forever** — a reload, a reopen, even a server restart yields the identical connection, so the agent's
  mcp config never needs reinstalling. A missing or malformed token closes the socket (`1008`) — nothing
  is minted. This is the gateway's "client-supplied token" recipe adapted to the app's session model.
- **Presence** — `gateway.py`. A player and its channel linger for `session_grace_seconds` (30s) after
  the browser disconnects, so a reload keeps the same character, then are reclaimed. The token stays
  valid regardless of the grace (the channel is recreated deterministically on the next connect).
  `_teardown_after_grace` takes the `_session_lock` for its reclaim (owner-guard + pop + channel/player
  removal) and `_acquire_session` cancels a pending teardown under the same lock, so a reconnect at the
  grace boundary can never reuse a session whose channel is being reclaimed.
- **Identity — the session, no player token** — the only credential is the browser's stored UUID (the
  client-supplied token above). It derives the channel, the channel binds one `LocalProvider`/`Session`,
  and `login` **adopts** the player into that session (`session.player_id`). Every other tool is answered
  against `session.player_id` (`provider.py` → `tools.py::dispatch` → `game.py::_player`), so **no tool
  takes a player id or token** — the agent can only ever act as its own session's player. There is no
  server-side secret and nothing for the agent to reconfigure: the MCP url + `mcp_token` (both derived
  from the stored UUID) are the whole config, and they never change.
- **Grid, never pixels** — server positions are integer `Cell`s (`helpers/geometry.py`). The map's
  `tile_size` (from the `.tmj`) is only a client render hint, streamed in the map payload.
- **Tiled map** — `maps/loader.py::load_tiled` parses a real Tiled orthogonal `.tmj` (`web/assets/map/`
  `island.tmj`, 80×56, 64px tiles). It is a **standard Tiled 1.10 file editable in the Tiled editor**
  (unique object ids, `next*` counters, tileset image `../terrain/tileset.png` relative to the map so
  Tiled resolves it — the client path is fixed in the loader since the browser serves from the web
  root). `foodCap` is a Tiled **map custom property** (`_map_prop`), so it survives a Tiled round-trip.
  Authoring a new map (layer names, object names → kind, required properties, the rules the loader
  enforces) is documented in [`docs/maps.md`](docs/maps.md). The loader rejects anything malformed with
  a friendly `MapError`: an infinite map, a missing/external tileset, a wrong-sized `ground`, **non-square
  tiles** (`tilewidth` must equal `tileheight`), an `objects`/`spawns` layer that is not an
  object group, an unknown object name, a missing or **non-numeric** property (`foodCap`, spawn
  `range`/`max`, coordinates) and an object placed **out of bounds** — never a raw `KeyError`/`ValueError`.
  The `ground` tile layer is an autotiled grass island on water
  (Wang coastline set from `terrain/tileset.png`); `gid 0` is sea. The `objects` object group holds
  the static art, each classified by `objects.py::get_object_kind` (no hardcoded names): `building`/
  `rock` are **solid** and carry a `sprite` plus a configurable square **footprint** in cells (1×1,
  2×2, 4×3, …), `bush` is a non-solid decoration, `tree` is choppable and `item` is collectible (carries
  an `item` property). The client renders `ground` + `objects` from the stream and reads the same object
  flags from the catalog; the server keeps only the derived blocked-cell grid.
- **Collision (tile-based)** — `MapDefinition.is_blocked` is true for sea tiles, a solid object's
  blocked cells, and out-of-bounds. `World._blocked` adds standing trees. The server walks cell by cell —
  since positions are authoritative integer cells, a shape is just the **set of cells it covers**. A
  solid blocks only its bottom rows (its base), capped at `loader.py::SOLID_DEPTH` (**2**), so a taller
  building (the 4×3 castle) keeps its **back row walkable** and an actor can pass behind it and be
  occluded by the sprite for depth; a 1–2 row solid (rocks, houses) blocks fully. The island map includes
  a rock-**walled reserved enclosure** (a hollow rectangle of solid rocks with a one-cell gate) so a
  player has to route through the opening to enter — the collision system alone enforces it.
- **Actor collision** — `World._occupied_by_actor(cell, mover)` is true when any other alive player or
  enemy stands on `cell`. `move` (and `_enemy_move`) refuse a target that is blocked **or** occupied,
  so no one steps onto another actor. It only guards the target, never the origin, so an actor that
  starts or respawns stacked on another can always step **out** to a free cell.
- **State machine (everything has one)** — `fsm.py`. States: idle, moving, attacking, shooting,
  spawning, dead. `World` enforces: you cannot act while moving/spawning, cannot move while busy, and
  cannot start a new swing/shot until the current one's animation ends. `_kill` transitions to `dead`
  through the machine (`to(DEAD)`, legal from every live state) and enemies revive with a fresh
  `StateMachine`. Death is idempotent: `_damage` ignores an already-dead target, so two hits in one
  tick never double-count a kill or re-enter `dead`.
- **Movement is server-timed** — `World.move` advances exactly **one cell** and holds `moving` for
  the player's `move_duration`; other actions are blocked until it ends. Blocked cells are refused.
  `move_duration` is therefore both the travel time **and** the cooldown between moves (a player cannot
  move again until it elapses), and speed items shorten it (`attributes.py`).
- **Weapons — one per class, list still supported** — `weapons.py`. Each has kind (melee/ranged),
  damage, range, attack duration and cooldown. A contact (melee) weapon out-damages the ranged bow
  (`sword` > `bow`). Two timers gate a strike: `busy_until` holds the swing/shot state for
  `attack_duration` (the animation), then `attack_ready_at` keeps the next strike locked out for the
  rest of `cooldown` (`_begin_attack`/`_busy_for_attack`), so the documented cooldown is enforced, not
  just the animation. `Player.weapons` is a **list** (the architecture allows several), but each class
  carries exactly one, set from its `ClassSpec`: warrior→`sword` (melee), archer→`bow` (ranged),
  monk→`staff` (melee), lancer→`spear` (melee, reaches **two cells**). The `shoot` tool fires the ranged
  weapon (only the archer carries one). The `weapons` tool lists what a player carries.
- **Attributes + items** — `attributes.py` + `items.py`. Base stats from `config.py`; carried items
  change max health, move duration (speed), vision range and attack speed (attacking duration).
  Collectibles (food, coins, items) are picked up by stepping onto their cell: `move` runs
  `World._collect_at` for immediate feedback, and each tick `World._resolve_pickups` sweeps up
  **everything** a standing player sits on, so loot dropped under its feet or a coin left under a
  collected food is still taken without another step.
- **Vision + wave** — vision range is a cell radius (attributes). `look_around` returns visible
  objects within range plus a four-direction scan, and increments `vision_pulse_seq` so the client
  draws the wave **only when the agent looks**. Other players' items and vision range are **private**
  (`Player.to_view` hides them; the browser snapshot shows vision only for the wave). A dead player
  awaiting respawn cannot act: `look_around`/`search_around`/`speak` return a `dead` reason (no vision
  wave, no scan, no bubble on a corpse), matching how `move`/`attack`/`shoot`/`chop` already refuse.
- **search_around** — `World.search_around`; filters visible objects by type. Valid types in
  `game.py::SEARCH_TYPES`: player, enemy, food, item, coin, tree.
- **Where things are** — every visible entry (`World._describe`) carries the object's grid `position`,
  its straight-line `distance`, its `steps` (chebyshev, the moves to reach it), the cell `offset`
  `{dx, dy}` and the `direction` to walk (or `here`), so the agent knows where everything is and what
  to do.
- **Resources** — `entities/player.py::Player.resources` (`wood`, `gold`). Chopping a tree until it
  falls grants `wood_per_tree`; **gold** is collected from **coins** (`entities/coin.py::Coin`), never
  credited directly. Meat (food) heals. Resources ride the snapshot and `get_player`; the catalog lists
  the keys.
- **Coins (gold)** — `entities/coin.py::Coin`. Gold lies on the ground as coins: `World._replenish_coins`
  scatters roaming coins map-wide (`coin_cap`, `coin_spawn_interval`) and `_drop_loot` drops a coin where
  a defeated enemy falls (loot `gold` becomes a coin, not an instant credit). Stepping onto a coin
  (`_collect_at`) adds its `value` to the player's gold. Coins are visible to `look_around`/`search_around`
  (`coin`) so an agent can find and walk onto them.
- **Speak** — `game.py::GameService.speak`. ≤ `speech_max_length` (50), single line, no tabs/breaks;
  shows as a bubble for a few seconds (`World.speak`).
- **Food** — `entities/food.py`; capped per map (`MapDefinition.food_cap`) and topped up on an
  interval (`World._replenish_food`); stepping onto it heals `food_heal`. The interval timer advances
  every period whether or not it spawns, so a dip below the cap still waits a full interval instead of
  refilling the instant a player consumes one (scarcity holds even when loot drops push food to the cap).
- **Roaming item respawn** — `World._replenish_pickups` scatters random items from the catalog onto
  free cells map-wide, kept at `pickup_cap` and topped up every `pickup_spawn_interval` (config), so
  the world always has items to find beyond the ones placed in the Tiled map. It advances its timer the
  same way, so it never refills faster than the interval.
- **Trees** — `entities/tree.py`; block movement, take several `chop`s to fall, then regrow. Each
  `chop` swings the melee weapon through the same `_busy_for_attack` gate as `attack` (so it honours
  the weapon busy state and cooldown) and the felling chop grants wood. `_regrow_trees` holds off while
  an actor **or a collectible** sits on the stump, so a regrown tree never traps a player nor seals a
  pickup or food inside a solid cell.
- **NPCs / spawns** — `maps/spawn_point.py::SpawnPoint` (entity, x, y, range, max). `World._fill_spawns` /
  `_revive_enemy` spawn and respawn NPCs randomly inside the range up to the max, each after its own
  `respawn_seconds` (from the `EnemySpec`). A revived enemy resets its timers and takes a fresh
  `StateMachine`, so it acts immediately. Every NPC parameter lives in its `EnemySpec` so profiles are
  reusable and animals drop in without engine changes.
- **NPC behavior profiles** — `World._act_enemy` dispatches on `Behavior`: **aggressive** chases the
  nearest visible player and attacks (melee `_enemy_attack`, or ranged `_launch_arrow` firing a hostile
  `Projectile`); **skittish** flees when a player is within `flee_range` and otherwise wanders;
  **wander** roams on `wander_chance`. `flee_when_attacked` NPCs are spooked for `spook_seconds` on a hit
  (`_damage`) and flee regardless of profile. Enemies move slower than players and hit softly. The
  four combat NPCs (`enemy_warrior`, `enemy_archer`, `enemy_lancer`, `enemy_monk`) are aggressive and
  render red via `EnemySpec.sprite` (warrior/archer/lancer/monk); the three **sheep** animals
  (`sheep_shy` skittish, `sheep_flighty` spooked-and-flees, `sheep_calm` just wanders) share the `sheep`
  sprite and drop food, gold or items — a new enemy or animal is one `EnemySpec` entry plus its spawn point.
- **Loot** — `World._drop_loot` rolls each `EnemySpec.loot` `LootDrop`: `food` drops a `Food` where the
  NPC fell, an item id (in `ITEMS`) drops a `Pickup`, anything else (gold) drops a `Coin` to walk onto.
  `npcs/registry.py` validates every loot `resource` against `{food} ∪ ITEMS ∪ RESOURCE_KINDS` at import,
  so an unknown resource fails fast instead of a runtime error when the NPC dies.
- **Placement never lands on a bad cell** — `_emptiest_spawn`/`_spawn_within` sample for variety but,
  when sampling misses, fall back to a deterministic `_first_free_cell` scan and **raise** if the map is
  genuinely full rather than returning a blocked or occupied cell. No actor is ever placed inside a wall
  or on top of another.
- **Death → respawn + immunity** — `World._kill` / `_resolve_respawns`. On death the server places
  the player at the **emptiest area** (`_emptiest_spawn`, farthest from others) and grants
  `spawn_immunity_seconds` (5s) of blinking immunity; immune players take no damage and are not
  targeted. The **player revives quickly** (`respawn_delay_seconds`, 3s) — it is the one exception:
  every other world respawn (food, roaming pickups, felled trees, NPCs) is **≥ 2 minutes**
  (`food_spawn_interval`/`pickup_spawn_interval`/`tree_regrow_seconds` = 120s, each `EnemySpec.respawn_seconds` = 120s), so resources stay scarce.
  A slain enemy is **dropped from the render snapshot** (`World.snapshot` keeps only live enemies), so it
  vanishes with the death burst instead of lingering as a corpse; a dead player stays briefly (dimmed)
  until it revives.
- **Shared catalog** — `catalog.py`, sent on the stream handshake (there is no browseable endpoint).
  Client and server share one definition of weapons/items/enemies/limits; the client only reads and
  draws. The map likewise reaches the client only through the stream handshake, never as an endpoint.
- **Depth/Y-sort, interpolation, camera** — client responsibilities; `helpers/interpolate.js` renders
  ~120 ms in the past and lerps projectiles and collectibles between the two surrounding snapshots.
  **Actors (players, enemies) instead walk smoothly** toward their authoritative cell over the per-step
  duration the snapshot carries (`moveMs` = the server's move/speed duration), so a slow enemy slides
  between tiles instead of popping; a jump of **more than 2 cells** (a respawn) snaps. `visionPulseSeq`/
  `speech`/`immune` drive effects. `EntityView.#depth` y-sorts actors and standing
  objects by their base, projectiles above, and **collectibles (food, items) in a band strictly below
  every actor** (`py - groundBand`, still above the ground), so a pickup a unit stands on always draws
  under it. Nothing the client draws is authoritative.
- **Client rendering** — `GameScene` draws the sea as a `TileSprite` of `terrain/water.png` (the water
  colour is the art's own), places an animated `terrain/foam.png` **coastline** (16-frame `foam_drift`,
  all in sync) on every sea cell touching land, each foam sprite **nudged onto the shore** by
  `FOAM.offset` (`#landDirection`) and drawn **below** the ground tilemap, so the grass tucks over its
  inner part and only a thin sea-side rim shows — a foam line hugging the coast (the `FOAM` constant
  tunes scale/offset/alpha in one place, shared with the gallery). It builds a Phaser tilemap
  from `map.ground` + `tileset.png`, and places the `map.objects` sprites Y-sorted by their base so
  units pass in front/behind. Choppable trees render one of four **variants** (`TREES`, chosen per tree
  by its cell) and rock objects use four sprites, so forests and shores look varied. Drifting `Clouds` live in
  a world-space layer over the map (map bounds plus `CLOUD_MARGIN_CELLS`), each cloud reassigned a
  random height/size/speed when it wraps, above the world yet below the HUD scene. The renderer is
  antialiased so text stays smooth, while the world textures are set to nearest filtering so the pixel
  art stays sharp. `game/Music.js` loops the background track (mute with **M**). The camera locks onto
  the player, recentres on resize.
- **Combat feedback** — the attacking state plays the unit's attack spritesheet, the ranged bow fires
  the `arrow` projectile which leaves a short fading golden trail, a drop in an entity's `health` (or a
  tree's `hits`) flashes it red once (a fill tint via `setTintMode`) and spawns a floating `DamageNumbers` value that
  rises and fades in a random direction (red for units, wood for trees), and spawn/death fire a real
  Phaser particle burst from a runtime-generated `spark` texture (blue on arrival, amber on leaving).
- **HiDPI (retina)** — Phaser sizes its canvas in CSS pixels, so on a retina screen the browser upscales
  the whole canvas and text turns blurry. `main.js` fixes this: `Scale.NONE` with the game sized to
  `window × DPR` (physical pixels) and the canvas CSS pinned to logical size (`scale.refresh()` after,
  so input maps correctly). The world compensates with `camera zoom × DPR` and the HUD with a single
  `DPR`-scaled layer, so every component keeps laying out in logical coordinates. `DPR` (capped at 2) is
  in `constants.js`.
- **Image HUD** — `HudScene` composes the `src/ui` kit from the Tiny Swords art (no DOM): a wooden
  `HealthBar` (a 3-slice frame with a gradient fill sized to the health ratio) with the name, a
  parchment `StatusStrip` (label + dot: `Connecting` yellow, `Live` green/amber/red by `latencyLevel`
  once online, `Reconnecting` red when offline; `HudScene.update` refreshes it **first**, before the
  self-dependent widgets, so the connection indicator is never starved. On a drop `GameSocket` clears
  the latency and `main.js` zeroes the online count, so the strip shows `Reconnecting  — ms  0 online`
  rather than stale numbers, and `GameSocket` retries with exponential backoff), an `Inventory` of
  resource chips (wood/gold icons + counts) and a parchment `StatsWindow` opened by a shield `Button`. Windows are a `Panel` 9-slice and the bar frame is a
  3-slice, both from continuous sliceable textures (`ui/panel9.png`, `ui/hpbar.png`) so nothing
  distorts at any size. The landing (`scenes/LoginScene.js`, all Phaser) is a login gate over the Tiny
  Swords sky with drifting clouds; Login reveals the connect option buttons, each opening a `Window`.

## Conventions

`uv` + ruff `line-length = 100` for Python (**100% branch coverage gate** over the whole `app`
package); `vite` + `vitest` for the client (one class per file, **100% coverage** over `helpers`/`net`
only — the `vitest.config.js` gate does not cover the Phaser view layer, which is guarded by the build
and manual smoke runs). Empty `__init__.py`, code and comments
in **English**, comments **rare** (non-obvious intent only, lowercase for single-line `#`/`//`, no
narration, no section separators), no semicolons splitting sentences, no legacy/back-compat/fallbacks,
single-line signatures/calls where they fit. Separate blocks of different responsibility with a blank
line (Python and `client/src`).

## Commands

```bash
make install    # python dev deps + build the client bundle (uses npm + uv)
make client     # (re)build the client bundle into src/app/web/dist
make lint       # ruff
make test       # pytest + vitest
make coverage   # both suites with their 100% coverage gates
make run        # build the client, then serve the game on 127.0.0.1:8000
```

## Gotchas

- Gateway settings use the `GATEWAY_` prefix; app settings use `APP_` (`config.py`).
- Enable the admin dashboard with `GATEWAY_ADMIN_ENABLED=true GATEWAY_ADMIN_KEY=... make run`, then
  open `/admin?key=...`. Each browser session appears there as a connected provider.
- A channel's `channel_id` and `mcp_token` are derived from the browser's stored token, so they are
  stable across reloads and server restarts (the channel is recreated on demand). A channel is only
  reclaimed after the grace with the browser gone.
- The client is built (Vite): edit `client/src`, run `make client` (or `make run`, which builds first).
  `src/app/web/dist` is generated and gitignored — never edit it by hand.
- The client-supplied-token model means any well-formed UUID mints a channel, so an unauthenticated
  flood of distinct tokens can consume up to `GATEWAY_MAXIMUM_CHANNELS` (unlogged-in sessions self-clear
  after `session_grace_seconds`). This is inherent to the recipe — cap it at the edge (per-IP connection
  rate limiting) or lower `GATEWAY_MAXIMUM_CHANNELS` with monitoring for a public deployment.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | The single-page client: menu (connect box) that becomes the game on login. |
| `GET` | `/app/info` | `{playersOnline, tools}` — for the login scene's online count and Tools window. |
| `GET` (WS) | `/app/stream` | The session socket, opened with `?token=<uuid>` (the browser's stored token). Server → `session` (mcp url+token), then `login`, `catalog`, `map`, `snapshot`, `me`, `pong`. Client → `ping`, `me`. A missing/malformed token is refused. |
| `GET` | `/static/...` | The self-hosted client, fonts and assets (served `no-cache`). |
| `GET` | `/mcp/{sessionChannelId}`, `/provider`, `/health`, `/admin` | Inherited from the gateway. |

The agent points its MCP client at the `mcpUrl` + `mcpToken` the browser shows in the connect box
(delivered in the session socket's first `session` message).

## Visual verification note

The Phaser client is built, syntax-checked and fully served, with correct sprite-frame math derived
from the real Tiny Swords dimensions (units 192×192/frame, tileset 64px, trees 192×256/frame). It is
HiDPI (`Scale.NONE` sized to `window × DPR`, `roundPixels`, world textures at nearest filtering), so it
adapts to any resolution. The look is verified during development with headless-Chromium smoke runs
(login → game render → combat → resize, asserting zero console errors), not by committed pixel tests.

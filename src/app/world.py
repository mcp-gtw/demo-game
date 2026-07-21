from __future__ import annotations

import random
from typing import Any

from app.attributes import compute_attributes
from app.classes import get_class
from app.colors import get_color
from app.config import AppSettings
from app.entities.coin import Coin
from app.entities.enemy import Enemy
from app.entities.food import Food
from app.entities.pickup import Pickup
from app.entities.player import Player
from app.entities.projectile import Projectile
from app.entities.tree import Tree
from app.errors import CommandError, StateError
from app.fsm import ATTACKING, DEAD, IDLE, MOVING, SHOOTING, SPAWNING, StateMachine
from app.helpers.geometry import CARDINALS, DIRECTIONS, Cell
from app.items import ITEMS
from app.maps.loader import default_map
from app.maps.map_definition import MapDefinition
from app.npcs.behavior import Behavior
from app.npcs.registry import get_enemy_spec
from app.weapons import MELEE, RANGED, WEAPONS, WeaponSpec

# how many random cells to sample when looking for the emptiest spawn area
_SPAWN_SAMPLES = 24
_DIRECTION_NAMES = tuple(DIRECTIONS)
_ITEM_IDS = tuple(ITEMS)


class World:
    """The authoritative grid simulation shared by every player."""

    def __init__(
        self,
        settings: AppSettings,
        game_map: MapDefinition | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.settings = settings
        self.map = game_map or default_map()
        self.rng = rng or random.Random()
        self.time = 0.0

        self.players: dict[str, Player] = {}
        self.enemies: dict[str, Enemy] = {}
        self.projectiles: dict[str, Projectile] = {}
        self.food: dict[str, Food] = {}
        self.trees: dict[str, Tree] = {}
        self.pickups: dict[str, Pickup] = {}
        self.coins: dict[str, Coin] = {}

        self._seq = 0
        self._next_food_at = 0.0
        self._next_pickup_at = 0.0
        self._next_coin_at = 0.0

        self._load_objects()
        self._fill_spawns()

    def add_player(
        self, player_id: str, name: str, char_class: str | None = None, color: str | None = None
    ) -> Player:
        spec = get_class(char_class)
        player = Player(
            id=player_id,
            name=name,
            cell=self._emptiest_spawn(),
            attributes=compute_attributes(self.settings, []),
            char_class=spec.id,
            sprite=spec.sprite,
            color=get_color(color),
            weapons=list(spec.weapons),
        )
        self.players[player_id] = player
        self._enter_spawn(player)
        return player

    def remove_player(self, player_id: str) -> None:
        self.players.pop(player_id, None)
        self.projectiles = {
            pid: shot for pid, shot in self.projectiles.items() if shot.owner_id != player_id
        }

    def require_player(self, player_id: str) -> Player:
        player = self.players.get(player_id)

        if player is None:
            raise CommandError("You are not present in the world, log in again")

        return player

    def look_around(self, player: Player) -> dict[str, Any]:
        if not player.alive:
            return {"reason": "dead", "visible": [], "directions": {}}

        # the vision wave only pulses when the agent asks what is around it
        player.vision_pulse_seq += 1
        radius = player.attributes.vision_range

        return {
            "self": player.to_public(self.time),
            "map": {"cols": self.map.cols, "rows": self.map.rows},
            "visionRange": radius,
            "visible": self._visible(player, radius),
            "directions": self._scan_directions(player, radius),
        }

    def search_around(self, player: Player, kind: str) -> dict[str, Any]:
        if not player.alive:
            return {"type": kind, "reason": "dead", "count": 0, "matches": []}

        radius = player.attributes.vision_range
        matches = [entry for entry in self._visible(player, radius) if entry["kind"] == kind]

        return {"type": kind, "visionRange": radius, "count": len(matches), "matches": matches}

    def move(self, player: Player, direction: str) -> dict[str, Any]:
        if not player.alive:
            return {"moved": False, "reason": "dead"}

        if player.machine.is_busy():
            ready = self._ready_ms(player.busy_until)
            return {"moved": False, "reason": "busy", "readyInMs": ready}

        self._validate_direction(direction)
        target = player.cell.stepped(direction)

        if self._blocked(target) or self._occupied_by_actor(target, player):
            player.facing = direction
            return {"moved": False, "reason": "blocked", "position": player.cell.as_dict()}

        player.facing = direction
        player.cell = target
        player.machine.to(MOVING)
        player.busy_until = self.time + player.attributes.move_duration

        collected = self._collect_at(player)

        return {
            "moved": True,
            "position": target.as_dict(),
            "facing": direction,
            "busyForMs": self._ready_ms(player.busy_until),
            "collected": collected,
        }

    def attack(self, player: Player, target_id: str) -> dict[str, Any]:
        weapon_id = player.weapon_of(MELEE)

        if weapon_id is None:
            return {"hit": False, "reason": "no_melee_weapon"}

        weapon = WEAPONS[weapon_id]
        blocked = self._busy_for_attack(player, "hit")

        if blocked is not None:
            return blocked

        target = self._find_target(target_id, attacker=player)

        if target is None:
            return {"hit": False, "reason": "invalid_target"}

        distance = player.cell.chebyshev_to(target.cell)

        if distance > weapon.range:
            return {"hit": False, "reason": "out_of_range", "distance": distance}

        self._begin_attack(player, weapon, ATTACKING)
        killed = self._damage(target, weapon.damage, attacker=player)

        return {
            "hit": True,
            "weapon": weapon_id,
            "targetId": target.id,
            "targetKind": "enemy" if isinstance(target, Enemy) else "player",
            "damage": weapon.damage,
            "killed": killed,
            "targetHealth": target.health,
        }

    def shoot(self, player: Player, direction: str | None) -> dict[str, Any]:
        weapon_id = player.weapon_of(RANGED)

        if weapon_id is None:
            return {"fired": False, "reason": "no_ranged_weapon"}

        weapon = WEAPONS[weapon_id]
        blocked = self._busy_for_attack(player, "fired")

        if blocked is not None:
            return blocked

        heading = direction or player.facing
        self._validate_direction(heading)

        self._begin_attack(player, weapon, SHOOTING)
        player.facing = heading
        self._seq += 1
        projectile = Projectile(
            id=f"shot:{self._seq}",
            owner_id=player.id,
            kind_name=weapon.projectile,
            cell=player.cell.copy(),
            direction=heading,
            damage=weapon.damage,
            speed=weapon.projectile_speed,
            range_left=weapon.range,
        )
        self.projectiles[projectile.id] = projectile

        return {
            "fired": True,
            "weapon": weapon_id,
            "projectileId": projectile.id,
            "direction": heading,
        }

    def speak(self, player: Player, text: str) -> dict[str, Any]:
        if not player.alive:
            return {"said": None, "reason": "dead"}

        player.speech_text = text
        player.speech_until = self.time + 4.0
        return {"said": text}

    def chop(self, player: Player, target_id: str) -> dict[str, Any]:
        weapon_id = player.weapon_of(MELEE)

        if weapon_id is None:
            return {"chopped": False, "reason": "no_melee_weapon"}

        blocked = self._busy_for_attack(player, "chopped")

        if blocked is not None:
            return blocked

        tree = self.trees.get(target_id)

        if tree is None or tree.broken:
            return {"chopped": False, "reason": "invalid_target"}

        if player.cell.chebyshev_to(tree.cell) > 1:
            return {"chopped": False, "reason": "out_of_range"}

        player.facing = self._facing_towards(player.cell, tree.cell)
        self._begin_attack(player, WEAPONS[weapon_id], ATTACKING)
        tree.hits -= 1

        if tree.hits > 0:
            return {"chopped": True, "broken": False, "hits": tree.hits}

        tree.broken = True
        tree.regrow_at = self.time + self.settings.tree_regrow_seconds
        player.resources["wood"] += self.settings.wood_per_tree

        return {
            "chopped": True,
            "broken": True,
            "hits": 0,
            "wood": self.settings.wood_per_tree,
            "resources": dict(player.resources),
        }

    def tick(self, dt: float) -> None:
        self.time += dt
        self._resolve_busy()
        self._advance_projectiles()
        self._advance_enemies()
        self._resolve_respawns()
        self._resolve_pickups()
        self._regrow_trees()
        self._replenish_food()
        self._replenish_pickups()
        self._replenish_coins()

    def snapshot(self) -> dict[str, Any]:
        now = self.time
        return {
            "time": round(now, 3),
            "map": {"cols": self.map.cols, "rows": self.map.rows, "tileSize": self.map.tile_size},
            "players": [player.to_snapshot(now) for player in self.players.values()],
            "enemies": [enemy.to_public() for enemy in self.enemies.values() if enemy.alive],
            "projectiles": [shot.to_public() for shot in self.projectiles.values()],
            "food": [food.to_public() for food in self.food.values()],
            "trees": [tree.to_public() for tree in self.trees.values()],
            "pickups": [pickup.to_public() for pickup in self.pickups.values()],
            "coins": [coin.to_public() for coin in self.coins.values()],
        }

    def _busy_for_attack(self, player: Player, key: str) -> dict[str, Any] | None:
        if not player.alive:
            return {key: False, "reason": "dead"}

        # moving, spawning or a still-playing swing/shot lock out the next strike
        if player.machine.is_busy():
            return {key: False, "reason": "busy", "readyInMs": self._ready_ms(player.busy_until)}

        # the swing finished but the weapon is still recovering for the rest of its cooldown
        if self.time < player.attack_ready_at:
            ready = self._ready_ms(player.attack_ready_at)
            return {key: False, "reason": "on_cooldown", "readyInMs": ready}

        return None

    def _begin_attack(self, player: Player, weapon: WeaponSpec, state: str) -> None:
        # an attack only ever starts from idle, so the swing state is always a fresh transition
        player.machine.to(state)
        player.busy_until = self.time + weapon.attack_duration / player.attributes.attack_speed
        player.attack_ready_at = self.time + weapon.cooldown

    def _advance_projectiles(self) -> None:
        for shot in list(self.projectiles.values()):
            if not self._step_projectile(shot):
                self.projectiles.pop(shot.id, None)

    def _step_projectile(self, shot: Projectile) -> bool:
        dx, dy = DIRECTIONS[shot.direction]

        for _ in range(max(1, shot.speed)):
            shot.cell = shot.cell.moved(dx, dy)
            shot.range_left -= 1

            if self._blocked(shot.cell):
                return False

            if self._projectile_hit(shot):
                return False

            if shot.range_left <= 0:
                return False

        return True

    def _projectile_hit(self, shot: Projectile) -> bool:
        owner = self.players.get(shot.owner_id)

        # an enemy arrow only strikes players, a player's shot strikes enemies and other players
        if shot.hostile:
            targets = list(self.players.values())
        else:
            targets = [*self.enemies.values(), *self.players.values()]

        for target in targets:
            if target.id == shot.owner_id or not target.alive:
                continue

            if isinstance(target, Player) and target.is_immune(self.time):
                continue

            if target.cell.equals(shot.cell):
                self._damage(target, shot.damage, attacker=owner)
                return True

        return False

    def _advance_enemies(self) -> None:
        for enemy in self.enemies.values():
            if not enemy.alive or self.time < enemy.busy_until:
                continue

            if enemy.machine.is_busy():
                enemy.machine.to(IDLE)

            self._act_enemy(enemy)

    def _act_enemy(self, enemy: Enemy) -> None:
        threat = self._nearest_prey(enemy)

        if self._is_fleeing(enemy, threat):
            self._enemy_move(enemy, self._facing_towards(threat.cell, enemy.cell))
        elif enemy.behavior is Behavior.AGGRESSIVE and threat is not None:
            if self._can_attack(enemy, threat):
                self._enemy_attack(enemy, threat)
            else:
                self._enemy_move(enemy, self._facing_towards(enemy.cell, threat.cell))
        elif enemy.behavior in (Behavior.SKITTISH, Behavior.WANDER):
            self._wander(enemy)

    def _is_fleeing(self, enemy: Enemy, threat: Player | None) -> bool:
        if threat is None:
            return False

        spooked = enemy.flee_when_attacked and self.time < enemy.spooked_until
        approached = (
            enemy.behavior is Behavior.SKITTISH
            and enemy.cell.distance_to(threat.cell) <= enemy.flee_range
        )
        return spooked or approached

    def _wander(self, enemy: Enemy) -> None:
        if self.rng.random() >= enemy.wander_chance:
            return

        self._enemy_move(enemy, self.rng.choice(_DIRECTION_NAMES))

    def _can_attack(self, enemy: Enemy, prey: Player) -> bool:
        if enemy.cell.chebyshev_to(prey.cell) > enemy.attack_range:
            return False

        if not enemy.ranged:
            return True

        # a ranged enemy fires only when the prey sits on one of its eight rays
        dx, dy = prey.cell.x - enemy.cell.x, prey.cell.y - enemy.cell.y
        return dx == 0 or dy == 0 or abs(dx) == abs(dy)

    def _enemy_attack(self, enemy: Enemy, prey: Player) -> None:
        if self.time < enemy.attack_ready_at:
            return

        enemy.facing = self._facing_towards(enemy.cell, prey.cell)
        enemy.busy_until = self.time + enemy.attack_duration
        enemy.attack_ready_at = self.time + enemy.attack_cooldown

        if enemy.ranged:
            enemy.machine.to(SHOOTING)
            self._launch_arrow(enemy)
        else:
            enemy.machine.to(ATTACKING)
            self._damage(prey, enemy.damage, attacker=None)

    def _launch_arrow(self, enemy: Enemy) -> None:
        self._seq += 1
        shot_id = f"shot:{self._seq}"
        self.projectiles[shot_id] = Projectile(
            id=shot_id,
            owner_id=enemy.id,
            kind_name="arrow",
            cell=enemy.cell.copy(),
            direction=enemy.facing,
            damage=enemy.damage,
            speed=enemy.projectile_speed,
            range_left=enemy.attack_range,
            hostile=True,
        )

    def _enemy_move(self, enemy: Enemy, direction: str) -> None:
        target = enemy.cell.stepped(direction)
        enemy.facing = direction

        if self._blocked(target) or self._occupied_by_actor(target, enemy):
            return

        enemy.cell = target
        enemy.machine.to(MOVING)
        enemy.busy_until = self.time + enemy.speed_duration

    def _nearest_prey(self, enemy: Enemy) -> Player | None:
        candidates = [
            player
            for player in self.players.values()
            if player.alive
            and not player.is_immune(self.time)
            and enemy.cell.distance_to(player.cell) <= enemy.vision_range
        ]

        if not candidates:
            return None

        return min(candidates, key=lambda player: enemy.cell.distance_to(player.cell))

    def _resolve_respawns(self) -> None:
        for enemy in self.enemies.values():
            if not enemy.alive and enemy.respawn_at is not None and self.time >= enemy.respawn_at:
                self._revive_enemy(enemy)

        for player in self.players.values():
            due = player.respawn_at is not None and self.time >= player.respawn_at

            if not player.alive and due:
                player.cell = self._emptiest_spawn()
                player.health = player.attributes.max_health
                player.alive = True
                player.respawn_at = None
                self._enter_spawn(player)

    def _revive_enemy(self, enemy: Enemy) -> None:
        spawn = self.map.spawns[enemy.spawn_index]
        enemy.cell = self._spawn_within(spawn.x, spawn.y, spawn.range)
        enemy.health = enemy.max_health
        enemy.alive = True
        enemy.respawn_at = None
        enemy.spooked_until = 0.0
        enemy.busy_until = 0.0
        enemy.attack_ready_at = 0.0
        enemy.machine = StateMachine()

    def _enter_spawn(self, player: Player) -> None:
        player.machine.to(SPAWNING)
        player.busy_until = self.time + self.settings.entry_animation_seconds
        player.immune_until = self.time + self.settings.spawn_immunity_seconds

    def _damage(self, target: Enemy | Player, amount: int, *, attacker: Player | None) -> bool:
        if not target.alive:
            return False

        if isinstance(target, Player) and target.is_immune(self.time):
            return False

        target.health = max(0, target.health - amount)

        if target.health > 0:
            if isinstance(target, Enemy) and target.flee_when_attacked:
                target.spooked_until = self.time + target.spook_seconds

            return False

        self._kill(target)

        if attacker is not None and attacker.id != target.id and attacker.alive:
            attacker.kills += 1

            if isinstance(target, Enemy):
                self._drop_loot(target)

        return True

    def _drop_loot(self, enemy: Enemy) -> None:
        for drop in get_enemy_spec(enemy.entity).loot:
            if self.rng.random() >= drop.chance:
                continue

            if drop.resource == "food":
                self._seq += 1
                self.food[f"food:{self._seq}"] = Food(
                    f"food:{self._seq}", enemy.cell.copy(), drop.amount
                )
            elif drop.resource in ITEMS:
                self._seq += 1
                self.pickups[f"loot:{self._seq}"] = Pickup(
                    f"loot:{self._seq}", enemy.cell.copy(), drop.resource
                )
            else:
                self._seq += 1
                self.coins[f"coin:{self._seq}"] = Coin(
                    f"coin:{self._seq}", enemy.cell.copy(), drop.amount
                )

    def _kill(self, target: Enemy | Player) -> None:
        target.alive = False
        target.machine.to(DEAD)

        if isinstance(target, Enemy):
            target.respawn_at = self.time + target.respawn_seconds
        else:
            target.deaths += 1
            target.respawn_at = self.time + self.settings.respawn_delay_seconds

    def _resolve_pickups(self) -> None:
        # sweep up everything a player is standing on, so loot dropped under its feet or a coin left
        # under a food it collected still gets picked up without needing another step
        for player in self.players.values():
            if not player.alive:
                continue

            while self._collect_at(player) is not None:
                pass

    def _resolve_busy(self) -> None:
        for player in self.players.values():
            if player.machine.is_busy() and self.time >= player.busy_until:
                player.machine.to(IDLE)

    def _collect_at(self, player: Player) -> dict[str, Any] | None:
        for food_id, food in list(self.food.items()):
            if food.cell.equals(player.cell):
                del self.food[food_id]
                player.health = min(player.attributes.max_health, player.health + food.heal)
                return {"kind": "food", "heal": food.heal, "health": player.health}

        for coin_id, coin in list(self.coins.items()):
            if coin.cell.equals(player.cell):
                del self.coins[coin_id]
                player.resources["gold"] += coin.value
                return {"kind": "gold", "gold": coin.value, "total": player.resources["gold"]}

        for pickup_id, pickup in list(self.pickups.items()):
            if pickup.cell.equals(player.cell):
                del self.pickups[pickup_id]
                self._grant_item(player, pickup.item)
                return {"kind": "item", "item": pickup.item}

        return None

    def _grant_item(self, player: Player, item_id: str) -> None:
        player.items.append(item_id)
        health_ratio = player.health / player.attributes.max_health
        player.attributes = compute_attributes(self.settings, player.items)
        player.health = max(1, round(player.attributes.max_health * health_ratio))

    def _replenish_food(self) -> None:
        if self.time < self._next_food_at:
            return

        # advance the timer whether or not we spawn, so a dip below the cap still waits a full
        # interval instead of refilling the instant a player consumes one
        self._next_food_at = self.time + self.settings.food_spawn_interval

        if len(self.food) >= self.map.food_cap:
            return

        cell = self._free_cell()

        if cell is not None:
            self._seq += 1
            food_id = f"food:{self._seq}"
            self.food[food_id] = Food(food_id, cell, self.settings.food_heal)

    def _replenish_pickups(self) -> None:
        if self.time < self._next_pickup_at:
            return

        self._next_pickup_at = self.time + self.settings.pickup_spawn_interval

        if len(self.pickups) >= self.settings.pickup_cap:
            return

        cell = self._free_cell()

        if cell is not None:
            self._seq += 1
            item = self.rng.choice(_ITEM_IDS)
            self.pickups[f"item:{self._seq}"] = Pickup(f"item:{self._seq}", cell, item)

    def _replenish_coins(self) -> None:
        if self.time < self._next_coin_at:
            return

        self._next_coin_at = self.time + self.settings.coin_spawn_interval

        if len(self.coins) >= self.settings.coin_cap:
            return

        cell = self._free_cell()

        if cell is not None:
            self._seq += 1
            coin_id = f"coin:{self._seq}"
            self.coins[coin_id] = Coin(coin_id, cell, self.rng.randint(1, 3))

    def _regrow_trees(self) -> None:
        for tree in self.trees.values():
            due = tree.broken and tree.regrow_at is not None and self.time >= tree.regrow_at

            # hold off while an actor or a collectible sits on the stump, so a regrown tree never
            # traps a player or seals a pickup inside a solid cell
            actor = self._entity_at(tree.cell) in ("player", "enemy")

            if due and not actor and not self._occupied(tree.cell):
                tree.broken = False
                tree.hits = tree.max_hits
                tree.regrow_at = None

    def _visible(self, player: Player, radius: int) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []

        for other in self.players.values():
            if other.id != player.id and other.alive:
                entries.append(self._describe(other.to_view(self.time), player.cell, other.cell))

        for enemy in self.enemies.values():
            if enemy.alive:
                entries.append(self._describe(enemy.to_public(), player.cell, enemy.cell))

        for food in self.food.values():
            entries.append(self._describe(food.to_public(), player.cell, food.cell))

        for pickup in self.pickups.values():
            entries.append(self._describe(pickup.to_public(), player.cell, pickup.cell))

        for coin in self.coins.values():
            entries.append(self._describe(coin.to_public(), player.cell, coin.cell))

        for tree in self.trees.values():
            if not tree.broken:
                entries.append(self._describe(tree.to_public(), player.cell, tree.cell))

        near = [entry for entry in entries if entry["distance"] <= radius]
        near.sort(key=lambda entry: entry["distance"])
        return near

    def _scan_directions(self, player: Player, radius: int) -> dict[str, Any]:
        return {
            direction: self._scan_ray(player.cell, *DIRECTIONS[direction], radius)
            for direction in CARDINALS
        }

    def _scan_ray(self, origin: Cell, dx: int, dy: int, radius: int) -> dict[str, Any]:
        for step in range(1, radius + 1):
            cell = origin.moved(dx * step, dy * step)

            if not self.map.in_bounds(cell.x, cell.y):
                return {"distance": step, "type": "wall", "position": cell.as_dict()}

            hit = self._entity_at(cell)

            if hit is not None:
                return {"distance": step, "type": hit, "position": cell.as_dict()}

        return {"distance": None, "type": "clear"}

    def _entity_at(self, cell: Cell) -> str | None:
        if self._blocked(cell):
            return "obstacle"

        for enemy in self.enemies.values():
            if enemy.alive and enemy.cell.equals(cell):
                return "enemy"

        for player in self.players.values():
            if player.alive and player.cell.equals(cell):
                return "player"

        return None

    def _emptiest_spawn(self) -> Cell:
        best: Cell | None = None
        best_score = -1.0

        for _ in range(_SPAWN_SAMPLES):
            candidate = self._free_cell()

            if candidate is None:
                continue

            score = self._crowding_distance(candidate)

            if score > best_score:
                best_score = score
                best = candidate

        return best or self._first_free_cell()

    def _crowding_distance(self, cell: Cell) -> float:
        occupants = [*self.players.values(), *(e for e in self.enemies.values() if e.alive)]

        if not occupants:
            return float(self.map.cols + self.map.rows)

        return min(cell.distance_to(occupant.cell) for occupant in occupants)

    def _spawn_within(self, cx: int, cy: int, spread: int) -> Cell:
        for _ in range(_SPAWN_SAMPLES):
            cell = Cell(
                cx + self.rng.randint(-spread, spread),
                cy + self.rng.randint(-spread, spread),
            )

            if self._entity_at(cell) is None and not self._occupied(cell):
                return cell

        return self._first_free_cell()

    def _first_free_cell(self) -> Cell:
        for y in range(self.map.rows):
            for x in range(self.map.cols):
                cell = Cell(x, y)

                if self._entity_at(cell) is None and not self._occupied(cell):
                    return cell

        raise StateError("The map has no free cell to place an actor")

    def _free_cell(self) -> Cell | None:
        for _ in range(_SPAWN_SAMPLES):
            cell = Cell(self.rng.randrange(self.map.cols), self.rng.randrange(self.map.rows))
            free = self._entity_at(cell) is None

            if free and not self._occupied(cell):
                return cell

        return None

    def _blocked(self, cell: Cell) -> bool:
        return self.map.is_blocked(cell.x, cell.y) or self._solid_tree(cell)

    def _solid_tree(self, cell: Cell) -> bool:
        return any(tree.solid and tree.cell.equals(cell) for tree in self.trees.values())

    def _occupied(self, cell: Cell) -> bool:
        on_food = any(food.cell.equals(cell) for food in self.food.values())
        on_pickup = any(pickup.cell.equals(cell) for pickup in self.pickups.values())
        on_coin = any(coin.cell.equals(cell) for coin in self.coins.values())
        return on_food or on_pickup or on_coin

    def _occupied_by_actor(self, cell: Cell, mover: Enemy | Player) -> bool:
        actors = (*self.players.values(), *self.enemies.values())
        return any(
            other.alive and other.id != mover.id and other.cell.equals(cell) for other in actors
        )

    def _find_target(self, target_id: str, *, attacker: Player) -> Enemy | Player | None:
        if target_id == attacker.id:
            return None

        target = self.enemies.get(target_id) or self.players.get(target_id)

        if target is None or not target.alive:
            return None

        if isinstance(target, Player) and target.is_immune(self.time):
            return None

        return target

    def _facing_towards(self, origin: Cell, goal: Cell) -> str:
        dx = (goal.x > origin.x) - (goal.x < origin.x)
        dy = (goal.y > origin.y) - (goal.y < origin.y)

        for name, (ddx, ddy) in DIRECTIONS.items():
            if ddx == dx and ddy == dy:
                return name

        return "down"

    def _describe(self, view: dict[str, Any], origin: Cell, cell: Cell) -> dict[str, Any]:
        dx, dy = cell.x - origin.x, cell.y - origin.y

        return {
            **view,
            "distance": round(origin.distance_to(cell), 1),
            "steps": max(abs(dx), abs(dy)),
            "offset": {"dx": dx, "dy": dy},
            "direction": self._facing_towards(origin, cell) if dx or dy else "here",
        }

    def _ready_ms(self, ready_at: float) -> int:
        return max(0, round((ready_at - self.time) * 1000))

    def _validate_direction(self, direction: str) -> None:
        if direction not in DIRECTIONS:
            raise CommandError(f"Unknown direction: {direction}")

    def _load_objects(self) -> None:
        for index, cell in enumerate(self.map.trees):
            self.trees[f"tree:{index}"] = Tree(id=f"tree:{index}", cell=cell.copy())

        for index, (cell, item) in enumerate(self.map.pickups):
            self.pickups[f"pickup:{index}"] = Pickup(f"pickup:{index}", cell.copy(), item)

    def _fill_spawns(self) -> None:
        for index, spawn in enumerate(self.map.spawns):
            spec = get_enemy_spec(spawn.entity)

            for slot in range(spawn.max):
                enemy_id = f"enemy:{index}:{slot}"
                self.enemies[enemy_id] = Enemy(
                    id=enemy_id,
                    entity=spec.entity,
                    cell=self._spawn_within(spawn.x, spawn.y, spawn.range),
                    max_health=spec.max_health,
                    spawn_index=index,
                    damage=spec.damage,
                    vision_range=spec.vision_range,
                    attack_range=spec.attack_range,
                    speed_duration=spec.speed_duration,
                    attack_cooldown=spec.attack_cooldown,
                    attack_duration=spec.attack_duration,
                    respawn_seconds=spec.respawn_seconds,
                    behavior=spec.behavior,
                    ranged=spec.ranged,
                    projectile_speed=spec.projectile_speed,
                    flee_range=spec.flee_range,
                    flee_when_attacked=spec.flee_when_attacked,
                    spook_seconds=spec.spook_seconds,
                    wander_chance=spec.wander_chance,
                )

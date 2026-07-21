from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # simulation rate in ticks per second
    tick_rate: float = 15.0

    # base player attributes every player starts with before items change them
    base_max_health: int = 100
    base_move_duration: float = 0.28
    base_vision_range: int = 6
    base_attack_speed: float = 1.0

    # world timing
    spawn_immunity_seconds: float = 5.0
    entry_animation_seconds: float = 0.6
    respawn_delay_seconds: float = 3.0

    # how long a player and its channel linger after the browser disconnects, so a reload keeps the
    # same character. The mcp url+token stay valid regardless: they derive from the client's stored
    # token, so a later reopen (even after a restart) recreates the identical channel.
    session_grace_seconds: float = 30.0

    # a snapshot send that does not complete within this long means the consumer is stuck, so the
    # hub drops it rather than letting one blocked socket stall the simulation for everyone
    stream_send_timeout_seconds: float = 2.0

    # world respawn timings (food, pickups, trees, NPCs) never dip below two minutes, so resources
    # stay scarce. Only the player revives quickly (respawn_delay_seconds above).
    food_heal: int = 40
    food_spawn_interval: float = 120.0

    # map-wide random item respawn: how many roaming pickups to keep and how often to top them up
    pickup_cap: int = 6
    pickup_spawn_interval: float = 120.0

    # roaming gold coins (enemies also drop them): how many to keep and how often to add one
    coin_cap: int = 8
    coin_spawn_interval: float = 120.0

    # a felled tree regrows after this long
    tree_regrow_seconds: float = 120.0

    # wood a player earns per felled tree (enemy rewards come from each NPC's loot table)
    wood_per_tree: int = 3

    # input limits shared with the tool schemas
    name_max_length: int = 32
    speech_max_length: int = 50


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    return AppSettings()

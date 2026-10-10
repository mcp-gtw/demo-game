from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from mcpgtw.config import validate_oauth_url


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    mcp_auth_mode: Literal["legacy", "oauth", "dual"] = "legacy"
    public_base_url: str = ""
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr = Field(default=SecretStr(""), repr=False)
    session_cookie_name: str = "game_session"
    allowed_browser_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    oauth_mcp_client_ids: Annotated[list[str], NoDecode] = Field(default_factory=list)
    oauth_database_path: str = ""
    oauth_allow_localhost_http: bool = False
    oauth_account_registration_enabled: bool = False
    websocket_ticket_ttl_seconds: float = Field(default=30, gt=0, le=60)
    session_idle_seconds: float = Field(default=900, gt=0, allow_inf_nan=False)
    oauth_login_timeout_seconds: int = Field(default=600, ge=1, le=1800)

    oauth_browser_rate_limit_requests: int = Field(default=30, ge=1)
    oauth_browser_rate_limit_window_seconds: float = Field(default=60, gt=0, allow_inf_nan=False)
    oauth_browser_rate_limit_maximum_keys: int = Field(default=10000, ge=1)

    @field_validator("allowed_browser_origins", "oauth_mcp_client_ids", mode="before")
    @classmethod
    def parse_csv(cls, value: object) -> object:
        return (
            [part.strip() for part in value.split(",") if part.strip()]
            if isinstance(value, str)
            else value
        )

    @model_validator(mode="after")
    def validate_browser_oauth(self) -> AppSettings:
        if self.mcp_auth_mode == "legacy":
            return self

        for url in [self.public_base_url, self.oidc_issuer, *self.allowed_browser_origins]:
            validate_oauth_url(url, self.oauth_allow_localhost_http)

        if (
            not self.oidc_client_id
            or not self.oidc_client_secret.get_secret_value()
            or not self.oauth_database_path
            or self.oauth_database_path == ":memory:"
            or not self.allowed_browser_origins
            or self.public_base_url.endswith("/")
        ):
            raise ValueError(
                "OAuth requires identity, durable sessions, origins and approved MCP clients"
            )

        if not self.session_cookie_name.isascii() or not self.session_cookie_name.isidentifier():
            raise ValueError("Invalid session cookie name")

        return self

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

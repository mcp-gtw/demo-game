from app.attributes import compute_attributes
from app.config import AppSettings
from app.weapons import MELEE, RANGED, WEAPONS


def test_base_attributes_without_items():
    settings = AppSettings()
    attrs = compute_attributes(settings, [])
    assert attrs.max_health == settings.base_max_health
    assert attrs.vision_range == settings.base_vision_range
    assert attrs.move_duration == settings.base_move_duration
    assert attrs.attack_speed == settings.base_attack_speed


def test_items_change_attributes():
    settings = AppSettings()
    attrs = compute_attributes(settings, ["heart", "boots", "spyglass", "gauntlet"])
    assert attrs.max_health == settings.base_max_health + 25
    assert attrs.vision_range == settings.base_vision_range + 2
    assert attrs.move_duration < settings.base_move_duration
    assert attrs.attack_speed > settings.base_attack_speed


def test_unknown_item_is_ignored():
    settings = AppSettings()
    attrs = compute_attributes(settings, ["not-a-real-item"])
    assert attrs.max_health == settings.base_max_health


def test_attributes_public_shape():
    public = compute_attributes(AppSettings(), []).to_public()
    assert set(public) == {"maxHealth", "moveDuration", "visionRange", "attackSpeed"}


def test_weapon_catalog_and_lookup():
    assert WEAPONS["sword"].kind == MELEE
    assert WEAPONS["bow"].kind == RANGED
    assert WEAPONS["bow"].projectile == "arrow"
    assert "laser" not in WEAPONS


def test_weapon_public_shape():
    public = WEAPONS["bow"].to_public()
    assert public["kind"] == RANGED
    assert public["projectile"] == "arrow"
    assert public["cooldown"] == 0.5
    assert "allowConcurrent" not in public

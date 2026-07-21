from app.catalog import build_catalog
from app.config import AppSettings


def test_catalog_exposes_shared_game_data():
    catalog = build_catalog(AppSettings())
    assert catalog["weapons"]["bow"]["kind"] == "ranged"
    assert catalog["items"]["heart"]["effects"]
    assert catalog["enemies"]["enemy_warrior"]["maxHealth"] > 0
    assert "down_left" in catalog["directions"]
    assert set(catalog["cardinals"]) == {"up", "down", "left", "right"}
    assert "moving" in catalog["states"]
    assert "food" in catalog["searchTypes"]
    assert catalog["limits"]["nameMaxLength"] == 32

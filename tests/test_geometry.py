import math

from app.helpers.geometry import CARDINALS, DIRECTIONS, Cell


def test_directions_are_integer_unit_deltas():
    assert DIRECTIONS["up"] == (0, -1)
    assert DIRECTIONS["down_right"] == (1, 1)
    assert set(CARDINALS) == {"up", "down", "left", "right"}


def test_cell_movement_and_stepping():
    cell = Cell(2, 3)
    assert cell.moved(1, -1).as_dict() == {"x": 3, "y": 2}
    assert cell.stepped("up").as_dict() == {"x": 2, "y": 2}
    assert cell.copy().equals(cell)
    assert not cell.equals(Cell(2, 4))


def test_cell_distances():
    a = Cell(0, 0)
    b = Cell(3, 4)
    assert a.distance_to(b) == math.hypot(3, 4)
    assert a.chebyshev_to(b) == 4

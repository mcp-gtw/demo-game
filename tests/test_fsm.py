import pytest

from app.errors import StateError
from app.fsm import ATTACKING, DEAD, IDLE, MOVING, SPAWNING, StateMachine


def test_valid_transitions():
    machine = StateMachine()
    assert machine.state == IDLE
    machine.to(MOVING)
    assert machine.is_busy()
    machine.to(IDLE)
    machine.to(ATTACKING)
    machine.to(IDLE)


def test_invalid_transition_raises():
    machine = StateMachine(state=MOVING)
    with pytest.raises(StateError):
        machine.to(ATTACKING)


def test_dead_only_goes_to_spawning():
    machine = StateMachine(state=DEAD)
    assert machine.can(SPAWNING)
    assert not machine.can(IDLE)


def test_is_busy_reports_action_states():
    assert StateMachine(state=SPAWNING).is_busy()
    assert not StateMachine(state=IDLE).is_busy()

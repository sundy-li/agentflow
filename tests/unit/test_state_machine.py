import pytest

from app.domain.state_machine import (
    InvalidTransitionError,
    TaskState,
    assert_transition,
    can_transition,
)


def test_allowed_transitions():
    assert can_transition(TaskState.AGENT_ISSUE, TaskState.AGENT_REVIEWABLE)
    assert can_transition(TaskState.AGENT_REVIEWABLE, TaskState.AGENT_APPROVED)
    assert can_transition(TaskState.AGENT_REVIEWABLE, TaskState.AGENT_CHANGED)
    assert can_transition(TaskState.AGENT_CHANGED, TaskState.AGENT_REVIEWABLE)


def test_rejected_transitions():
    assert not can_transition(TaskState.AGENT_ISSUE, TaskState.AGENT_APPROVED)
    assert not can_transition(TaskState.AGENT_APPROVED, TaskState.AGENT_REVIEWABLE)
    with pytest.raises(InvalidTransitionError):
        assert_transition(TaskState.AGENT_APPROVED, TaskState.AGENT_REVIEWABLE)


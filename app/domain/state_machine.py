from enum import Enum
from typing import Iterable, Optional, Union


class InvalidTransitionError(ValueError):
    pass


class TaskState(str, Enum):
    AGENT_ISSUE = "agent-issue"
    AGENT_REVIEWABLE = "agent-reviewable"
    AGENT_CHANGED = "agent-changed"
    AGENT_APPROVED = "agent-approved"


ALLOWED_TRANSITIONS = {
    TaskState.AGENT_ISSUE: {TaskState.AGENT_REVIEWABLE},
    TaskState.AGENT_REVIEWABLE: {TaskState.AGENT_APPROVED, TaskState.AGENT_CHANGED},
    TaskState.AGENT_CHANGED: {TaskState.AGENT_REVIEWABLE},
    TaskState.AGENT_APPROVED: set(),
}


def as_task_state(value: Union[TaskState, str]) -> TaskState:
    if isinstance(value, TaskState):
        return value
    return TaskState(value)


def can_transition(from_state: Union[TaskState, str], to_state: Union[TaskState, str]) -> bool:
    source = as_task_state(from_state)
    target = as_task_state(to_state)
    if source == target:
        return True
    return target in ALLOWED_TRANSITIONS.get(source, set())


def assert_transition(from_state: Union[TaskState, str], to_state: Union[TaskState, str]) -> None:
    if not can_transition(from_state, to_state):
        raise InvalidTransitionError(
            "Invalid state transition: {0} -> {1}".format(
                as_task_state(from_state).value,
                as_task_state(to_state).value,
            )
        )


def state_from_labels(labels: Iterable[str]) -> Optional[TaskState]:
    label_set = set(labels)
    priority = [
        TaskState.AGENT_CHANGED,
        TaskState.AGENT_REVIEWABLE,
        TaskState.AGENT_APPROVED,
        TaskState.AGENT_ISSUE,
    ]
    for state in priority:
        if state.value in label_set:
            return state
    return None


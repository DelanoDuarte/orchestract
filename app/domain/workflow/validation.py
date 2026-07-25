from typing import TYPE_CHECKING

from app.domain.workflow.exceptions import WorkflowValidationError

if TYPE_CHECKING:
    from app.domain.workflow.models import WorkflowDefinition


def find_validation_issues(definition: "WorkflowDefinition") -> list[str]:
    """Non-raising readiness check, reused by activate() and by the UI to
    show a live checklist before the user even attempts to activate.

    A workflow must have exactly one start step, at least one end step, and
    every step must be reachable from the start -- otherwise a document
    could get stuck on a step nothing routes into, or the workflow could
    never signal completion.
    """
    if not definition.steps:
        return ["Add at least one step."]

    issues: list[str] = []
    initial_steps = [step for step in definition.steps if step.is_initial]
    terminal_steps = [step for step in definition.steps if step.is_terminal]

    if len(initial_steps) == 0:
        issues.append("Mark one step as the start step.")
    elif len(initial_steps) > 1:
        issues.append("Only one step can be the start step.")

    if len(terminal_steps) == 0:
        issues.append("Mark at least one step as an end step.")

    if len(initial_steps) == 1:
        reachable = {initial_steps[0].key}
        frontier = [initial_steps[0].key]
        while frontier:
            current = frontier.pop()
            for transition in definition.transitions_from(current):
                if transition.to_step_key not in reachable:
                    reachable.add(transition.to_step_key)
                    frontier.append(transition.to_step_key)

        all_keys = {step.key for step in definition.steps}
        unreachable = sorted(all_keys - reachable)
        if unreachable:
            issues.append(f"These steps can't be reached from the start yet: {', '.join(unreachable)}.")

    return issues


def validate_workflow_graph(definition: "WorkflowDefinition") -> None:
    issues = find_validation_issues(definition)
    if issues:
        raise WorkflowValidationError(" ".join(issues))

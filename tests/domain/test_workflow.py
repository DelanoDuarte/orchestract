import pytest

from app.domain.documents.exceptions import EmptyDocumentTitleError
from app.domain.documents.models import Document
from app.domain.workflow.exceptions import (
    AmbiguousTransitionError,
    DuplicateStepKeyError,
    MultipleInitialStepsError,
    UnknownStepError,
    WorkflowDefinitionLockedError,
    WorkflowValidationError,
)
from app.domain.workflow.models import WorkflowDefinition
from app.domain.workflow.validation import find_validation_issues
from app.domain.workflow_instances.exceptions import (
    InactiveWorkflowError,
    InvalidTransitionError,
    WorkflowAlreadyCompletedError,
)
from app.domain.workflow_instances.models import InstanceStatus, WorkflowInstance

AGENT_A, AGENT_B, AGENT_C = 1, 2, 3


def build_linear_definition() -> WorkflowDefinition:
    definition = WorkflowDefinition.create(organization_id=1, name="Simple Lifecycle")
    definition.add_step("draft", "Draft", AGENT_A, is_initial=True)
    definition.add_step("negotiate", "Negotiate", AGENT_B)
    definition.add_step("sign", "Sign", AGENT_C, is_terminal=True)
    definition.add_transition("draft", "negotiate", "send_for_negotiation")
    definition.add_transition("negotiate", "sign", "approve")
    definition.add_transition("negotiate", "draft", "request_changes")
    return definition


def test_add_step_rejects_duplicate_key():
    definition = build_linear_definition()
    with pytest.raises(DuplicateStepKeyError):
        definition.add_step("draft", "Another Draft", AGENT_A)


def test_add_step_rejects_second_initial_step():
    definition = build_linear_definition()
    with pytest.raises(MultipleInitialStepsError):
        definition.add_step("extra", "Extra", AGENT_A, is_initial=True)


def test_add_transition_rejects_unknown_step():
    definition = build_linear_definition()
    with pytest.raises(UnknownStepError):
        definition.add_transition("draft", "nonexistent", "go")


def test_add_transition_rejects_ambiguous_action():
    definition = build_linear_definition()
    with pytest.raises(AmbiguousTransitionError):
        definition.add_transition("draft", "sign", "send_for_negotiation")


def test_activate_requires_initial_step():
    definition = WorkflowDefinition.create(organization_id=1, name="No Initial")
    definition.add_step("only", "Only", AGENT_A, is_terminal=True)
    with pytest.raises(WorkflowValidationError):
        definition.activate()


def test_activate_requires_all_steps_reachable():
    definition = build_linear_definition()
    definition.add_step("orphan", "Orphan", AGENT_A)
    with pytest.raises(WorkflowValidationError):
        definition.activate()


def test_activate_requires_a_terminal_step():
    definition = WorkflowDefinition.create(organization_id=1, name="No End")
    definition.add_step("only", "Only", AGENT_A, is_initial=True)
    with pytest.raises(WorkflowValidationError):
        definition.activate()


def test_find_validation_issues_reports_specific_problems():
    definition = WorkflowDefinition.create(organization_id=1, name="Incomplete")
    assert find_validation_issues(definition) == ["Add at least one step."]

    definition.add_step("draft", "Draft", AGENT_A)
    issues = find_validation_issues(definition)
    assert "Mark one step as the start step." in issues
    assert "Mark at least one step as an end step." in issues

    definition_with_orphan = WorkflowDefinition.create(organization_id=1, name="Has Orphan")
    definition_with_orphan.add_step("draft", "Draft", AGENT_A, is_initial=True, is_terminal=True)
    definition_with_orphan.add_step("orphan", "Orphan", AGENT_B)
    issues = find_validation_issues(definition_with_orphan)
    assert any("orphan" in issue for issue in issues)

    assert find_validation_issues(build_linear_definition()) == []


def test_activate_succeeds_and_locks_further_edits():
    definition = build_linear_definition()
    definition.activate()
    assert definition.status.value == "active"
    with pytest.raises(WorkflowDefinitionLockedError):
        definition.add_step("late", "Late", AGENT_A)


def test_instance_cannot_start_on_inactive_definition():
    definition = build_linear_definition()
    with pytest.raises(InactiveWorkflowError):
        WorkflowInstance.start(document_id=1, definition=definition, actor="alice")


def test_instance_lifecycle_transitions_and_completes():
    definition = build_linear_definition()
    definition.activate()
    instance = WorkflowInstance.start(document_id=1, definition=definition, actor="alice")
    assert instance.current_step_key == "draft"
    assert len(instance.history) == 1

    with pytest.raises(InvalidTransitionError):
        instance.apply_transition(definition, "approve", actor="bob")

    instance.apply_transition(definition, "send_for_negotiation", actor="bob")
    assert instance.current_step_key == "negotiate"

    instance.apply_transition(definition, "approve", actor="carol", comment="looks good")
    assert instance.current_step_key == "sign"
    assert instance.status == InstanceStatus.COMPLETED
    assert instance.completed_at is not None

    with pytest.raises(WorkflowAlreadyCompletedError):
        instance.apply_transition(definition, "approve", actor="carol")


def test_document_requires_non_empty_title():
    with pytest.raises(EmptyDocumentTitleError):
        Document.create(organization_id=1, title="   ", document_type="NDA")


def test_document_add_version_increments_version_number():
    document = Document.create(organization_id=1, title="MSA", document_type="MSA")
    assert document.current_version_no == 0
    v1 = document.add_version("s3://bucket/v1.pdf", uploaded_by="alice")
    v2 = document.add_version("s3://bucket/v2.pdf", uploaded_by="bob", notes="fixed typo")
    assert v1.version_no == 1
    assert v2.version_no == 2
    assert document.current_version_no == 2
    assert document.latest_version() is v2

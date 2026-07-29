import enum
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.shared.base import Base
from app.domain.shared.types import slugify, utcnow
from app.domain.workflow.exceptions import (
    AmbiguousTransitionError,
    DuplicateStepKeyError,
    EmptyWorkflowNameError,
    MultipleInitialStepsError,
    UnknownStepError,
    WorkflowDefinitionLockedError,
    WorkflowValidationError,
)


class WorkflowStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class WorkflowStep(Base):
    """A node in a workflow graph, owned by the WorkflowDefinition aggregate."""

    __tablename__ = "workflow_steps"
    __table_args__ = (UniqueConstraint("workflow_definition_id", "key", name="uq_step_def_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_definition_id: Mapped[int] = mapped_column(ForeignKey("workflow_definitions.id"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))
    is_initial: Mapped[bool] = mapped_column(default=False)
    is_terminal: Mapped[bool] = mapped_column(default=False)

    definition: Mapped["WorkflowDefinition"] = relationship(back_populates="steps")


class WorkflowTransition(Base):
    """A directed edge between two steps of the same WorkflowDefinition, keyed by an action name."""

    __tablename__ = "workflow_transitions"
    __table_args__ = (
        UniqueConstraint("workflow_definition_id", "from_step_key", "action_name", name="uq_transition_action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_definition_id: Mapped[int] = mapped_column(ForeignKey("workflow_definitions.id"), index=True)
    from_step_key: Mapped[str] = mapped_column(String(80))
    to_step_key: Mapped[str] = mapped_column(String(80))
    action_name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    definition: Mapped["WorkflowDefinition"] = relationship(back_populates="transitions")


class WorkflowDefinition(Base):
    """Aggregate root for a customizable document workflow graph.

    Steps and transitions are entities of this aggregate and must only be
    mutated through its methods, which enforce the invariants: unique step
    keys, exactly one initial step, no ambiguous (same from-step/action)
    transitions, and structural edits are locked once the definition is
    activated.
    """

    __tablename__ = "workflow_definitions"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_workflow_org_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    steps: Mapped[list[WorkflowStep]] = relationship(
        back_populates="definition",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.id",
        lazy="selectin",
    )
    transitions: Mapped[list[WorkflowTransition]] = relationship(
        back_populates="definition",
        cascade="all, delete-orphan",
        order_by="WorkflowTransition.id",
        lazy="selectin",
    )

    @classmethod
    def create(cls, organization_id: int, name: str, description: str | None = None) -> "WorkflowDefinition":
        name = name.strip()
        if not name:
            raise EmptyWorkflowNameError()
        return cls(
            organization_id=organization_id,
            name=name,
            slug=slugify(name),
            description=description,
            status=WorkflowStatus.DRAFT,
        )

    def rename(self, new_name: str) -> None:
        """Renames the workflow. Name/description are metadata, so (unlike the
        graph) they stay editable in any status -- only structural edits are
        locked once activated."""
        new_name = new_name.strip()
        if not new_name:
            raise EmptyWorkflowNameError()
        self.name = new_name
        self.slug = slugify(new_name)

    def set_description(self, description: str | None) -> None:
        self.description = description

    def _require_draft(self) -> None:
        if self.status != WorkflowStatus.DRAFT:
            raise WorkflowDefinitionLockedError(self.id)

    def get_step(self, key: str) -> WorkflowStep:
        for step in self.steps:
            if step.key == key:
                return step
        raise UnknownStepError(key)

    def add_step(
        self,
        key: str,
        name: str,
        agent_id: int,
        description: str | None = None,
        is_initial: bool = False,
        is_terminal: bool = False,
    ) -> WorkflowStep:
        self._require_draft()
        if any(step.key == key for step in self.steps):
            raise DuplicateStepKeyError(key)
        if is_initial and any(step.is_initial for step in self.steps):
            raise MultipleInitialStepsError()
        step = WorkflowStep(
            key=key,
            name=name,
            description=description,
            agent_id=agent_id,
            is_initial=is_initial,
            is_terminal=is_terminal,
        )
        self.steps.append(step)
        return step

    def add_transition(
        self, from_key: str, to_key: str, action_name: str, description: str | None = None
    ) -> WorkflowTransition:
        self._require_draft()
        self.get_step(from_key)
        self.get_step(to_key)
        if any(t.from_step_key == from_key and t.action_name == action_name for t in self.transitions):
            raise AmbiguousTransitionError(from_key, action_name)
        transition = WorkflowTransition(
            from_step_key=from_key, to_step_key=to_key, action_name=action_name, description=description
        )
        self.transitions.append(transition)
        return transition

    def transitions_from(self, step_key: str) -> list[WorkflowTransition]:
        return [t for t in self.transitions if t.from_step_key == step_key]

    def find_transition(self, step_key: str, action_name: str) -> WorkflowTransition | None:
        for transition in self.transitions_from(step_key):
            if transition.action_name == action_name:
                return transition
        return None

    def initial_step(self) -> WorkflowStep:
        for step in self.steps:
            if step.is_initial:
                return step
        raise WorkflowValidationError("workflow has no initial step")

    def activate(self) -> None:
        self._require_draft()
        from app.domain.workflow.validation import validate_workflow_graph

        validate_workflow_graph(self)
        self.status = WorkflowStatus.ACTIVE

    def retire(self) -> None:
        if self.status != WorkflowStatus.ACTIVE:
            raise WorkflowDefinitionLockedError(self.id)
        self.status = WorkflowStatus.RETIRED

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.shared.base import Base
from app.domain.shared.types import utcnow
from app.domain.workflow.models import WorkflowStatus
from app.domain.workflow_instances.exceptions import (
    InactiveWorkflowError,
    InvalidTransitionError,
    WorkflowAlreadyCompletedError,
)

if TYPE_CHECKING:
    from app.domain.workflow.models import WorkflowDefinition


class InstanceStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


class WorkflowHistoryEntry(Base):
    """An audit trail entry recording one step change of a WorkflowInstance."""

    __tablename__ = "workflow_history_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_instance_id: Mapped[int] = mapped_column(ForeignKey("workflow_instances.id"), index=True)
    from_step_key: Mapped[str | None] = mapped_column(String(80), default=None)
    to_step_key: Mapped[str] = mapped_column(String(80))
    action_name: Mapped[str | None] = mapped_column(String(80), default=None)
    actor: Mapped[str] = mapped_column(String(200))
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow)

    instance: Mapped["WorkflowInstance"] = relationship(back_populates="history")


class WorkflowInstance(Base):
    """Aggregate root tracking one document's live run through a WorkflowDefinition.

    References `document_id` and `workflow_definition_id` by id only (not by
    relationship) so this aggregate stays independent of the Document and
    WorkflowDefinition aggregates, per DDD aggregate boundaries.
    """

    __tablename__ = "workflow_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    workflow_definition_id: Mapped[int] = mapped_column(ForeignKey("workflow_definitions.id"), index=True)
    current_step_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[InstanceStatus] = mapped_column(Enum(InstanceStatus), default=InstanceStatus.ACTIVE)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    history: Mapped[list[WorkflowHistoryEntry]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="WorkflowHistoryEntry.occurred_at",
        lazy="selectin",
    )

    @classmethod
    def start(cls, document_id: int, definition: "WorkflowDefinition", actor: str) -> "WorkflowInstance":
        if definition.status != WorkflowStatus.ACTIVE:
            raise InactiveWorkflowError(definition.id)
        initial = definition.initial_step()
        instance = cls(
            document_id=document_id,
            workflow_definition_id=definition.id,
            current_step_key=initial.key,
            status=InstanceStatus.ACTIVE,
        )
        instance.history.append(
            WorkflowHistoryEntry(
                from_step_key=None,
                to_step_key=initial.key,
                action_name=None,
                actor=actor,
                comment="workflow started",
            )
        )
        return instance

    def available_actions(self, definition: "WorkflowDefinition") -> list:
        if self.status != InstanceStatus.ACTIVE:
            return []
        return definition.transitions_from(self.current_step_key)

    def apply_transition(
        self,
        definition: "WorkflowDefinition",
        action_name: str,
        actor: str,
        comment: str | None = None,
    ) -> None:
        if self.status != InstanceStatus.ACTIVE:
            raise WorkflowAlreadyCompletedError(self.id)
        transition = definition.find_transition(self.current_step_key, action_name)
        if transition is None:
            raise InvalidTransitionError(self.current_step_key, action_name)
        target_step = definition.get_step(transition.to_step_key)
        self.history.append(
            WorkflowHistoryEntry(
                from_step_key=self.current_step_key,
                to_step_key=target_step.key,
                action_name=action_name,
                actor=actor,
                comment=comment,
            )
        )
        self.current_step_key = target_step.key
        if target_step.is_terminal:
            self.status = InstanceStatus.COMPLETED
            self.completed_at = utcnow()

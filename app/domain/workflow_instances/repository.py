from typing import Protocol

from app.domain.workflow_instances.models import WorkflowInstance


class WorkflowInstanceRepository(Protocol):
    async def add(self, instance: WorkflowInstance) -> None: ...

    async def get(self, instance_id: int) -> WorkflowInstance | None: ...

    async def get_for_document(self, document_id: int) -> WorkflowInstance | None: ...

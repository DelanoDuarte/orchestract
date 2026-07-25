from app.domain.shared.exceptions import ConflictError


class InactiveWorkflowError(ConflictError):
    def __init__(self, definition_id: int | None) -> None:
        super().__init__(f"workflow definition {definition_id} is not active and cannot be started")
        self.definition_id = definition_id


class InvalidTransitionError(ConflictError):
    def __init__(self, step_key: str, action_name: str) -> None:
        super().__init__(f"no transition '{action_name}' is available from step '{step_key}'")
        self.step_key = step_key
        self.action_name = action_name


class WorkflowAlreadyCompletedError(ConflictError):
    def __init__(self, instance_id: int | None) -> None:
        super().__init__(f"workflow instance {instance_id} has already completed")
        self.instance_id = instance_id

from app.domain.shared.exceptions import ConflictError, DomainError


class EmptyWorkflowNameError(DomainError):
    def __init__(self) -> None:
        super().__init__("workflow name must not be empty")


class DuplicateStepKeyError(DomainError):
    def __init__(self, key: str) -> None:
        super().__init__(f"step key '{key}' already exists in this workflow")
        self.key = key


class UnknownStepError(DomainError):
    def __init__(self, key: str) -> None:
        super().__init__(f"unknown step key '{key}'")
        self.key = key


class MultipleInitialStepsError(DomainError):
    def __init__(self) -> None:
        super().__init__("workflow already has an initial step")


class AmbiguousTransitionError(DomainError):
    def __init__(self, from_key: str, action_name: str) -> None:
        super().__init__(f"transition '{action_name}' from step '{from_key}' is already defined")
        self.from_key = from_key
        self.action_name = action_name


class WorkflowDefinitionLockedError(ConflictError):
    def __init__(self, definition_id: int | None) -> None:
        super().__init__(f"workflow definition {definition_id} is not editable in its current status")
        self.definition_id = definition_id


class WorkflowValidationError(DomainError):
    pass

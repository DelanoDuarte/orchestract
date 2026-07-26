from app.domain.shared.exceptions import ConflictError, DomainError


class EmptyRoleNameError(DomainError):
    def __init__(self) -> None:
        super().__init__("role name must not be empty")


class EmptyUserNameError(DomainError):
    def __init__(self) -> None:
        super().__init__("user name must not be empty")


class EmptyUserEmailError(DomainError):
    def __init__(self) -> None:
        super().__init__("user email must not be empty")


class DuplicateRoleNameError(ConflictError):
    def __init__(self, name: str) -> None:
        super().__init__(f"a role named '{name}' already exists in this organization")


class DuplicateEmailError(ConflictError):
    def __init__(self, email: str) -> None:
        super().__init__(f"a user with email '{email}' already exists")


class InvalidCredentialsError(DomainError):
    def __init__(self) -> None:
        super().__init__("incorrect email or password")


class PermissionDeniedError(DomainError):
    def __init__(self, message: str = "you do not have permission to perform this action") -> None:
        super().__init__(message)

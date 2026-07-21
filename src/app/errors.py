class AppError(RuntimeError):
    """Base error raised by the game application."""


class CommandError(AppError):
    """Raised when a command request is structurally invalid or not allowed."""


class UnknownCommandError(CommandError):
    """Raised when a command name is not part of the game command set."""


class MapError(AppError):
    """Raised when a map definition is invalid."""


class StateError(AppError):
    """Raised when a state machine is asked for a transition it does not allow."""

"""Errors raised while parsing or validating preBF programs."""


class PreBFError(Exception):
    """A user-facing source error with an optional line number."""

    def __init__(self, message: str, line: int | None = None) -> None:
        self.message = message
        self.line = line
        prefix = f"Строка {line}: " if line is not None else ""
        super().__init__(prefix + message)

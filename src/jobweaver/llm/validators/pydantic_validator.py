from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class SchemaValidator(Protocol):
    def validate(self, data: dict[str, Any]) -> BaseModel: ...


class PydanticValidator:
    """Validate dict payloads against a Pydantic model."""

    def __init__(self, model: type[BaseModel]) -> None:
        self._model = model

    def validate(self, data: dict[str, Any]) -> BaseModel:
        return self._model.model_validate(data)

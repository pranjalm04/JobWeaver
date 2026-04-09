from __future__ import annotations

from pydantic import BaseModel

from physicianx.llm.validators.pydantic_validator import PydanticValidator, SchemaValidator

_REGISTRY: dict[type[BaseModel], SchemaValidator] = {}


def register_model(model: type[BaseModel], validator: SchemaValidator) -> None:
    """Register a validator for an output schema (one per Pydantic model class)."""

    _REGISTRY[model] = validator


def validator_for(model: type[BaseModel]) -> SchemaValidator:
    """Return the validator for a registered schema, or raise KeyError."""

    try:
        return _REGISTRY[model]
    except KeyError as e:
        raise KeyError(f"No SchemaValidator registered for {model.__name__}") from e

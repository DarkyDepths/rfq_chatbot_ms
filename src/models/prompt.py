"""Prompt assembly contract for future context building."""

from pydantic import BaseModel, ConfigDict, Field


class PromptEnvelope(BaseModel):
    """Stable prompt structure used by later chat phases."""

    model_config = ConfigDict(extra="forbid")

    stable_prefix: str
    variable_suffix: str
    total_budget: int = Field(ge=1)

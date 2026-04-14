"""Turn request and response DTOs for future chat routes."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from src.models.envelope import SourceRef


class TurnRequest(BaseModel):
    """Minimal turn input contract."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)


class TurnResponse(BaseModel):
    """Minimal turn output contract."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: uuid.UUID
    turn_number: int = Field(ge=1)
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_refs: list[SourceRef] = Field(default_factory=list)

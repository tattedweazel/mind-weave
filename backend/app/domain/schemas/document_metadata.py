"""Document metadata schema for the SPA's Manage Documents → Metadata tab."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentMetadata(BaseModel):
    """
    Derived size statistics + identity fields for a Document.

    Returned by ``GET /api/v1/documents/{id}/metadata``. Token counts are an
    *estimate* against ``tokenizer`` (currently ``o200k_base``, the GPT-4o
    family). The frontend surfaces this honestly so users understand local
    LM Studio models may diverge slightly.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

    token_count: int
    character_count: int
    word_count: int
    line_count: int

    tokenizer: str

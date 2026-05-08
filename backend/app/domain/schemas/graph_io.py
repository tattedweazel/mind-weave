"""Start/stop handle metadata."""

from typing import Any, Literal, Optional

from pydantic import BaseModel


class RequiredInput(BaseModel):
    """A required input slot on the Start node. key is the handle ID for wiring."""

    key: str
    type: Literal["string", "list", "dictionary", "structure", "document", "boolean", "int", "datetime", "gmail", "any"]
    value: Optional[Any] = None  # null = prompt at run time


class RequiredOutput(BaseModel):
    """Expected output slot on the Stop node. key is the handle ID for wiring."""

    key: str
    type: Literal[
        "string",
        "list",
        "dictionary",
        "structure",
        "document",
        "boolean",
        "int",
        "datetime",
        "gmail",
        "audio",
        "any",
    ]

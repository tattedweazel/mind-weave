"""
Default Personas
================
System-level Persona definitions seeded into the database on first startup.
"""

from enum import Enum


class DefaultPersonas(Enum):
    """System personas that are created on startup if they don't exist."""

    DEFAULT = {
        "name": "default",
        "description": "A helpful general-purpose assistant.",
        "system_prompt": "You are a helpful, concise, and professional assistant.",
        "is_default": True,
        "type": "system",
    }

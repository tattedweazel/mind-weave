"""
Document Service
================
CRUD operations for Documents, scoped to the requesting user.
System-level documents (user_id=None) are visible to all users.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from sqlmodel import Session, or_, select

from app.domain.document_json import (
    deterministic_json_dumps,
    merge_json_objects,
    parse_json_object_strict,
)
from app.domain.schemas.documents import DocumentCreate, DocumentUpdate
from app.persistence.tables import Document

_DOCUMENT_APPEND_SEPARATOR = "\n\n"
WriteMode = Literal["replace", "append", "merge_json"]


class DocumentService:
    """Scoped CRUD service for Documents."""

    def __init__(self, session: Session, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.user_id = user_id

    def get_document(self, id: uuid.UUID) -> Optional[Document]:
        """Return a Document by ID (user-owned or system-level)."""
        return self.session.exec(
            select(Document).where(
                Document.id == id,
                or_(Document.user_id == self.user_id, Document.user_id == None),  # noqa: E711
            )
        ).first()

    def get_document_by_name(self, name: str) -> Optional[Document]:
        """Return a Document by name (user-owned or system-level)."""
        return self.session.exec(
            select(Document).where(
                Document.name == name,
                or_(Document.user_id == self.user_id, Document.user_id == None),  # noqa: E711
            )
        ).first()

    def list_documents(self) -> List[Document]:
        """Return all Documents visible to this user."""
        return list(
            self.session.exec(
                select(Document).where(
                    or_(Document.user_id == self.user_id, Document.user_id == None)  # noqa: E711
                )
            ).all()
        )

    def create_document(self, data: DocumentCreate) -> Document:
        """Create and persist a new Document owned by this user."""
        document = Document(**data.model_dump(), user_id=self.user_id)
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def update_document(self, id: uuid.UUID, data: DocumentUpdate) -> Optional[Document]:
        """Update a user-owned Document. System documents cannot be updated."""
        document = self.get_document(id)
        if not document or document.user_id != self.user_id:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(document, key, value)
        document.updated_at = datetime.now(timezone.utc)

        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def delete_document(self, id: uuid.UUID) -> bool:
        """Delete a user-owned Document. System documents cannot be deleted."""
        document = self.get_document(id)
        if not document or document.user_id != self.user_id:
            return False
        self.session.delete(document)
        self.session.commit()
        return True

    def upsert_document(
        self,
        *,
        name: str,
        content: str,
        existing_document_id: Optional[uuid.UUID] = None,
        write_mode: WriteMode = "replace",
    ) -> Document:
        """
        Create or update a user-owned document. System documents cannot be mutated.

        write_mode:
        - replace: set body to content
        - append: append content after body with a blank line between
        - merge_json: both existing body (if any) and content must parse as JSON objects;
          deep-merge with incoming keys winning; body is stored as deterministic JSON text.
        """
        if not name or not str(name).strip():
            raise ValueError("Document upsert: name is required")
        if self.user_id is None:
            raise ValueError("Document upsert requires an authenticated user")

        def _compute_body(old_body: str) -> str:
            if write_mode == "replace":
                return content
            if write_mode == "append":
                if not old_body:
                    return content
                return old_body + _DOCUMENT_APPEND_SEPARATOR + content
            # merge_json
            old_obj = parse_json_object_strict(old_body, what="Existing document body")
            inc_obj = parse_json_object_strict(content, what="merge_json content")
            merged = merge_json_objects(old_obj, inc_obj)
            return deterministic_json_dumps(merged)

        if existing_document_id is not None:
            document = self.get_document(existing_document_id)
            if not document:
                raise ValueError("Document upsert: document not found or not visible")
            if document.user_id != self.user_id:
                raise ValueError("Document upsert: cannot modify system or other users' documents")
            new_body = _compute_body(document.body or "")
            updated = self.update_document(
                existing_document_id,
                DocumentUpdate(body=new_body),
            )
            assert updated is not None
            return updated

        existing = self.get_document_by_name(name.strip())
        if existing is None:
            if write_mode == "replace":
                body = content
            elif write_mode == "append":
                body = content
            else:
                inc = parse_json_object_strict(content, what="merge_json content")
                body = deterministic_json_dumps(inc)
            return self.create_document(
                DocumentCreate(name=name.strip(), description="", body=body),
            )

        if existing.user_id != self.user_id:
            raise ValueError(
                "Document upsert: a system document with this name exists; choose another name",
            )

        new_body = _compute_body(existing.body or "")
        updated = self.update_document(existing.id, DocumentUpdate(body=new_body))
        assert updated is not None
        return updated

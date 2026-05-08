"""
Documents API
=============
CRUD endpoints for Documents.

  GET    /api/v1/documents/             — list all Documents visible to the current user
  POST   /api/v1/documents/             — create a Document
  GET    /api/v1/documents/{id}         — get by ID
  GET    /api/v1/documents/{id}/metadata — derived stats (token / char / word / line counts)
  PUT    /api/v1/documents/{id}         — update
  DELETE /api/v1/documents/{id}         — delete (user-owned only)
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.schemas.document_metadata import DocumentMetadata
from app.domain.schemas.documents import DocumentCreate, DocumentListItem, DocumentUpdate
from app.domain.services.document_metadata_service import (
    TOKENIZER_NAME,
    compute_document_metadata,
)
from app.domain.services.document_service import DocumentService
from app.persistence.db import get_session
from app.persistence.tables import Document, User

router = APIRouter()


@router.get("/", response_model=List[DocumentListItem])
def list_documents(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return all Documents visible to the current user (slim, without body)."""
    return DocumentService(session, current_user.id).list_documents()


@router.post("/", response_model=Document, status_code=status.HTTP_201_CREATED)
def create_document(
    data: DocumentCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new Document. Name must be unique."""
    svc = DocumentService(session, current_user.id)
    if svc.get_document_by_name(data.name):
        raise HTTPException(status_code=400, detail="A Document with that name already exists.")
    return svc.create_document(data)


@router.get("/{id}", response_model=Document)
def get_document(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a single Document by ID."""
    document = DocumentService(session, current_user.id).get_document(id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.get("/{id}/metadata", response_model=DocumentMetadata)
def get_document_metadata(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Derived size statistics for a Document body.

    Surfaced in the SPA's **Manage Documents → Metadata** tab. Token counts
    are estimated against the GPT-4o family encoding (``o200k_base``); local
    LM Studio models may use a different tokenizer.
    """
    document = DocumentService(session, current_user.id).get_document(id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    stats = compute_document_metadata(document.body or "")
    return DocumentMetadata(
        id=document.id,
        name=document.name,
        created_at=document.created_at,
        updated_at=document.updated_at,
        token_count=stats.token_count,
        character_count=stats.character_count,
        word_count=stats.word_count,
        line_count=stats.line_count,
        tokenizer=TOKENIZER_NAME,
    )


@router.put("/{id}", response_model=Document)
def update_document(
    id: uuid.UUID,
    data: DocumentUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update a user-owned Document."""
    svc = DocumentService(session, current_user.id)
    if data.name:
        existing = svc.get_document_by_name(data.name)
        if existing and existing.id != id:
            raise HTTPException(status_code=400, detail="A Document with that name already exists.")
    document = svc.update_document(id, data)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a user-owned Document."""
    success = DocumentService(session, current_user.id).delete_document(id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found.")

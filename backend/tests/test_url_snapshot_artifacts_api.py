"""URL snapshot artifact GET (auth-scoped)."""

from __future__ import annotations

import base64

from sqlmodel import Session, select

from app.persistence.tables import UrlSnapshotArtifact, User

_MIN_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+lmfkAAAAASUVORK5CYII="
)


def test_get_url_snapshot_artifact_404_when_missing(client, db_session: Session):
    import uuid

    r = client.get(f"/api/v1/url-snapshot-artifacts/{uuid.uuid4()}")
    assert r.status_code == 404


def test_get_url_snapshot_artifact_returns_png(client, db_session: Session):
    u = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert u is not None
    art = UrlSnapshotArtifact(
        user_id=u.id,
        image_bytes=_MIN_PNG,
        mime_type="image/png",
        width=1,
        height=1,
        final_url="https://example.com/",
    )
    db_session.add(art)
    db_session.commit()
    db_session.refresh(art)

    r = client.get(f"/api/v1/url-snapshot-artifacts/{art.id}")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")
    assert r.content == _MIN_PNG


def test_post_url_snapshot_artifact_creates_row(client, db_session: Session):
    u = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert u is not None
    before = len(db_session.exec(select(UrlSnapshotArtifact).where(UrlSnapshotArtifact.user_id == u.id)).all())
    files = {"file": ("t.png", _MIN_PNG, "image/png")}
    r = client.post("/api/v1/url-snapshot-artifacts", files=files)
    assert r.status_code == 200
    j = r.json()
    assert "artifact_id" in j
    assert j["mime_type"] == "image/png"
    assert j["width"] == 1
    assert j["height"] == 1
    after = len(db_session.exec(select(UrlSnapshotArtifact).where(UrlSnapshotArtifact.user_id == u.id)).all())
    assert after == before + 1


def test_post_url_snapshot_artifact_rejects_garbage(client, db_session: Session):
    files = {"file": ("x.bin", b"not an image", "application/octet-stream")}
    r = client.post("/api/v1/url-snapshot-artifacts", files=files)
    assert r.status_code == 400

"""Test altyapisi.

Testler AYRI bir veritabaninda calisir (`agency_cortex_test`). Gelistirme
veya uretim verisi asla test tarafindan ezilmez.

Her test kendi islemi (transaction) icinde calisir ve sonunda geri alinir;
boylece testler birbirini etkilemez.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

# GUVENLIK: Test veritabani ZORLA ayarlanir, `setdefault` ile DEGIL.
#
# `setdefault` kullanilsaydi, kabukta POSTGRES_DB tanimliysa testler o
# veritabanina baglanirdi. Gelistirme veya URETIM veritabaninda test
# calistirmak, testlerin veriyi silmesi anlamina gelir.
#
# Bu satirlar uygulama import edilmeden ONCE calismalidir.
os.environ["APP_ENV"] = "development"
os.environ["POSTGRES_DB"] = os.environ.get("POSTGRES_TEST_DB", "agency_cortex_test")
os.environ["SECRET_KEY"] = "test-secret-anahtari"
os.environ["ENCRYPTION_KEY"] = "test-sifreleme-anahtari"
# Baglanti bilgileri disaridan verilebilir (CI icin), veritabani ADI verilemez.
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "agency")
os.environ.setdefault("POSTGRES_PASSWORD", "dev-parola")
os.environ.setdefault("REDIS_HOST", "localhost")

# Son kontrol: veritabani adi "_test" ile bitmiyorsa HICBIR SEY calistirilmaz.
if not os.environ["POSTGRES_DB"].endswith("_test"):
    raise RuntimeError(
        "Testler yalnizca adi '_test' ile biten bir veritabaninda calisabilir. "
        f"Verilen: {os.environ['POSTGRES_DB']}"
    )

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

import app.models  # noqa: F401,E402  - tablolarin kayit olmasi icin
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, get_db  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.enums import WorkspaceRole  # noqa: E402
from app.models.identity import User, Workspace, WorkspaceMember  # noqa: E402

_engine = create_engine(get_settings().database_url, future=True)


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Iterator[None]:
    Base.metadata.create_all(_engine)
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    """Her test icin geri alinabilir bir oturum."""
    connection = _engine.connect()
    transaction = connection.begin()
    # join_transaction_mode="create_savepoint": uctaki db.commit() veya
    # db.rollback() cagrilari dis islemi bozmaz; SAVEPOINT uzerinden calisir.
    # Bu olmadan, hata yolunu deneyen bir test veritabaninda kalinti birakir.
    session = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()   # Testin yazdigi her sey silinir
        connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """Uygulamayi test veritabanina bagli olarak calistirir."""
    fastapi_app.dependency_overrides[get_db] = lambda: db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test verisi uretecleri
# ---------------------------------------------------------------------------

@pytest.fixture
def make_user(db: Session):
    def _make(email: str | None = None, password: str = "GucluSifre123!") -> User:
        user = User(
            email=email or f"kullanici-{uuid.uuid4().hex[:8]}@ornek.com",
            full_name="Test Kullanicisi",
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture
def make_workspace(db: Session):
    def _make(name: str = "Test Musterisi") -> Workspace:
        ws = Workspace(name=name, slug=f"musteri-{uuid.uuid4().hex[:8]}")
        db.add(ws)
        db.flush()
        return ws

    return _make


@pytest.fixture
def add_member(db: Session):
    def _add(workspace: Workspace, user: User, role: WorkspaceRole) -> WorkspaceMember:
        member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role)
        db.add(member)
        db.flush()
        return member

    return _add


@pytest.fixture
def auth_headers():
    """Bir kullanici adina istek yapmak icin baslik uretir."""

    def _headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}

    return _headers

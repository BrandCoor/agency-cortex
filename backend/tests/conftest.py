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
from pathlib import Path

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
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

import app.models  # noqa: F401,E402  - tablolarin kayit olmasi icin
from app.core.config import get_settings  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.enums import PermissionPackage, WorkspaceRole  # noqa: E402
from app.models.identity import User, Workspace, WorkspaceMember  # noqa: E402
from app.platforms import meta_ayar  # noqa: E402
from app.services import ai_butce  # noqa: E402

_engine = create_engine(get_settings().database_url, future=True)


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Iterator[None]:
    """Test semasini MIGRATION ile kurar.

    Neden `Base.metadata.create_all` degil:
    Uretimde sema migration'larla kurulur. Testler semayi baska bir yolla
    kurarsa, bozuk bir migration hicbir testte yakalanmaz ve hata ilk kez
    URETIMDE ortaya cikar. Migration'lari testlerin kendisi calistirinca,
    her test kosusunda migration zinciri de dogrulanmis olur.
    """
    from alembic.config import Config

    from alembic import command

    # Onceki kosudan kalan sema varsa tamamen temizlenir.
    with _engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    alembic_cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent.parent / "alembic"),
    )
    command.upgrade(alembic_cfg, "head")
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    """Her test icin geri alinabilir bir oturum."""
    connection = _engine.connect()
    transaction = connection.begin()
    # join_transaction_mode="create_savepoint": uctaki db.commit() veya
    # db.rollback() cagrilari dis islemi bozmaz; SAVEPOINT uzerinden calisir.
    # Bu olmadan, hata yolunu deneyen bir test veritabaninda kalinti birakir.
    oturum_uretici = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = oturum_uretici()

    # Butce rezervasyonu normalde AYRI bir baglantida, kisa bir islemde
    # yapilir. Testte veri henuz islenmedigi (commit edilmedigi) icin ayri
    # bir baglanti onu goremez; bu yuzden ayni baglantiya baglanir.
    # Esszamanlilik testi bunu KULLANMAZ, gercek ayri baglantilar acar.
    onceki_uretici = ai_butce.oturum_ureticiyi_ayarla(oturum_uretici)
    onceki_meta = meta_ayar.oturum_ureticiyi_ayarla(oturum_uretici)

    try:
        yield session
    finally:
        ai_butce.oturum_ureticiyi_ayarla(onceki_uretici)
        meta_ayar.oturum_ureticiyi_ayarla(onceki_meta)
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


#: Eski musteri rolu -> kullanici yetki paketi.
#
# Uyelik artik YETKI TASIMAZ. Testlerin cogu "bu kisi bu musteride
# editor" demek icin yazilmisti; yeni anlami "bu kisi editor".
_ROL_PAKET = {
    WorkspaceRole.OWNER: PermissionPackage.ADMIN,
    WorkspaceRole.ADMIN: PermissionPackage.ADMIN,
    WorkspaceRole.STRATEGIST: PermissionPackage.STRATEGIST,
    WorkspaceRole.EDITOR: PermissionPackage.EDITOR,
    WorkspaceRole.VIEWER: PermissionPackage.VIEWER,
}


@pytest.fixture
def add_member(db: Session):
    """Kullaniciyi musteriye atar ve yetki paketini ayarlar.

    Uyelik yalnizca ERISIMI belirler; ne yapabilecegi kullanicinin
    kendi paketinde/izinlerinde yazar.
    """
    def _add(workspace: Workspace, user: User, role=None) -> WorkspaceMember:
        if role is not None:
            user.permission_package = (
                role if isinstance(role, PermissionPackage) else _ROL_PAKET[role]
            )
        member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id)
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

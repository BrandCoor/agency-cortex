"""Zamanlanmis ve kuyruga alinan isler."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.db import check_database
from app.core.logging_config import get_logger
from app.core.redis_client import check_redis
from app.workers.celery_app import celery_app

log = get_logger("worker")


@celery_app.task(name="app.workers.tasks.heartbeat")
def heartbeat() -> dict:
    """Worker'in ayakta ve bagimliliklarina erisebildigini kanitlar.

    Bu is bilerek yan etkisizdir; istedigi kadar tekrar calistirilabilir.
    """
    db_ok, db_error = check_database()
    redis_ok, redis_error = check_redis()

    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "database_ok": db_ok,
        "redis_ok": redis_ok,
    }

    if db_ok and redis_ok:
        log.info("heartbeat_ok", **result)
    else:
        log.error("heartbeat_basarisiz", db_error=db_error, redis_error=redis_error, **result)

    return result


@celery_app.task(
    name="app.workers.tasks.sync_social_accounts",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,        # Her denemede bekleme suresi artar
    retry_backoff_max=600,
    retry_jitter=True,         # Tum isler ayni anda tekrar denemesin
)
def sync_social_accounts(self, workspace_id: str | None = None) -> dict:
    """Bagli sosyal medya hesaplarini senkronize eder.

    Tekrar calistirilabilir: ayni veri iki kez yazilmaz.
    `workspace_id` verilirse yalnizca o musteri islenir.
    """
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.social import SocialAccount
    from app.platforms.registry import get_adapter
    from app.services.sync import sync_social_account

    db = SessionLocal()
    ozet = {"hesap_sayisi": 0, "basarili": 0, "hatali": 0, "hatalar": []}
    try:
        sorgu = select(SocialAccount).where(SocialAccount.is_active.is_(True))
        if workspace_id:
            sorgu = sorgu.where(SocialAccount.workspace_id == workspace_id)

        for account in db.execute(sorgu).scalars():
            ozet["hesap_sayisi"] += 1
            try:
                adapter = get_adapter(account.platform)
                result = sync_social_account(db, account=account, adapter=adapter)
                db.commit()
                if result.errors:
                    ozet["hatali"] += 1
                    ozet["hatalar"].extend(result.errors)
                else:
                    ozet["basarili"] += 1
            except Exception as exc:  # noqa: BLE001 - bir hesabin hatasi digerlerini durdurmaz
                db.rollback()
                ozet["hatali"] += 1
                ozet["hatalar"].append(f"{account.id}: {type(exc).__name__}")
                log.exception("hesap_senkron_hatasi", social_account_id=str(account.id))

        log.info("senkron_tamamlandi", **{k: v for k, v in ozet.items() if k != "hatalar"})
        return ozet
    finally:
        db.close()

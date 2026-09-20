"""Sosyal medya verisinin cekilmesi ve normalize edilmesi.

TASARIM KURALI - IDEMPOTENT: Bu fonksiyonlar istendigi kadar tekrar
calistirilabilir. Ayni veri iki kez kaydedilmez, sayilar iki katina cikmaz.
Bir is yarida kalirsa yeniden calistirmak guvenlidir.

VERI AKISI:
  Platform API -> ham yanit (media_metrics_raw, degistirilmez)
               -> normalize olcum (media_metrics_normalized)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.social import (
    AccountMetrics,
    MediaMetricsNormalized,
    MediaMetricsRaw,
    PlatformMedia,
    SocialAccount,
)
from app.platforms.base import Capability, MetricPoint, PlatformAdapter
from app.services.token_store import load_tokens

log = get_logger("sync")


@dataclass
class SyncResult:
    """Bir senkronizasyonun sonucu. Rapor ve hata ayiklama icin."""

    media_seen: int = 0
    media_created: int = 0
    raw_stored: int = 0
    raw_skipped_duplicate: int = 0
    metrics_written: int = 0
    account_metrics_written: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def payload_hash(payload: dict) -> str:
    """Ham yanitin parmak izi.

    Ayni yanitin ikinci kez islenmesini engeller. Anahtarlar siralanir ki
    ayni icerik her zaman ayni izi uretsin.
    """
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _upsert_media(
    db: Session, *, account: SocialAccount, item, result: SyncResult
) -> PlatformMedia:
    """Icerigi kaydeder; zaten varsa gunceller (tekrar olusturmaz)."""
    existing = db.execute(
        select(PlatformMedia).where(
            PlatformMedia.workspace_id == account.workspace_id,
            PlatformMedia.platform == account.platform,
            PlatformMedia.external_id == item.external_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.caption = item.caption
        existing.permalink = item.permalink
        existing.published_at = item.published_at
        return existing

    media = PlatformMedia(
        workspace_id=account.workspace_id,
        social_account_id=account.id,
        platform=account.platform,
        external_id=item.external_id,
        media_type=item.media_type,
        caption=item.caption,
        permalink=item.permalink,
        published_at=item.published_at,
    )
    db.add(media)
    db.flush()
    result.media_created += 1
    return media


def _store_raw(
    db: Session,
    *,
    account: SocialAccount,
    media_id: uuid.UUID | None,
    points: list[MetricPoint],
    result: SyncResult,
) -> uuid.UUID | None:
    """Ham yaniti saklar. Ayni yanit daha once geldiyse tekrar yazmaz."""
    if not points:
        return None

    raw_payload = {"metrics": [p.raw for p in points]}
    digest = payload_hash(raw_payload)

    existing = db.execute(
        select(MediaMetricsRaw).where(
            MediaMetricsRaw.workspace_id == account.workspace_id,
            MediaMetricsRaw.payload_hash == digest,
        )
    ).scalar_one_or_none()

    if existing is not None:
        result.raw_skipped_duplicate += 1
        return existing.id

    raw = MediaMetricsRaw(
        workspace_id=account.workspace_id,
        media_id=media_id,
        platform=account.platform,
        source_endpoint=points[0].source_endpoint,
        fetched_at=datetime.now(UTC),
        raw_payload=raw_payload,
        payload_hash=digest,
    )
    db.add(raw)
    db.flush()
    result.raw_stored += 1
    return raw.id


def _write_normalized(
    db: Session,
    *,
    account: SocialAccount,
    media_id: uuid.UUID,
    raw_id: uuid.UUID | None,
    points: list[MetricPoint],
    result: SyncResult,
) -> None:
    """Normalize olcumleri yazar.

    Ayni olcum (ayni icerik + metrik + donem + zaman) ikinci kez gelirse
    yeni satir eklenmez, degeri guncellenir. Bu sayede is tekrar
    calistirildiginda sayilar sisirilmez.
    """
    now = datetime.now(UTC)
    for point in points:
        stmt = (
            pg_insert(MediaMetricsNormalized)
            .values(
                id=uuid.uuid4(),
                workspace_id=account.workspace_id,
                media_id=media_id,
                raw_reference_id=raw_id,
                platform=account.platform,
                metric_name=point.metric_name,
                metric_value=point.value,
                measurement_period=point.measurement_period,
                measured_at=point.measured_at,
                fetched_at=now,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_normalized_metric",
                set_={
                    "metric_value": point.value,
                    "raw_reference_id": raw_id,
                    "fetched_at": now,
                    "updated_at": now,
                },
            )
        )
        db.execute(stmt)
        result.metrics_written += 1


def _write_account_metrics(
    db: Session, *, account: SocialAccount, points: list[MetricPoint], result: SyncResult
) -> None:
    now = datetime.now(UTC)
    for point in points:
        stmt = (
            pg_insert(AccountMetrics)
            .values(
                id=uuid.uuid4(),
                workspace_id=account.workspace_id,
                social_account_id=account.id,
                platform=account.platform,
                metric_name=point.metric_name,
                metric_value=point.value,
                measurement_period=point.measurement_period,
                measured_at=point.measured_at,
                fetched_at=now,
                source_endpoint=point.source_endpoint,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_account_metric",
                set_={"metric_value": point.value, "fetched_at": now, "updated_at": now},
            )
        )
        db.execute(stmt)
        result.account_metrics_written += 1


def sync_social_account(
    db: Session, *, account: SocialAccount, adapter: PlatformAdapter, media_limit: int = 50
) -> SyncResult:
    """Bir hesabin icerik ve metriklerini ceker.

    Tekrar calistirilabilir: ayni veri iki kez yazilmaz.
    """
    result = SyncResult()

    tokens = load_tokens(
        db, workspace_id=account.workspace_id, social_account_id=account.id
    )
    if tokens is None:
        result.errors.append("Bu hesap icin kayitli erisim anahtari yok.")
        account.sync_error = result.errors[-1]
        return result

    # Yetenek bildirilmemisse veri cekilmeye calisilmaz; sahte sifir uretilmez.
    if not adapter.supports(Capability.LIST_MEDIA):
        result.errors.append(
            f"'{account.platform.value}' adaptoru icerik listelemeyi desteklemiyor."
        )
        account.sync_error = result.errors[-1]
        return result

    media_items = adapter.list_media(
        access_token=tokens.access_token,
        account_external_id=account.external_id,
        limit=media_limit,
    )
    result.media_seen = len(media_items)

    for item in media_items:
        media = _upsert_media(db, account=account, item=item, result=result)

        if not adapter.supports(Capability.FETCH_MEDIA_METRICS):
            continue

        points = adapter.fetch_media_metrics(
            access_token=tokens.access_token, media_external_id=item.external_id
        )
        raw_id = _store_raw(
            db, account=account, media_id=media.id, points=points, result=result
        )
        _write_normalized(
            db, account=account, media_id=media.id, raw_id=raw_id,
            points=points, result=result,
        )

    if adapter.supports(Capability.FETCH_ACCOUNT_METRICS):
        account_points = adapter.fetch_account_metrics(
            access_token=tokens.access_token, account_external_id=account.external_id
        )
        _write_account_metrics(db, account=account, points=account_points, result=result)

    account.last_synced_at = datetime.now(UTC)
    account.sync_error = None
    db.flush()

    log.info(
        "hesap_senkronize_edildi",
        workspace_id=str(account.workspace_id),
        social_account_id=str(account.id),
        media_seen=result.media_seen,
        media_created=result.media_created,
        raw_stored=result.raw_stored,
        raw_skipped_duplicate=result.raw_skipped_duplicate,
        metrics_written=result.metrics_written,
    )
    return result

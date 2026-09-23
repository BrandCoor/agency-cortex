"""Celery kuyruk ve zamanlayici yapilandirmasi.

Her is: zaman asimili, sinirli tekrar denemeli ve tekrar calistirilabilir
(idempotent) olmalidir. Bu dosya bu kurallari merkezi olarak uygular.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "agency_cortex",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    timezone=settings.tz,
    enable_utc=True,
    task_acks_late=True,            # Is bitmeden onay verilmez; worker cokerse is kaybolmaz
    task_reject_on_worker_lost=True,
    task_time_limit=900,            # 15 dakika: sert sinir
    task_soft_time_limit=840,       # 14 dakika: once nazik uyari
    task_default_retry_delay=60,
    task_max_retries=3,
    worker_prefetch_multiplier=1,   # Uzun isler icin adil dagitim
    worker_max_tasks_per_child=200, # Bellek sizintisina karsi periyodik yenileme
    result_expires=86400,
)

# Zamanlanmis isler. Aksamalar ayri asamalarda eklenecek; su an yalnizca
# sistemin kendi sagligini izleyen is aktif.
# Saatler Europe/Istanbul'a goredir (timezone ayari yukarida).
# ZAMANLAMANIN SAHIBI KIM?
#
# Is akislari (veri cekme, arastirma, icerik, haftalik rapor, baglanti
# sagligi) n8n tarafindan zamanlanir ve panelde "Otomasyon" sayfasinda
# gorunur. Burada TEKRAR zamanlanmazlar.
#
# Neden: daha once veri senkronu hem burada (6 saatte bir) hem WF-01'de
# vardi; haftalik rapor ise ikisinde de PAZARTESI 08:00 idi. Ayni is iki
# kez calisiyordu ve buradaki calismalar panelde HIC GORUNMUYORDU -
# kullanici "akis calisti mi" sorusunu cevaplayamazdi.
#
# Burada yalnizca n8n'de karsiligi OLMAYAN isler kalir.
celery_app.conf.beat_schedule = {
    "heartbeat-her-5-dakika": {
        "task": "app.workers.tasks.heartbeat",
        "schedule": crontab(minute="*/5"),
    },
    # Gunluk ve aylik rapor: n8n'de karsiligi yok (WF-04 haftaliktir).
    "gunluk-rapor-sabah-07": {
        "task": "app.workers.tasks.generate_daily_report",
        "schedule": crontab(minute=30, hour=7),
    },
    "aylik-rapor-ayin-biri-09": {
        "task": "app.workers.tasks.generate_monthly_report",
        "schedule": crontab(minute=0, hour=9, day_of_month=1),
    },
}

celery_app.autodiscover_tasks(["app.workers"])

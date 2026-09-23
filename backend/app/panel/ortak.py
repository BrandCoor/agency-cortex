"""Kenar menude yalnizca ACILABILEN sayfalar gorunur.

SORUN: menu, uyeligi olan herkese butun baglantilari gosteriyordu.
Izni olmayan biri "Yetkiler"e tiklayinca "Bulunamadı" sayfasi aliyordu.
Calismayan bir dugme, olmayan bir dugmeden daha kotudur.

COZUM: uyelik bulunan her istekte, o kisinin bu musterideki gecerli
izinleri `request.state.izinler` icine konur; sablon buna bakar.

ONEMLI: bu yalnizca GORUNUM. Asil kilit sayfalarin kendisindedir. Menude
gizlemek guvenlik degildir; adresi elle yazan biri yine reddedilir.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.services.yetkiler import kullanici_izinleri


def izinleri_hatirla(request, db, user) -> None:
    """Bu istegin menusu icin gecerli izinleri saklar."""
    try:
        request.state.izinler = kullanici_izinleri(db, user)
    except Exception:  # noqa: BLE001 - menu, sayfayi ASLA dusurmemeli
        # Izinler okunamazsa menu eksik gorunur; sayfa yine acilir.
        request.state.izinler = frozenset()


def uyelik_bul(request, db, user, workspace_id: uuid.UUID):
    """Kullanicinin bu musterideki uyeligi (yoksa None).

    Uyelik bulunursa menunun ihtiyaci olan izinler de hazirlanir. Uc ayri
    panel modulu bunun kendi kopyasini tutuyordu; kopyalar zamanla
    birbirinden ayrilirdi.
    """
    from app.models.identity import WorkspaceMember

    uyelik = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).scalar_one_or_none()
    if uyelik is not None:
        # Kenar menu, yapilamayacak isleri GOSTERMEZ.
        izinleri_hatirla(request, db, user)
    return uyelik

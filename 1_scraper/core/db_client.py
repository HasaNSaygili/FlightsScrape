"""
db_client.py
────────────
Supabase'e toplu (bulk) upsert işlemleri yapan istemci modülü.
"""

from __future__ import annotations

from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from core.flight_model import FlightData


# ─── CLIENT SINGLETON ─────────────────────────────────────────────────

_client: Client | None = None


def get_client() -> Client:
    """Supabase istemcisini döndürür (singleton)."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError(
                "SUPABASE_URL ve SUPABASE_SERVICE_ROLE_KEY ortam değişkenleri ayarlanmalıdır."
            )
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _client


# ─── UPSERT İŞLEMLERİ ─────────────────────────────────────────────────

async def upsert_flights(flights: list[FlightData], batch_size: int = 500) -> int:
    """
    Uçuş verilerini Supabase'e toplu upsert eder.

    Args:
        flights: Validate edilmiş FlightData listesi
        batch_size: Her batch'teki kayıt sayısı

    Returns:
        Toplam işlenen kayıt sayısı
    """
    client = get_client()
    records = [f.to_db_dict() for f in flights]
    total = 0

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        client.table("flights").upsert(
            batch,
            on_conflict="flight_number,flight_date,airport_code",
        ).execute()
        total += len(batch)

    return total

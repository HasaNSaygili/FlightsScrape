"""
base_scraper.py
───────────────
Tüm scraper'ların miras aldığı soyut temel sınıf.
Ortak metotları (HTTP istek, proxy rotasyonu, hata yönetimi,
veri doğrulama ve Supabase'e yazma) tek noktada toplar.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import date

import aiohttp

from core.flight_model import FlightData, SourceEnum
from core.proxy_manager import ProxyManager
from core.db_client import upsert_flights
from config import REQUEST_TIMEOUT, MAX_RETRIES, REQUEST_DELAY


logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Her işletmeci scraper'ı bu sınıftan türetilir."""

    # Alt sınıflar override eder
    SOURCE: SourceEnum
    AIRPORT_CODES: list[str] = []  # Bu scraper'ın kapsadığı havalimanları

    def __init__(self, proxy_manager: ProxyManager | None = None):
        self.proxy_manager = proxy_manager or ProxyManager()

    # ── Soyut Metotlar ─────────────────────────────────────────────────

    @abstractmethod
    async def fetch_flights(
        self,
        session: aiohttp.ClientSession,
        airport_code: str,
        flight_date: date,
    ) -> list[FlightData]:
        """
        Belirli bir havalimanı ve tarih için uçuş verilerini çeker.
        Alt sınıf, API'ye istek atıp ham JSON'ı FlightData listesine dönüştürür.
        """
        ...

    # ── Ortak Metotlar ─────────────────────────────────────────────────

    async def run(self, flight_date: date | None = None) -> int:
        """
        Bu scraper'ın kapsadığı tüm havalimanları için veri çekip
        Supabase'e yazan ana çalıştırma metodu.

        Returns:
            Toplam yazılan kayıt sayısı
        """
        target_date = flight_date or date.today()
        total = 0

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        ) as session:
            for code in self.AIRPORT_CODES:
                try:
                    flights = await self.fetch_flights(session, code, target_date)
                    if flights:
                        count = await upsert_flights(flights)
                        total += count
                        logger.info(
                            f"[{self.SOURCE.value}] {code}: {count} uçuş yazıldı"
                        )
                    else:
                        logger.warning(f"[{self.SOURCE.value}] {code}: Veri bulunamadı")
                except Exception as e:
                    logger.error(
                        f"[{self.SOURCE.value}] {code}: Hata — {e}", exc_info=True
                    )

                # Rate limiting
                await asyncio.sleep(REQUEST_DELAY)

        return total

    async def _request_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        method: str = "GET",
        headers: dict | None = None,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict | list | None:
        """
        Proxy rotasyonlu HTTP istek atar, JSON döndürür.
        Başarısız olursa MAX_RETRIES kadar yeniden dener.
        """
        proxy = self.proxy_manager.get_proxy_dict()
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    proxy=proxy,
                ) as response:
                    response.raise_for_status()
                    return await response.json()

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                logger.warning(
                    f"[{self.SOURCE.value}] İstek başarısız (deneme {attempt}/{MAX_RETRIES}): {e}"
                )
                # Bir sonraki denemede farklı proxy
                proxy = self.proxy_manager.get_proxy_dict()
                await asyncio.sleep(attempt * 0.5)

        logger.error(f"[{self.SOURCE.value}] {MAX_RETRIES} deneme sonrası başarısız: {last_error}")
        return None

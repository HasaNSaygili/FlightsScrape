"""
fraport_tav_scraper.py
──────────────────────
Fraport TAV — Antalya Havalimanı (AYT).

API Keşfi:
  AYT, modern bir JSON API kullanmıyor. Tıpkı Sabiha Gökçen gibi sunucu tarafında oluşturulan (SSR)
  HTML tablolar kullanıyor. 4 farklı sayfa üzerinden (iç/dış geliş/gidiş) veriler alınıp BeautifulSoup ile parse edilecek.

  URL'ler:
  - Dış Hat Geliş: /passengers-visitors/flight-info/international-arrivals
  - İç Hat Geliş: /passengers-visitors/flight-info/domestic-arrivals
  - Dış Hat Gidiş: /passengers-visitors/flight-info/international-departures
  - İç Hat Gidiş: /passengers-visitors/flight-info/domestic-departures
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta
import asyncio

import aiohttp
from bs4 import BeautifulSoup

from core.flight_model import (
    FlightData,
    DirectionEnum,
    FlightStatusEnum,
    SourceEnum,
)
from scrapers.base_scraper import BaseScraper
from config import REQUEST_DELAY

logger = logging.getLogger(__name__)

# ─── Türkiye saat dilimi ──────────────────────────────────────────────
TZ_TR = timezone(timedelta(hours=3))

# ─── API Sabitleri ────────────────────────────────────────────────────
BASE_URL = "https://www.antalya-airport.aero/passengers-visitors/flight-info"

ENDPOINTS = [
    (f"{BASE_URL}/international-arrivals", DirectionEnum.ARRIVAL),
    (f"{BASE_URL}/domestic-arrivals", DirectionEnum.ARRIVAL),
    (f"{BASE_URL}/international-departures", DirectionEnum.DEPARTURE),
    (f"{BASE_URL}/domestic-departures", DirectionEnum.DEPARTURE),
]

DEFAULT_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "accept-language": "en-US,en;q=0.9",
}

# ─── Durum Normalizasyonu ─────────────────────────────────────────────

def _normalize_status(raw_status: str | None) -> FlightStatusEnum:
    """AYT durumunu normalize eder (İngilizce)."""
    if not raw_status:
        return FlightStatusEnum.UNKNOWN

    lower = raw_status.lower().strip()
    if "land" in lower:
        return FlightStatusEnum.LANDED
    if "depart" in lower:
        return FlightStatusEnum.DEPARTED
    if "cancel" in lower:
        return FlightStatusEnum.CANCELLED
    if "delay" in lower:
        return FlightStatusEnum.DELAYED
    if "board" in lower or "gate" in lower: # Boarding, Gate Open, Gate closed
        return FlightStatusEnum.BOARDING
    if "check-in" in lower or "sched" in lower:
        return FlightStatusEnum.SCHEDULED
    if "time" in lower: # On time
        return FlightStatusEnum.ON_TIME
        
    return FlightStatusEnum.UNKNOWN

class FraportTavScraper(BaseScraper):
    """
    Fraport TAV scraper — Antalya Havalimanı (AYT).
    HTML sayfalarını parse eder.
    """

    SOURCE = SourceEnum.FRAPORT_TAV
    AIRPORT_CODES = ["AYT"]

    async def run(self, flight_date: date | None = None) -> int:
        """Kendi run metodumuzda 4 URL'i gezeceğiz."""
        target_date = flight_date or date.today()
        total = 0

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=45),
            headers=DEFAULT_HEADERS,
        ) as session:
            for url, direction in ENDPOINTS:
                try:
                    await asyncio.sleep(REQUEST_DELAY)
                    proxy = self.proxy_manager.get_proxy_dict()
                    
                    async with session.get(url, proxy=proxy) as resp:
                        resp.raise_for_status()
                        html_content = await resp.text()

                    flights = self._parse_html(html_content, direction, target_date)
                    
                    if flights:
                        from core.db_client import upsert_flights
                        count = await upsert_flights(flights)
                        total += count
                        logger.info(f"[fraport] AYT {direction.value} ({url.split('/')[-1]}): {count} uçuş yazıldı")
                except Exception as e:
                    logger.error(f"[fraport] URL isteğinde hata: {url} -> {e}")

        logger.info(f"[fraport] Toplam: {total} uçuş kaydı yazıldı")
        return total

    def _parse_html(self, html: str, direction: DirectionEnum, target_date: date) -> list[FlightData]:
        soup = BeautifulSoup(html, "html.parser")
        flights: list[FlightData] = []
        
        # Antalya havalimanında uçuşlar 'div.flight-info-row' veya table içinde gelir
        # Telerik yapısında çoğunlukla table tag'i bulunur
        has_airline = soup.find("td", class_="airline")
        table = has_airline.find_parent("table") if has_airline else None

        if not table:
            # Alternatif olarak div yapısına bak
            rows = soup.select(".flight-row") # Örnek CSS sınıfı, tam HTML'e göre uyarlanmalı
            if not rows:
                return []
        
        # Table tbody satırları
        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            # Genelde Antalya sütunları:
            # 0: Tarih/Durum (zamanla değişiyor)
            # 1: Tahmini Süre
            # 2: Airline
            # 3: Uçuş No (Örn: PC/PGT 1580)
            # 4: Şehir (Vnukovo)
            # 5: Kapı/Terminal
            
            def safe_text(tds, cls1, cls2=None):
                for c in tds:
                    classes = c.get("class", [])
                    if cls1 in classes or (cls2 and cls2 in classes):
                        return c.text.strip()
                return ""

            flight_number_col = safe_text(cols, "flightnum")
            
            # XQ/SXS 209 -> XQ209
            parts = flight_number_col.strip().split()
            if len(parts) >= 2:
                flight_number = f"{parts[0].split('/')[0]}{parts[1]}"
            else:
                flight_number = flight_number_col.split('/')[0].replace(" ", "")

            airline_name = safe_text(cols, "airline")
            city = safe_text(cols, "from", "to")
            
            # scheduled time is in td.time.scheduled
            scheduled_str = safe_text(cols, "scheduled")
            estimated_str = safe_text(cols, "estimated")
            
            terminal = safe_text(cols, "terminal")
            status_str = safe_text(cols, "status")
                
            if not flight_number:
                continue

            scheduled_dt = self._combine_date_time(target_date, scheduled_str)
            if not scheduled_dt:
                continue

            estimated_dt = self._combine_date_time(target_date, estimated_str)
            
            if direction == DirectionEnum.ARRIVAL:
                origin_city = city
                destination_city = "Antalya"
            else:
                origin_city = "Antalya"
                destination_city = city

            flight = FlightData(
                flight_number=flight_number,
                flight_date=target_date,
                airport_code="AYT",
                direction=direction,
                source=self.SOURCE,
                airport_name="Antalya Havalimanı",
                airline_code=self._extract_airline_code(flight_number),
                airline_name=airline_name if airline_name else None,
                origin_city=origin_city,
                destination_city=destination_city,
                scheduled_time=scheduled_dt,
                estimated_time=estimated_dt,
                status=_normalize_status(status_str),
                status_detail=status_str if status_str else None,
                terminal=terminal if terminal else None,
            )
            flights.append(flight)

        return flights

    def _extract_airline_code(self, flight_number: str) -> str | None:
        code = ""
        for ch in flight_number:
            if ch.isalpha():
                code += ch
            else:
                break
        return code.upper() if code else None

    def _combine_date_time(self, d: date, time_str: str) -> datetime | None:
        # time_str could be "09:40"
        time_str = time_str.replace(".", ":") # Sometimes 09.40
        if not time_str or ":" not in time_str:
            return None
        
        parts = time_str.split(":")
        if len(parts) >= 2:
            try:
                hour = int(parts[0][-2:]) # robust if it has other chars "Time: 09:40"
                minute = int(parts[1][:2])
                return datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ_TR)
            except ValueError:
                pass
        return None

    async def fetch_flights(
        self,
        session: aiohttp.ClientSession,
        airport_code: str,
        flight_date: date,
    ) -> list[FlightData]:
        raise NotImplementedError("Fraport TAV kendi run() metodunu kullanır.")

"""
ic_ictas_scraper.py
───────────────────
IC İçtaş — Zafer Havalimanı (KZR).

API Keşfi:
  Zafer Havalimanı, modern bir JSON API kullanmıyor.
  Sunucu tarafında oluşturulan (SSR) HTML tablolarını 4 ayrı adresten sunar.
  - /TR/ichatlargelen
  - /TR/ichatlargiden
  - /TR/dishatlargelen
  - /TR/dishatlargiden
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

BASE_URL = "https://www.zafer.aero/TR"

ENDPOINTS = [
    (f"{BASE_URL}/ichatlargelen", DirectionEnum.ARRIVAL),
    (f"{BASE_URL}/ichatlargiden", DirectionEnum.DEPARTURE),
    (f"{BASE_URL}/dishatlargelen", DirectionEnum.ARRIVAL),
    (f"{BASE_URL}/dishatlargiden", DirectionEnum.DEPARTURE),
]

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def _normalize_status(raw_status: str | None) -> FlightStatusEnum:
    if not raw_status:
        return FlightStatusEnum.UNKNOWN

    lower = raw_status.lower().strip()
    if "indi" in lower or "land" in lower:
        return FlightStatusEnum.LANDED
    if "kalk" in lower or "depart" in lower:
        return FlightStatusEnum.DEPARTED
    if "iptal" in lower or "cancel" in lower:
        return FlightStatusEnum.CANCELLED
    if "gecik" in lower or "delay" in lower:
        return FlightStatusEnum.DELAYED
    if "kap" in lower or "board" in lower or "gate" in lower:
        return FlightStatusEnum.BOARDING
    if "zaman" in lower or "time" in lower:
        return FlightStatusEnum.ON_TIME
    if "check-in" in lower or "beklen" in lower or "sched" in lower:
        return FlightStatusEnum.SCHEDULED
        
    return FlightStatusEnum.UNKNOWN

class IcIctasScraper(BaseScraper):
    """
    IC İçtaş — Zafer Havalimanı (KZR) Scraper.
    """

    SOURCE = SourceEnum.IC_ICTAS
    AIRPORT_CODES = ["KZR"]

    async def run(self, flight_date: date | None = None) -> int:
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
                        logger.info(f"[ic_ictas] KZR {direction.value} ({url.split('/')[-1]}): {count} uçuş yazıldı")
                except Exception as e:
                    logger.error(f"[ic_ictas] URL isteğinde hata: {url} -> {e}")

        logger.info(f"[ic_ictas] Toplam: {total} uçuş kaydı yazıldı")
        return total

    def _parse_html(self, html: str, direction: DirectionEnum, target_date: date) -> list[FlightData]:
        soup = BeautifulSoup(html, "html.parser")
        flights: list[FlightData] = []
        
        table = soup.find("table")
        if not table:
            return []
            
        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            # Zafer Havalimanı sütun yapısı:
            # 0: Tarih (08.03.2026)
            # 1: Logo (img)
            # 2: Sefer No (TK 2055)
            # 3: Şehir / Yer
            # 4: Ara Meydan
            # 5: Planlı Kalkış/Varış (15:55)
            # 6: Tahmini (16:50)
            # 7: Kapı / Bagaj No
            # 8: Durum (İNDİ vs)
            
            def get_text(idx):
                return cols[idx].text.strip().replace("\n", "") if len(cols) > idx else ""

            date_str = get_text(0)
            if not date_str:
                continue
                
            flight_number = get_text(2).replace(" ", "")
            if not flight_number:
                continue

            city_desc = get_text(3)
            scheduled_str = get_text(5)
            estimated_str = get_text(6)
            gate_terminal = get_text(7)
            status_str = get_text(8)
            
            # Tarih eşleşmiyorsa pass
            if date_str != target_date.strftime("%d.%m.%Y"):
                continue

            airline_name = self._guess_airline(cols[1])

            scheduled_dt = self._combine_date_time(target_date, scheduled_str)
            if not scheduled_dt:
                continue

            estimated_dt = self._combine_date_time(target_date, estimated_str)
            
            if direction == DirectionEnum.ARRIVAL:
                origin_city = city_desc
                destination_city = "Kütahya/Zafer" 
            else:
                origin_city = "Kütahya/Zafer"
                destination_city = city_desc

            flight = FlightData(
                flight_number=flight_number,
                flight_date=target_date,
                airport_code="KZR",
                direction=direction,
                source=self.SOURCE,
                airport_name="Zafer Havalimanı",
                airline_code=self._extract_airline_code(flight_number),
                airline_name=airline_name,
                origin_city=origin_city,
                destination_city=destination_city,
                scheduled_time=scheduled_dt,
                estimated_time=estimated_dt,
                status=_normalize_status(status_str),
                status_detail=status_str if status_str else None,
                gate=gate_terminal if gate_terminal else None,
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

    def _guess_airline(self, td) -> str | None:
        if not td: return None
        img = td.find("img")
        if img and img.get("alt"):
            return img.get("alt").strip()
        if img and img.get("src"):
            src = img.get("src").lower()
            if "thy" in src or "turkish" in src or "tk" in src: return "Turkish Airlines"
            if "pc" in src or "pegasus" in src: return "Pegasus Airlines"
            if "eurowings" in src: return "Eurowings"
            if "sunexpress" in src or "xq" in src: return "SunExpress"
        return td.text.strip() or None

    def _combine_date_time(self, d: date, time_str: str) -> datetime | None:
        time_str = time_str.replace(".", ":") 
        if not time_str or ":" not in time_str:
            return None
        
        parts = time_str.split(":")
        if len(parts) >= 2:
            try:
                hour = int(parts[0][-2:]) 
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
        raise NotImplementedError("IC İçtaş kendi run() metodunu kullanır.")

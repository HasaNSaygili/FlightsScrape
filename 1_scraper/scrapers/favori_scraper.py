"""
favori_scraper.py
─────────────────
Favori Airports — Çukurova Havalimanı (COV).

API Keşfi:
  Çukurova Havalimanı'nın web sitesinde, uçuş verileri bir AJAX GET isteği ile HTML snippet olarak dönüyor.
  Endpoint: GET https://cukurovaairport.aero/include/get_data.php?pageId={type}
  type: dom-arr-flights, dom-dep-flights, int-arr-flights, int-dep-flights
  Header: X-Requested-With: XMLHttpRequest
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta
import asyncio
import re

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

API_URL = "https://cukurovaairport.aero/include/get_data.php"

ENDPOINTS = [
    ("dom-arr-flights", DirectionEnum.ARRIVAL),
    ("dom-dep-flights", DirectionEnum.DEPARTURE),
    ("int-arr-flights", DirectionEnum.ARRIVAL),
    ("int-dep-flights", DirectionEnum.DEPARTURE),
]

DEFAULT_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html, */*; q=0.01",
}

def _normalize_status(raw_status: str | None) -> FlightStatusEnum:
    if not raw_status:
        return FlightStatusEnum.UNKNOWN

    lower = raw_status.lower().strip()
    if "indi" in lower or "landed" in lower:
        return FlightStatusEnum.LANDED
    if "kalk" in lower or "departed" in lower:
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

def _parse_cov_datetime(text: str | None) -> datetime | None:
    # Text looks like: "Planlanan Zaman08.03.202611:15" or "Tahmini Zaman08.03.202611:20"
    if not text:
        return None
    # We can extract the date and time using regex: DD.MM.YYYYHH:MM or DD.MM.YYYY HH:MM
    match = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*(\d{2}:\d{2})", text)
    if match:
        date_str, time_str = match.groups()
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M").replace(tzinfo=TZ_TR)
        except ValueError:
            return None
    return None

class FavoriScraper(BaseScraper):
    """
    Favori Çukurova Havalimanı (COV) Scraper.
    """

    SOURCE = SourceEnum.FAVORI
    AIRPORT_CODES = ["COV"]

    async def run(self, flight_date: date | None = None) -> int:
        target_date = flight_date or date.today()
        total = 0

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=45),
            headers=DEFAULT_HEADERS,
        ) as session:
            for page_id, direction in ENDPOINTS:
                try:
                    await asyncio.sleep(REQUEST_DELAY)
                    proxy = self.proxy_manager.get_proxy_dict()
                    url = f"{API_URL}?pageId={page_id}"
                    
                    async with session.get(url, proxy=proxy) as resp:
                        resp.raise_for_status()
                        html_content = await resp.text()

                    flights = self._parse_html(html_content, direction, target_date)
                    
                    if flights:
                        from core.db_client import upsert_flights
                        count = await upsert_flights(flights)
                        total += count
                        logger.info(f"[favori] COV {direction.value} ({page_id}): {count} uçuş yazıldı")
                except Exception as e:
                    logger.error(f"[favori] URL isteğinde hata: {page_id} -> {e}")

        logger.info(f"[favori] Toplam: {total} uçuş kaydı yazıldı")
        return total

    def _parse_html(self, html: str, direction: DirectionEnum, target_date: date) -> list[FlightData]:
        soup = BeautifulSoup(html, "html.parser")
        flights: list[FlightData] = []
        
        rows = soup.find_all("tr")
        for tr in rows:
            # Uçuş Numarası
            ucus_box = tr.find("div", class_="ucusBox")
            flight_number = ucus_box.text.strip().replace("\n", "").replace(" ", "") if ucus_box else ""
            if not flight_number:
                continue
                
            airline_name = self._guess_airline(ucus_box)

            # Şehir
            route_box = tr.find("div", class_="routeBox")
            city = route_box.text.strip() if route_box else ""

            # Zaman
            planlanan_box = tr.find("div", class_="planlanan-ucus")
            planlanan_text = planlanan_box.text.strip().replace("\n", "") if planlanan_box else ""
            scheduled_dt = _parse_cov_datetime(planlanan_text)
            
            tahmini_box = tr.find("div", class_="tahmini-ucus")
            tahmini_text = tahmini_box.text.strip().replace("\n", "") if tahmini_box else ""
            estimated_dt = _parse_cov_datetime(tahmini_text)

            if not scheduled_dt:
                continue
                
            # Filter by exactly the target date
            if scheduled_dt.date() != target_date:
                continue

            # Durum
            status_box = tr.find("div", class_="status-box")
            status_str = status_box.text.strip() if status_box else ""

            # Kapı / Terminal
            gate_td = tr.find("td", class_="gate-info")
            gate = gate_td.text.strip() if gate_td else ""
            
            if direction == DirectionEnum.ARRIVAL:
                origin_city = city
                destination_city = "Mersin/Adana" # Çukurova
            else:
                origin_city = "Mersin/Adana"
                destination_city = city

            flight = FlightData(
                flight_number=flight_number,
                flight_date=target_date,
                airport_code="COV",
                direction=direction,
                source=self.SOURCE,
                airport_name="Çukurova Havalimanı",
                airline_code=self._extract_airline_code(flight_number),
                airline_name=airline_name,
                origin_city=origin_city,
                destination_city=destination_city,
                scheduled_time=scheduled_dt,
                estimated_time=estimated_dt,
                status=_normalize_status(status_str),
                status_detail=status_str if status_str else None,
                gate=gate if gate and gate != "-" else None,
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

    def _guess_airline(self, ucus_box) -> str | None:
        if not ucus_box: return None
        img = ucus_box.find("img")
        if img and img.get("alt"):
            return img.get("alt")
        if img and img.get("src"):
            src = img.get("src").lower()
            if "thy" in src or "turkish" in src: return "Turkish Airlines"
            if "pc" in src or "pegasus" in src: return "Pegasus Airlines"
            if "ajet" in src or "vf" in src: return "AJet"
            if "sunexpress" in src or "xq" in src: return "SunExpress"
            if "corendon" in src or "xc" in src: return "Corendon Airlines"
        return None

    async def fetch_flights(
        self,
        session: aiohttp.ClientSession,
        airport_code: str,
        flight_date: date,
    ) -> list[FlightData]:
        raise NotImplementedError("Favori kendi run() metodunu kullanır.")

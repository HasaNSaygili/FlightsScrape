"""
estu_scraper.py
───────────────
ESTÜ — Eskişehir Hasan Polatkan Havalimanı (AOE).

API Keşfi:
  Hasan Polatkan, uçuş verilerini Google Apps Script üzerinden JSON olarak döner.
  Endpoint: GET https://script.google.com/macros/s/AKfycbyUTZ9bka3gD876eQ-MKGZPUdpIMkCMlTA3Wqh6nCQeH2mgaEIrPjp1RocP5jFwWifUEQ/exec?type={arrival|departure}&date=DD.MM.YYYY
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta
import asyncio

import aiohttp

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

API_URL = "https://script.google.com/macros/s/AKfycbyUTZ9bka3gD876eQ-MKGZPUdpIMkCMlTA3Wqh6nCQeH2mgaEIrPjp1RocP5jFwWifUEQ/exec"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
}

def _normalize_status(raw_status: str | None) -> FlightStatusEnum:
    if not raw_status or raw_status.strip() == "---":
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

class EstuScraper(BaseScraper):
    """
    ESTÜ — Eskişehir Hasan Polatkan (AOE) Scraper.
    """

    SOURCE = SourceEnum.ESTU
    AIRPORT_CODES = ["AOE"]

    async def fetch_flights(
        self,
        session: aiohttp.ClientSession,
        airport_code: str,
        flight_date: date,
    ) -> list[FlightData]:
        
        all_flights: list[FlightData] = []
        date_str = flight_date.strftime("%d.%m.%Y")
        
        # 1. Arrivals
        arr = await self._fetch_leg(session, "arrival", DirectionEnum.ARRIVAL, flight_date, date_str)
        all_flights.extend(arr)
        
        await asyncio.sleep(REQUEST_DELAY)
        
        # 2. Departures
        dep = await self._fetch_leg(session, "departure", DirectionEnum.DEPARTURE, flight_date, date_str)
        all_flights.extend(dep)

        return all_flights

    async def _fetch_leg(
        self,
        session: aiohttp.ClientSession,
        leg_type: str,
        direction: DirectionEnum,
        target_date: date,
        date_str: str,
    ) -> list[FlightData]:
        
        url = f"{API_URL}?type={leg_type}&date={date_str}"
        proxy = self.proxy_manager.get_proxy_dict()
        
        try:
            # Google Apps Script redirects (302) to script.googleusercontent.com, so allow_redirects=True
            async with session.get(url, headers=DEFAULT_HEADERS, proxy=proxy, timeout=25, allow_redirects=True) as resp:
                resp.raise_for_status()
                json_data = await resp.json()
        except Exception as e:
            logger.error(f"[estu] AOE API hatası ({direction.value}): {e}")
            return []

        data_list = json_data.get("data", [])
        if not data_list:
            return []

        # İlk obje genelde header satırıdır (ör. {"flightNo": "flightNo", ...}). Kontrol et.
        parsed_flights = []
        for raw in data_list:
            if raw.get("flightNo") == "flightNo" or raw.get("date") == "date":
                continue # Header row
                
            try:
                flight = self._parse_flight(raw, direction, target_date)
                if flight:
                    parsed_flights.append(flight)
            except Exception as e:
                logger.debug(f"[estu] Parse hatası: {e}")

        logger.info(f"[estu] AOE {direction.value}: {len(parsed_flights)} uçuş bulundu.")
        return parsed_flights

    def _parse_flight(
        self,
        raw: dict,
        direction: DirectionEnum,
        target_date: date,
    ) -> FlightData | None:

        flight_number = raw.get("flightNo")
        if not flight_number or flight_number.strip() == "":
            return None
            
        airline_name = raw.get("airlineName")
        
        time_str = raw.get("time") # Ör: "12:45"
        scheduled_dt = None
        if time_str and ":" in time_str:
            try:
                h, m = map(int, time_str.split(":", 1))
                scheduled_dt = datetime(target_date.year, target_date.month, target_date.day, h, m, tzinfo=TZ_TR)
            except ValueError:
                pass

        if not scheduled_dt or scheduled_dt.date() != target_date:
            return None

        status_str = raw.get("remarks")
        status = _normalize_status(status_str)

        if direction == DirectionEnum.ARRIVAL:
            origin_city = raw.get("origin")
            destination_city = "Eskişehir"
        else:
            origin_city = "Eskişehir"
            destination_city = raw.get("destination")

        return FlightData(
            flight_number=flight_number,
            flight_date=target_date,
            airport_code="AOE",
            direction=direction,
            source=self.SOURCE,
            airport_name="Hasan Polatkan Havalimanı",
            airline_code=self._extract_airline_code(flight_number),
            airline_name=airline_name,
            origin_city=origin_city,
            destination_city=destination_city,
            scheduled_time=scheduled_dt,
            estimated_time=None, # Verilmiyor
            status=status,
            status_detail=status_str if status_str and status_str != "---" else None,
        )

    def _extract_airline_code(self, flight_number: str) -> str | None:
        code = ""
        for ch in flight_number:
            if ch.isalpha():
                code += ch
            else:
                break
        return code.upper() if code else None

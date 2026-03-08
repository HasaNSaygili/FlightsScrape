"""
yda_scraper.py
──────────────
YDA — Dalaman Havalimanı (DLM).

API Keşfi:
  YDA Dalaman, AWS API Gateway üzerinde host edilen bir JSON REST API kullanıyor.
  Endpoint: GET https://n7tosj4g7c.execute-api.eu-west-1.amazonaws.com/pro/flights?flightDirection={D/A}&isHome=false
  x-api-key gerektiriyor.
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

# ─── API Sabitleri ────────────────────────────────────────────────────
API_URL = "https://n7tosj4g7c.execute-api.eu-west-1.amazonaws.com/pro/flights"

DEFAULT_HEADERS = {
    "x-api-key": "QcwHM1dxUl5AwyDtNXoNm3PxlE1SEEYE4S3SBfW0",
    "x-airport-code": "DLM",
    "x-app-language": "tr",
    "x-app-version": "3",
    "accept": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

# ─── Durum Normalizasyonu ─────────────────────────────────────────────

def _normalize_status(remark: str | None) -> FlightStatusEnum:
    """DLM durumunu normalize eder (Türkçe/İngilizce)."""
    if not remark:
        return FlightStatusEnum.UNKNOWN

    lower = remark.lower().strip()
    if "indi" in lower or "land" in lower:
        return FlightStatusEnum.LANDED
    if "kalk" in lower or "depart" in lower:
        return FlightStatusEnum.DEPARTED
    if "iptal" in lower or "cancel" in lower:
        return FlightStatusEnum.CANCELLED
    if "gecik" in lower or "delay" in lower:
        return FlightStatusEnum.DELAYED
    if "kap" in lower or "board" in lower or "gate" in lower: # Kapı kapandı, gate open vs.
        return FlightStatusEnum.BOARDING
    if "zaman" in lower or "time" in lower:
        return FlightStatusEnum.ON_TIME
    if "check-in" in lower or "beklen" in lower or "sched" in lower:
        return FlightStatusEnum.SCHEDULED
        
    return FlightStatusEnum.UNKNOWN

def _parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        # Ensure it's in Turkish timezone
        return dt.astimezone(TZ_TR)
    except ValueError:
        return None

class YdaScraper(BaseScraper):
    """
    YDA Scraper — Dalaman Havalimanı (DLM).
    """

    SOURCE = SourceEnum.YDA
    AIRPORT_CODES = ["DLM"]

    async def fetch_flights(
        self,
        session: aiohttp.ClientSession,
        airport_code: str,
        flight_date: date,
    ) -> list[FlightData]:
        """Base class bu metodu kullanarak DLM için çağıracaktır."""
        
        all_flights: list[FlightData] = []
        
        # 1. Departures (D)
        dep_data = await self._fetch_leg(session, "D", DirectionEnum.DEPARTURE, flight_date)
        all_flights.extend(dep_data)
        
        await asyncio.sleep(REQUEST_DELAY)
        
        # 2. Arrivals (A)
        arr_data = await self._fetch_leg(session, "A", DirectionEnum.ARRIVAL, flight_date)
        all_flights.extend(arr_data)

        return all_flights

    async def _fetch_leg(
        self,
        session: aiohttp.ClientSession,
        leg_code: str,
        direction: DirectionEnum,
        target_date: date,
    ) -> list[FlightData]:
        
        url = f"{API_URL}?flightDirection={leg_code}&isHome=false"
        proxy = self.proxy_manager.get_proxy_dict()
        
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, proxy=proxy, timeout=15) as resp:
                resp.raise_for_status()
                json_data = await resp.json()
        except Exception as e:
            logger.error(f"[yda] DLM API hatası ({direction.value}): {e}")
            return []

        if not isinstance(json_data, list):
            logger.warning(f"[yda] Beklenmeyen format, list dönmedi: {type(json_data)}")
            return []

        parsed_flights = []
        for raw in json_data:
            try:
                flight = self._parse_flight(raw, direction, target_date)
                if flight:
                    parsed_flights.append(flight)
            except Exception as e:
                logger.debug(f"[yda] Parse hatası: {e}")

        logger.info(f"[yda] DLM {direction.value}: {len(parsed_flights)} uçuş bulundu.")
        return parsed_flights

    def _parse_flight(
        self,
        raw: dict,
        direction: DirectionEnum,
        target_date: date,
    ) -> FlightData | None:

        flight_number = raw.get("flightNumber")
        if not flight_number:
            return None
            
        airline_name = raw.get("airlineName")
        city_desc = raw.get("originDestAirportDesc", "")
        
        scheduled = _parse_iso(raw.get("scheduledDateTime"))
        estimated = _parse_iso(raw.get("estimatedDateTime"))
        
        if not scheduled:
            return None

        status_str = raw.get("remark")
        status = _normalize_status(status_str)

        if direction == DirectionEnum.ARRIVAL:
            origin_city = city_desc
            destination_city = "Muğla" # Dalaman
        else:
            origin_city = "Muğla"
            destination_city = city_desc

        gate = raw.get("gateCode")
        carousel = raw.get("carrouselCode")
        terminal = gate if direction == DirectionEnum.DEPARTURE else carousel

        return FlightData(
            flight_number=flight_number,
            flight_date=scheduled.date(),
            airport_code="DLM",
            direction=direction,
            source=self.SOURCE,
            airport_name="Dalaman Havalimanı",
            airline_code=raw.get("airlineCode"),
            airline_name=airline_name,
            origin_city=origin_city,
            destination_city=destination_city,
            scheduled_time=scheduled,
            estimated_time=estimated,
            status=status,
            status_detail=status_str,
            terminal=terminal,
        )

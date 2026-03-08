"""
tav_scraper.py
──────────────
TAV Havalimanları — İzmir (ADB), Ankara (ESB), Bodrum (BJV), Gazipaşa (GZP).

API Keşfi:
  TAV, tüm havalimanları için ortak bir altyapı kullanır.
  Endpoint: GET https://{domain}/Home/getCurrentFlights?flightLeg={LEG}
  - LEG: 'ARR' (Geliş) veya 'DEP' (Gidiş)
  - Header: "x-requested-with": "XMLHttpRequest" zorunludur.

Alan Adları (Domains):
  - ADB: izmirairport.com
  - ESB: esenbogaairport.com
  - BJV: milas-bodrumairport.com
  - GZP: gzpairport.com
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
TAV_DOMAINS = {
    "ADB": "izmirairport.com",
    "ESB": "esenbogaairport.com",
    "BJV": "milas-bodrumairport.com",
    "GZP": "gzpairport.com",
}

DEFAULT_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}

# ─── Durum Normalizasyonu ─────────────────────────────────────────────

def _normalize_status(remark_en: str | None) -> FlightStatusEnum:
    """TAV İngilizce durumunu normalize eder."""
    if not remark_en:
        return FlightStatusEnum.UNKNOWN

    lower = remark_en.lower()
    if "land" in lower:
        return FlightStatusEnum.LANDED
    if "depart" in lower:
        return FlightStatusEnum.DEPARTED
    if "cancel" in lower:
        return FlightStatusEnum.CANCELLED
    if "delay" in lower:
        return FlightStatusEnum.DELAYED
    if "board" in lower:
        return FlightStatusEnum.BOARDING
    if "gate" in lower:   # Gate Open / Gate Closing vs.
        return FlightStatusEnum.BOARDING
    if "check" in lower:  # Check-in Open
        return FlightStatusEnum.SCHEDULED
    if "time" in lower:   # On Time
        return FlightStatusEnum.ON_TIME
    if "sched" in lower:  # Scheduled
        return FlightStatusEnum.SCHEDULED
        
    return FlightStatusEnum.UNKNOWN


def _parse_tav_datetime(dt_str: str | None) -> datetime | None:
    """'08.03.2026 09:55' formatını datetime'a çevirir."""
    if not dt_str or not dt_str.strip():
        return None
    try:
        # TAV genelde 'DD.MM.YYYY HH:MM' formatında veriyor
        dt = datetime.strptime(dt_str.strip(), "%d.%m.%Y %H:%M")
        return dt.replace(tzinfo=TZ_TR)
    except ValueError:
        return None


class TavScraper(BaseScraper):
    """
    TAV Havalimanları Scraper.
    ADB, ESB, BJV, GZP için istek atar.
    """

    SOURCE = SourceEnum.TAV
    AIRPORT_CODES = list(TAV_DOMAINS.keys())

    async def fetch_flights(
        self,
        session: aiohttp.ClientSession,
        airport_code: str,
        flight_date: date,
    ) -> list[FlightData]:
        """Base class bu metodu kullanarak her havalimanı için çağıracaktır."""
        
        domain = TAV_DOMAINS.get(airport_code)
        if not domain:
            logger.error(f"[tav] {airport_code} için domain bulunamadı!")
            return []

        all_flights: list[FlightData] = []
        
        # 1. ARR (Geliş)
        arr_url = f"https://{domain}/Home/getCurrentFlights?flightLeg=ARR"
        arr_data = await self._fetch_leg(session, arr_url, airport_code, DirectionEnum.ARRIVAL, flight_date)
        all_flights.extend(arr_data)
        
        await asyncio.sleep(REQUEST_DELAY)
        
        # 2. DEP (Gidiş)
        dep_url = f"https://{domain}/Home/getCurrentFlights?flightLeg=DEP"
        dep_data = await self._fetch_leg(session, dep_url, airport_code, DirectionEnum.DEPARTURE, flight_date)
        all_flights.extend(dep_data)

        return all_flights

    async def _fetch_leg(
        self,
        session: aiohttp.ClientSession,
        url: str,
        airport_code: str,
        direction: DirectionEnum,
        target_date: date,
    ) -> list[FlightData]:
        
        proxy = self.proxy_manager.get_proxy_dict()
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, proxy=proxy, timeout=15) as resp:
                resp.raise_for_status()
                json_data = await resp.json()
        except Exception as e:
            logger.error(f"[tav] {airport_code} {direction.value} API hatası: {e}")
            return []

        if not json_data or not json_data.get("result"):
            logger.warning(f"[tav] {airport_code} {url} geçerli JSON döndürmedi.")
            return []

        flights_list = json_data.get("data", {}).get("flights", [])
        parsed_flights = []

        for raw in flights_list:
            try:
                flight = self._parse_flight(raw, airport_code, direction, target_date)
                if flight:
                    parsed_flights.append(flight)
            except Exception as e:
                logger.debug(f"[tav] Parse hatası: {e}")

        logger.info(f"[tav] {airport_code} {direction.value}: {len(parsed_flights)} uçuş bulundu.")
        return parsed_flights

    def _parse_flight(
        self,
        raw: dict,
        airport_code: str,
        direction: DirectionEnum,
        target_date: date,
    ) -> FlightData | None:
        """JSON objesini FlightData'ya çevirir."""

        airline_iata = (raw.get("airlineIata") or "").strip()
        flight_num_only = (raw.get("flightNumber") or "").strip()
        
        # Birleştir: 'VF' ve '3013' -> 'VF3013'
        flight_number = f"{airline_iata}{flight_num_only}"
        if not flight_number:
            return None

        # Zamanlar
        # TAV JSON'ı stad (scheduled), etad (estimated), atad (actual) verir
        scheduled = _parse_tav_datetime(raw.get("stad"))
        if not scheduled:
            return None
            
        estimated = _parse_tav_datetime(raw.get("etad"))
        actual = _parse_tav_datetime(raw.get("atad"))

        flight_d = scheduled.date()

        # Durum
        remark_dict = raw.get("remark", {})
        remark_en = remark_dict.get("remarkEn", "")
        remark_tr = remark_dict.get("remarkTr", "")
        status = _normalize_status(remark_en)

        # Şehir/Havalimanı kodları
        path_dict = raw.get("path", {})
        origin_dict = path_dict.get("origin", {})
        dest_dict = path_dict.get("destination", {})

        return FlightData(
            flight_number=flight_number,
            flight_date=flight_d,
            airport_code=airport_code,
            direction=direction,
            source=SourceEnum.TAV,
            airport_name=None, # TAV için ad doldurmasak da olur veya config'den çekilir
            airline_code=airline_iata if airline_iata else None,
            airline_name=raw.get("airlineName"),
            origin_code=origin_dict.get("originIata"),
            origin_city=origin_dict.get("originEn") or origin_dict.get("originTr"),
            destination_code=dest_dict.get("destinationIata"),
            destination_city=dest_dict.get("destinationEn") or dest_dict.get("destinationTr"),
            scheduled_time=scheduled,
            estimated_time=estimated,
            actual_time=actual,
            status=status,
            status_detail=remark_tr if remark_tr else remark_en, # Tercihen Türkçe detay
            gate=raw.get("gate"),
            terminal=None,
        )

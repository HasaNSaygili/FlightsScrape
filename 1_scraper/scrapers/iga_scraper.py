"""
iga_scraper.py
──────────────
İGA — İstanbul Havalimanı (IST).

API Keşfi:
  POST https://www.istairport.com/umbraco/api/FlightInfo/GetFlightStatusBoard

  Form Parametreleri:
    - nature:          0 (Geliş/Arrival), 1 (Gidiş/Departure)
    - pageSize:        Sayfa başına uçuş sayısı (varsayılan 10, büyütülebilir)
    - isInternational: 0 (İç Hat), 1 (Dış Hat)
    - date:            Başlangıç tarihi (boş = bugün)
    - endDate:         Bitiş tarihi (boş = bugün)
    - culture:         'en' veya 'tr'
    - searchTerm:      Uçuş numarası filtresi (boş = tümü)
    - clickedButton:   Boş bırakılır

  Pagination:
    - Response'daki "showMoreFlightsBtn" true ise daha fazla veri var
    - "newStartDate" ile sonraki sayfa çekilir (date parametresine atanır)

  Dönen JSON Örneği:
    {
      "flightNumber": "TK2311",
      "airlineCode": "TK",
      "airlineName": "Turkish Airlines",
      "fromCityCode": "ADB",
      "fromCityName": "IZMIR",
      "toCityCode": "IST",
      "toCityName": "ISTANBUL",
      "scheduledDatetime": "2026-03-08T10:15:00",
      "estimatedDatetime": "2026-03-08T09:45:00",
      "gate": "",
      "carousel": "1A",
      "counter": "",
      "remark": "Landed",
      "remarkCode": "LAN",
      "codeshare": ["JU8034", "SQ6215"]
    }
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta

import aiohttp

from core.flight_model import (
    FlightData,
    DirectionEnum,
    FlightStatusEnum,
    SourceEnum,
)
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# ─── Türkiye saat dilimi ──────────────────────────────────────────────
TZ_TR = timezone(timedelta(hours=3))

# ─── API Sabitleri ────────────────────────────────────────────────────
API_URL = "https://www.istairport.com/umbraco/api/FlightInfo/GetFlightStatusBoard"

DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://www.istairport.com",
    "referer": "https://www.istairport.com/en/passenger/flight-info/departure",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}

# Sayfa başına çekilecek uçuş sayısı (mümkün olduğunca büyük)
PAGE_SIZE = 200

# Maksimum sayfalama (sonsuz loop koruması)
MAX_PAGES = 20

# ─── Durum Normalizasyonu ─────────────────────────────────────────────

REMARK_CODE_MAP: dict[str, FlightStatusEnum] = {
    "LAN": FlightStatusEnum.LANDED,
    "DEP": FlightStatusEnum.DEPARTED,
    "SCT": FlightStatusEnum.ON_TIME,
    "EAR": FlightStatusEnum.ON_TIME,      # Erken = zamanında
    "DLY": FlightStatusEnum.DELAYED,
    "CNL": FlightStatusEnum.CANCELLED,
    "BRD": FlightStatusEnum.BOARDING,
    "GTO": FlightStatusEnum.BOARDING,      # Gate Open
    "GTC": FlightStatusEnum.BOARDING,      # Gate Closing
    "FBR": FlightStatusEnum.BOARDING,      # Final Boarding
    "DVR": FlightStatusEnum.DIVERTED,
    "CHK": FlightStatusEnum.SCHEDULED,     # Check-in Open
}


def _normalize_status(remark_code: str | None, remark: str | None) -> FlightStatusEnum:
    """remarkCode ile durumu normalize eder."""
    if remark_code and remark_code in REMARK_CODE_MAP:
        return REMARK_CODE_MAP[remark_code]
    if remark:
        lower = remark.lower()
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
        if "on time" in lower or "early" in lower:
            return FlightStatusEnum.ON_TIME
    return FlightStatusEnum.UNKNOWN


def _parse_datetime(dt_str: str | None) -> datetime | None:
    """ISO format datetime string'i parse eder. '2026-03-08T10:15:00' → datetime"""
    if not dt_str or not dt_str.strip():
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_TR)
        return dt
    except (ValueError, AttributeError):
        return None


class IgaScraper(BaseScraper):
    """
    İGA scraper — İstanbul Havalimanı (IST).
    Gelen ve giden, iç hat ve dış hat uçuşlarını sayfalayarak çeker.
    """

    SOURCE = SourceEnum.IGA
    AIRPORT_CODES = ["IST"]

    async def run(self, flight_date: date | None = None) -> int:
        """
        IST için 4 kombinasyon çeker:
          nature=0, isInternational=0  (Geliş İç Hat)
          nature=0, isInternational=1  (Geliş Dış Hat)
          nature=1, isInternational=0  (Gidiş İç Hat)
          nature=1, isInternational=1  (Gidiş Dış Hat)
        """
        target_date = flight_date or date.today()
        total = 0

        combinations = [
            (0, 0, DirectionEnum.ARRIVAL),   # Geliş İç Hat
            (0, 1, DirectionEnum.ARRIVAL),   # Geliş Dış Hat
            (1, 0, DirectionEnum.DEPARTURE), # Gidiş İç Hat
            (1, 1, DirectionEnum.DEPARTURE), # Gidiş Dış Hat
        ]

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers=DEFAULT_HEADERS,
        ) as session:
            for nature, is_intl, direction in combinations:
                try:
                    flights = await self._fetch_all_pages(
                        session=session,
                        nature=nature,
                        is_international=is_intl,
                        direction=direction,
                        target_date=target_date,
                    )
                    if flights:
                        from core.db_client import upsert_flights
                        count = await upsert_flights(flights)
                        total += count
                        hat = "Dış Hat" if is_intl else "İç Hat"
                        yon = "Geliş" if nature == 0 else "Gidiş"
                        logger.info(f"[iga] IST {yon} {hat}: {count} uçuş yazıldı")
                except Exception as e:
                    logger.error(f"[iga] IST nature={nature} intl={is_intl}: {e}", exc_info=True)

        logger.info(f"[iga] Toplam: {total} uçuş kaydı yazıldı")
        return total

    async def _fetch_all_pages(
        self,
        session: aiohttp.ClientSession,
        nature: int,
        is_international: int,
        direction: DirectionEnum,
        target_date: date,
    ) -> list[FlightData]:
        """Tüm sayfaları iterate ederek uçuşları toplar."""

        all_flights: list[FlightData] = []
        seen_flight_ids: set[str] = set()
        current_date = ""  # Boş = bugünden başla
        page = 0

        while page < MAX_PAGES:
            page += 1
            proxy = self.proxy_manager.get_proxy_dict()

            form_data = {
                "nature": str(nature),
                "searchTerm": "",
                "pageSize": str(PAGE_SIZE),
                "isInternational": str(is_international),
                "date": current_date,
                "endDate": "",
                "culture": "en",
                "clickedButton": "",
            }

            try:
                async with session.post(
                    API_URL,
                    data=form_data,
                    proxy=proxy,
                ) as resp:
                    resp.raise_for_status()
                    json_data = await resp.json()
            except Exception as e:
                logger.warning(f"[iga] Sayfa {page} hatası: {e}")
                break

            # Response yapısı: { status, message, result: { data: { flights: [...] }, showMoreFlightsBtn, newStartDate } }
            if not json_data or not json_data.get("status"):
                break

            result = json_data.get("result", {})
            data = result.get("data", {})
            raw_flights = data.get("flights", [])

            if not raw_flights:
                break
                
            new_flights_count = 0

            for raw in raw_flights:
                try:
                    flight_id_str = str(raw.get("id", ""))
                    if not flight_id_str or flight_id_str in seen_flight_ids:
                        continue
                        
                    seen_flight_ids.add(flight_id_str)
                    flight = self._parse_flight(raw, direction, target_date)
                    if flight:
                        all_flights.append(flight)
                        new_flights_count += 1
                except Exception as e:
                    logger.debug(f"[iga] Parse hatası: {e}")
                    
            if new_flights_count == 0:
                break # Infinite loop protection

            # Pagination kontrolü
            show_more = result.get("showMoreFlightsBtn", False)
            new_start = result.get("newStartDate", "")

            if not show_more or not new_start:
                break

            current_date = new_start

        return all_flights

    def _parse_flight(
        self,
        raw: dict,
        direction: DirectionEnum,
        target_date: date,
    ) -> FlightData | None:
        """Tek bir İGA JSON uçuş kaydını FlightData'ya dönüştürür."""

        flight_number = raw.get("flightNumber", "").strip()
        if not flight_number:
            return None

        # Zamanlar
        scheduled = _parse_datetime(raw.get("scheduledDatetime"))
        if scheduled is None:
            return None

        estimated = _parse_datetime(raw.get("estimatedDatetime"))

        # Tarihi scheduled_time'dan al
        flight_d = scheduled.date()

        # Durum
        remark_code = raw.get("remarkCode", "")
        remark_text = raw.get("remark", "")
        status = _normalize_status(remark_code, remark_text)

        return FlightData(
            flight_number=flight_number,
            flight_date=flight_d,
            airport_code="IST",
            direction=direction,
            source=SourceEnum.IGA,
            airport_name="İstanbul Havalimanı",
            airline_code=raw.get("airlineCode"),
            airline_name=raw.get("airlineName"),
            origin_code=raw.get("fromCityCode"),
            origin_city=raw.get("fromCityName"),
            destination_code=raw.get("toCityCode"),
            destination_city=raw.get("toCityName"),
            scheduled_time=scheduled,
            estimated_time=estimated,
            status=status,
            status_detail=remark_text if remark_text else None,
            gate=raw.get("gate") if raw.get("gate") else None,
            terminal=None,
        )

    async def fetch_flights(
        self,
        session: aiohttp.ClientSession,
        airport_code: str,
        flight_date: date,
    ) -> list[FlightData]:
        """BaseScraper uyumluluğu — İGA kendi run() metodunu kullanır."""
        raise NotImplementedError(
            "İGA scraper kendi run() metodunu kullanır, fetch_flights çağrılmamalı"
        )

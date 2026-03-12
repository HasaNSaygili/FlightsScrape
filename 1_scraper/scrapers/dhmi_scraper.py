"""
dhmi_scraper.py
───────────────
DHMİ (Devlet Hava Meydanları İşletmesi) — 40+ Anadolu havalimanı.

API Keşfi:
  - Havalimanı Listesi : GET https://flightwebsvc.dhmi.gov.tr/api/Airports
  - Uçuş Verileri      : GET https://flightwebsvc.dhmi.gov.tr/api/Flights/{AirportID}/{Direction}/{Region}
    - Direction: DA (Geliş/Arrival), DD (Gidiş/Departure)
    - Region:    D (İç Hat/Domestic), I (Dış Hat/International)

  Zorunlu Header:
    ktoken: 7s1nN3ItzoPlH7iw/YwPF///Ru9pZaqeBhP303OJX/zL9iUa+UQjFYooO47P2HMBjeAJnjcvt3QxtrsZxcYUug==
    referer: https://dhmi.gov.tr/
    origin: https://dhmi.gov.tr

  Dönen JSON Örneği:
    {
      "Number": "TK2126",
      "Date": "08.03.2026",
      "SrcDst": "İSTANBUL",
      "Airline": "Turkish Airlines",
      "Planned": "09:10",
      "Estimated": "09:10",
      "Gate": "21",
      "Status": "İNDİ - LANDED",
      "ColorCode": "fill-green",
      "Active": 0
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
BASE_URL = "https://flightwebsvc.dhmi.gov.tr/api"
AIRPORTS_URL = f"{BASE_URL}/Airports"
FLIGHTS_URL = f"{BASE_URL}/Flights"  # /{AirportID}/{Direction}/{Region}

REQUIRED_HEADERS = {
    "ktoken": "7s1nN3ItzoPlH7iw/YwPF///Ru9pZaqeBhP303OJX/zL9iUa+UQjFYooO47P2HMBjeAJnjcvt3QxtrsZxcYUug==",
    "referer": "https://dhmi.gov.tr/",
    "origin": "https://dhmi.gov.tr",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}

# DHMİ Havalimanları: İsme göre IATA kodu bulma (NAME-BASED LOOKUP)
# Statik ID map yerine isim kullanır — DHMI API'nin ID sırası değişebilir!
DHMI_NAME_TO_IATA: dict[str, str] = {
    "ankara esenboga": "ESB",
    "istanbul havalimanı": "IST",
    "adana": "ADA",
    "adıyaman": "ADF",
    "antalya": "AYT",
    "ağrı": "AJI",
    "afyon": "AFY",
    "amasya": "UAB",
    "batman": "BAL",
    "balıkesir": "BZI",
    "bingöl": "BGG",
    "bursa": "BXN",
    "çanakkale": "CKZ",
    "denizli": "DNZ",
    "diyarbakır": "DIY",
    "erzincan": "ERC",
    "erzurum": "ERZ",
    "elazığ": "EZS",
    "gaziantep": "GZT",
    "hatay": "HTY",
    "iğdır": "IGD",
    "isparta": "ISE",
    "kars": "KSY",
    "kastamonu": "KFS",
    "konya": "KYA",
    "kahramanmaraş": "KCM",
    "malatya": "MLX",
    "muş": "MSR",
    "sinop": "NOP",
    "sivas": "VAS",
    "şanlıurfa": "SFQ",
    "mardin": "MQM",
    "trabzon": "TZX",
    "uşak": "USQ",
    "van": "VAN",
    "samsun": "SZF",
    "zonguldak": "ONQ",
    "ordu giresun": "OGU",
    "şırnak": "NKT",
    "tokat": "TJK",
    "gökçeada": "GKD",
    "hakkari-yüksekova": "YKO",
    "yüksekova": "YKO",
    "rize artvin": "RIZ",
    "rize": "RIZ",
    "gazipaşa": "GZP",
    "kapadokya": "NAV",
    "nevşehir": "NAV",
    "tekirdag": "TEQ",
    "milas bodrum": "BJV",
    "muğla dalaman": "DLM",
    "dalaman": "DLM",
    "İzmir adnan menderes": "ADB",
    "kayseri": "ASR",
    "hakkari": "YKO",
    "çıldır": "CII",
}


def _name_to_iata(airport_name: str) -> str | None:
    """Havalimanı adından IATA kodunu bulur (case-insensitive, kısmi eşleşme)."""
    if not airport_name:
        return None
    name_lower = airport_name.lower().strip()
    # Tam eşleşme önce
    if name_lower in DHMI_NAME_TO_IATA:
        return DHMI_NAME_TO_IATA[name_lower]
    # Kısmi eşleşme
    for key, iata in DHMI_NAME_TO_IATA.items():
        if key in name_lower:
            return iata
    return None


# Yedek statik ID → IATA map (sadece isim bazlı lookup başarısız olursa)
DHMI_AIRPORT_MAP: dict[int, dict] = {
    1: {"iata": "ESB", "name": "Ankara Esenboğa Havalimanı"},
    2: {"iata": "ADA", "name": "Adana Havalimanı"},
    3: {"iata": "ADF", "name": "Adıyaman Havalimanı"},
    4: {"iata": "AYT", "name": "Antalya Havalimanı"},
    5: {"iata": "AJI", "name": "Ağrı Ahmed-i Hani Havalimanı"},
    6: {"iata": "AFY", "name": "Afyon-Kocatepe Havalimanı"},
    7: {"iata": "UAB", "name": "Amasya-Merzifon Havalimanı"},
    8: {"iata": "BAL", "name": "Batman Havalimanı"},
    9: {"iata": "BZI", "name": "Balıkesir Havalimanı"},
    10: {"iata": "BGG", "name": "Bingöl Havalimanı"},
    11: {"iata": "BXN", "name": "Bursa Yenişehir Havalimanı"},
    12: {"iata": "CKZ", "name": "Çanakkale Havalimanı"},
    13: {"iata": "DNZ", "name": "Denizli Çardak Havalimanı"},
    14: {"iata": "DIY", "name": "Diyarbakır Havalimanı"},
    15: {"iata": "ERC", "name": "Erzincan Havalimanı"},
    16: {"iata": "ERZ", "name": "Erzurum Havalimanı"},
    17: {"iata": "EZS", "name": "Elazığ Havalimanı"},
    18: {"iata": "GZT", "name": "Gaziantep Havalimanı"},
    19: {"iata": "HTY", "name": "Hatay Havalimanı"},
    20: {"iata": "IGD", "name": "Iğdır Havalimanı"},
    21: {"iata": "ISE", "name": "Isparta Süleyman Demirel Havalimanı"},
    22: {"iata": "KSY", "name": "Kars Harakani Havalimanı"},
    23: {"iata": "KFS", "name": "Kastamonu Havalimanı"},
    24: {"iata": "KYA", "name": "Konya Havalimanı"},
    25: {"iata": "KCM", "name": "Kahramanmaraş Havalimanı"},
    26: {"iata": "MLX", "name": "Malatya Erhaç Havalimanı"},
    27: {"iata": "MSR", "name": "Muş Havalimanı"},
    28: {"iata": "NOP", "name": "Sinop Havalimanı"},
    29: {"iata": "VAS", "name": "Sivas Nuri Demirağ Havalimanı"},
    30: {"iata": "GNY", "name": "Şanlıurfa GAP Havalimanı"},
    31: {"iata": "TZX", "name": "Trabzon Havalimanı"},
    32: {"iata": "USQ", "name": "Uşak Havalimanı"},
    33: {"iata": "VAN", "name": "Van Ferit Melen Havalimanı"},
    34: {"iata": "SZF", "name": "Samsun Çarşamba Havalimanı"},
    35: {"iata": "ONQ", "name": "Zonguldak Havalimanı"},
    36: {"iata": "EDO", "name": "Balıkesir Koca Seyit Havalimanı"},
    37: {"iata": "OGU", "name": "Ordu-Giresun Havalimanı"},
    38: {"iata": "NKT", "name": "Şırnak Havalimanı"},
    39: {"iata": "TJK", "name": "Tokat Havalimanı"},
    40: {"iata": "GKD", "name": "Gökçeada Havalimanı"},
    41: {"iata": "YKO", "name": "Hakkari-Yüksekova Havalimanı"},
    42: {"iata": "RIZ", "name": "Rize-Artvin Havalimanı"},
    43: {"iata": "SFQ", "name": "Şanlıurfa Havalimanı"},
    44: {"iata": "CII", "name": "Çıldır Havalimanı"},
}


# ─── Durum Normalizasyonu ─────────────────────────────────────────────

STATUS_MAP: dict[str, FlightStatusEnum] = {
    # Türkçe
    "indi": FlightStatusEnum.LANDED,
    "iniş": FlightStatusEnum.LANDED,
    "kalktı": FlightStatusEnum.DEPARTED,
    "kalkış": FlightStatusEnum.DEPARTED,
    "rötarlı": FlightStatusEnum.DELAYED,
    "rötar": FlightStatusEnum.DELAYED,
    "gecikme": FlightStatusEnum.DELAYED,
    "iptal": FlightStatusEnum.CANCELLED,
    "zamanında": FlightStatusEnum.ON_TIME,
    "bekleniyor": FlightStatusEnum.SCHEDULED,
    "kapıda": FlightStatusEnum.BOARDING,
    # İngilizce
    "landed": FlightStatusEnum.LANDED,
    "departed": FlightStatusEnum.DEPARTED,
    "delayed": FlightStatusEnum.DELAYED,
    "cancelled": FlightStatusEnum.CANCELLED,
    "canceled": FlightStatusEnum.CANCELLED,
    "on time": FlightStatusEnum.ON_TIME,
    "scheduled": FlightStatusEnum.SCHEDULED,
    "boarding": FlightStatusEnum.BOARDING,
    "diverted": FlightStatusEnum.DIVERTED,
}


def _normalize_status(raw: str | None) -> FlightStatusEnum:
    """Ham durum metnini normalize eder. Örn: 'İNDİ - LANDED' → LANDED"""
    if not raw:
        return FlightStatusEnum.UNKNOWN

    lower = raw.lower().strip()
    for keyword, status in STATUS_MAP.items():
        if keyword in lower:
            return status
    return FlightStatusEnum.UNKNOWN


def _parse_time(date_str: str, time_str: str | None) -> datetime | None:
    """
    DHMİ formatını datetime'a çevirir.
    date_str: '08.03.2026'
    time_str: '09:10' veya None
    """
    if not time_str or not time_str.strip():
        return None
    try:
        combined = f"{date_str} {time_str.strip()}"
        dt = datetime.strptime(combined, "%d.%m.%Y %H:%M")
        return dt.replace(tzinfo=TZ_TR)
    except (ValueError, AttributeError):
        return None


def _extract_airline_code(flight_number: str) -> str | None:
    """Uçuş numarasından havayolu kodunu çıkarır. 'TK2126' → 'TK'"""
    code = ""
    for ch in flight_number:
        if ch.isalpha():
            code += ch
        else:
            break
    return code.upper() if code else None


class DhmiScraper(BaseScraper):
    """
    DHMİ scraper — tek script ile 40+ Anadolu havalimanının
    gelen ve giden uçuş verilerini çeker.
    """

    SOURCE = SourceEnum.DHMI

    # BaseScraper.AIRPORT_CODES yerine DHMI'nin kendi ID sistemini kullanıyoruz
    AIRPORT_CODES: list[str] = []  # Kullanılmıyor, kendi run() metodumuz var

    async def run(self, flight_date: date | None = None) -> int:
        """
        Tüm DHMİ havalimanları için veri çeker.
        Önce /api/Airports'tan güncel listeyi alır,
        sonra her havalimanı için 4 kombinasyon dener:
          DA/D (Geliş İç Hat), DA/I (Geliş Dış Hat)
          DD/D (Gidiş İç Hat), DD/I (Gidiş Dış Hat)
        """
        target_date = flight_date or date.today()
        total = 0

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers=REQUIRED_HEADERS,
        ) as session:
            # 1) Havalimanı listesini çek
            airports = await self._fetch_airports(session)
            if not airports:
                logger.error("[dhmi] Havalimanı listesi alınamadı, statik map kullanılacak")
                airports = [
                    {"Id": aid, "Name": data["name"]}
                    for aid, data in DHMI_AIRPORT_MAP.items()
                ]

            logger.info(f"[dhmi] {len(airports)} havalimanı bulundu")

            # 2) Her havalimanı × yön × hat kombinasyonu
            combinations = [
                ("DA", "D"),  # Geliş İç Hat
                ("DA", "I"),  # Geliş Dış Hat
                ("DD", "D"),  # Gidiş İç Hat
                ("DD", "I"),  # Gidiş Dış Hat
            ]

            for airport in airports:
                airport_id = airport["Id"]
                airport_name = airport.get("Name", "")

                # IATA kodunu bul
                iata = self._get_iata(airport_id, airport_name)

                for direction_code, region_code in combinations:
                    try:
                        flights = await self._fetch_flights_for_combo(
                            session=session,
                            airport_id=airport_id,
                            airport_name=airport_name,
                            iata=iata,
                            direction_code=direction_code,
                            region_code=region_code,
                            target_date=target_date,
                        )
                        if flights:
                            from core.db_client import upsert_flights
                            count = await upsert_flights(flights)
                            total += count
                    except Exception as e:
                        logger.error(
                            f"[dhmi] {iata} {direction_code}/{region_code}: {e}",
                            exc_info=True,
                        )

            logger.info(f"[dhmi] Toplam: {total} uçuş kaydı yazıldı")
        return total

    async def _fetch_airports(self, session: aiohttp.ClientSession) -> list[dict]:
        """DHMİ'nin havalimanı listesini çeker."""
        proxy = self.proxy_manager.get_proxy_dict()
        try:
            async with session.get(AIRPORTS_URL, proxy=proxy) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as e:
            logger.warning(f"[dhmi] Airports endpoint hatası: {e}")
            return []

    async def _fetch_flights_for_combo(
        self,
        session: aiohttp.ClientSession,
        airport_id: int,
        airport_name: str,
        iata: str,
        direction_code: str,
        region_code: str,
        target_date: date,
    ) -> list[FlightData]:
        """Tek bir havalimanı/yön/hat kombinasyonu için uçuşları çeker ve parse eder."""

        url = f"{FLIGHTS_URL}/{airport_id}/{direction_code}/{region_code}"
        proxy = self.proxy_manager.get_proxy_dict()

        try:
            async with session.get(url, proxy=proxy) as resp:
                resp.raise_for_status()
                raw_flights = await resp.json()
        except Exception as e:
            logger.warning(f"[dhmi] {iata} {direction_code}/{region_code}: {e}")
            return []

        if not raw_flights or not isinstance(raw_flights, list):
            return []

        direction = (
            DirectionEnum.ARRIVAL if direction_code == "DA" else DirectionEnum.DEPARTURE
        )

        flights: list[FlightData] = []
        for raw in raw_flights:
            try:
                flight = self._parse_flight(
                    raw=raw,
                    airport_code=iata,
                    airport_name=airport_name,
                    direction=direction,
                    target_date=target_date,
                )
                if flight:
                    flights.append(flight)
            except Exception as e:
                logger.debug(f"[dhmi] Parse hatası: {e} — raw: {raw}")

        return flights

    def _parse_flight(
        self,
        raw: dict,
        airport_code: str,
        airport_name: str,
        direction: DirectionEnum,
        target_date: date,
    ) -> FlightData | None:
        """Tek bir ham JSON uçuş kaydını FlightData'ya dönüştürür."""

        flight_number = raw.get("Number", "").strip()
        if not flight_number:
            return None

        date_str = raw.get("Date", target_date.strftime("%d.%m.%Y"))

        # Tarihi parse et
        try:
            parsed_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            parsed_date = target_date

        # Saatleri parse et
        scheduled = _parse_time(date_str, raw.get("Planned"))
        if scheduled is None:
            # scheduled_time zorunlu — yoksa atla
            return None

        estimated = _parse_time(date_str, raw.get("Estimated"))
        actual = _parse_time(date_str, raw.get("Actual"))

        # Durum normalizasyonu
        raw_status = raw.get("Status", "")
        status = _normalize_status(raw_status)

        # Rota bilgisi: SrcDst alanı kalkış/varış şehrini verir
        src_dst = raw.get("SrcDst", "")

        # direction'a göre origin/destination belirle
        if direction == DirectionEnum.ARRIVAL:
            origin_city = src_dst
            destination_city = airport_name.replace(" Havalimanı", "")
        else:
            origin_city = airport_name.replace(" Havalimanı", "")
            destination_city = src_dst

        return FlightData(
            flight_number=flight_number,
            flight_date=parsed_date,
            airport_code=airport_code,
            direction=direction,
            source=SourceEnum.DHMI,
            airport_name=airport_name,
            airline_code=_extract_airline_code(flight_number),
            airline_name=raw.get("Airline"),
            origin_city=origin_city if origin_city else None,
            destination_city=destination_city if destination_city else None,
            scheduled_time=scheduled,
            estimated_time=estimated,
            actual_time=actual,
            status=status,
            status_detail=raw_status if raw_status else None,
            gate=raw.get("Gate"),
            terminal=raw.get("Terminal"),
        )

    def _get_iata(self, airport_id: int, airport_name: str) -> str:
        """Havalimanı adından IATA kodunu çözer. İsim bazlı lookup önceliklidir."""
        # 1) İsim bazlı lookup (en güvenilir — API ID'leri değişse bile çalışır)
        iata_from_name = _name_to_iata(airport_name)
        if iata_from_name:
            return iata_from_name
        # 2) Statik ID map'e bak (yedek)
        if airport_id in DHMI_AIRPORT_MAP:
            logger.debug(
                f"[dhmi] İsim bulunamadı, statik map kullanıldı: id={airport_id} ({airport_name})"
            )
            return DHMI_AIRPORT_MAP[airport_id]["iata"]
        # 3) Hiçbiri eşleşmezse ID tabanlı fallback
        logger.warning(
            f"[dhmi] Bilinmeyen havalimanı: id={airport_id}, name='{airport_name}' "
            f"→ 'DHM{airport_id}' kullanılıyor"
        )
        return f"DHM{airport_id}"

    async def fetch_flights(
        self,
        session: aiohttp.ClientSession,
        airport_code: str,
        flight_date: date,
    ) -> list[FlightData]:
        """BaseScraper uyumluluğu için — DHMİ kendi run() metodunu kullanır."""
        raise NotImplementedError(
            "DHMİ scraper kendi run() metodunu kullanır, fetch_flights çağrılmamalı"
        )

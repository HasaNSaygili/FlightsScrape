"""
heas_scraper.py
───────────────
HEAŞ — Sabiha Gökçen Havalimanı (SAW).

API Keşfi:
  SAW web sitesi modern bir JSON API kullanmıyor. Bunun yerine ASP.NET WebForms UpdatePanel
  mantığıyla HTML tablosunu (Telerik RadAjax) güncelliyor.
  Bu yüzden uçuş verilerini doğrudan HTML içindeki <table class="feedtable"> tag'inden
  BeautifulSoup ile parse ediyoruz.

  - İstek Atılan URL: https://www.sabihagokcen.aero/yolcu-ve-ziyaretciler/yolcu-rehberi/ucus-bilgi-ekrani
  - Gelen/Giden state'ini değiştirmek için __EVENTTARGET ve __VIEWSTATE parametreleri simüle edilir
  veya sayfaya direkt ilk girildiğinde gelen default tablo parse edilir.
  Ancak en stabili sayfayı fetch edip table içini okumaktır.
"""

from __future__ import annotations

import logging
import asyncio
from datetime import date, datetime, timezone, timedelta

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
SAW_URL = "https://www.sabihagokcen.aero/yolcu-ve-ziyaretciler/yolcu-rehberi/ucus-bilgi-ekrani"

DEFAULT_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    # Orijinal Dili belirler
    "cookie": "language=tr",
}

# ─── Durum Normalizasyonu ─────────────────────────────────────────────

STATUS_MAP: dict[str, FlightStatusEnum] = {
    "indi": FlightStatusEnum.LANDED,
    "kalktı": FlightStatusEnum.DEPARTED,
    "gecikmeli": FlightStatusEnum.DELAYED,
    "iptal": FlightStatusEnum.CANCELLED,
    "kapi iptal": FlightStatusEnum.CANCELLED,
    "kapı açıldı": FlightStatusEnum.BOARDING,
    "kapı kapandı": FlightStatusEnum.BOARDING,
    "kapi acildi": FlightStatusEnum.BOARDING,
    "kapi kapandi": FlightStatusEnum.BOARDING,
    "biniş": FlightStatusEnum.BOARDING,
    "bagaj": FlightStatusEnum.LANDED, # Bagaj bekleniyorsa inmiştir
    "zamanında": FlightStatusEnum.ON_TIME,
    "zamaninda": FlightStatusEnum.ON_TIME,
}

def _normalize_status(raw: str | None) -> FlightStatusEnum:
    """HTML tablosundan gelen Türkçe durumu normalize eder."""
    if not raw:
        return FlightStatusEnum.UNKNOWN

    lower = raw.lower().strip()
    for keyword, status in STATUS_MAP.items():
        if keyword in lower:
            return status

    # Eğer sadece saat varsa (örn: "09:30") bu tahmini saattir, uçuş bekleniyordur
    if ":" in lower and len(lower) <= 5:
        return FlightStatusEnum.SCHEDULED

    return FlightStatusEnum.UNKNOWN


class HeasScraper(BaseScraper):
    """
    HEAŞ scraper — Sabiha Gökçen Havalimanı (SAW).
    ASP.NET tablosunu parse eder.
    """

    SOURCE = SourceEnum.HEAS
    AIRPORT_CODES = ["SAW"]

    async def run(self, flight_date: date | None = None) -> int:
        """
        SAW için ASP.NET formunu simüle ederek Geliş ve Gidiş tablolarını çeker.
        """
        target_date = flight_date or date.today()
        total = 0

        # İstekler arası delay
        await asyncio.sleep(REQUEST_DELAY)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers=DEFAULT_HEADERS,
        ) as session:
            try:
                # 1. İlk GET İsteği - Geliş veya Gidiş (default Geliş açılır genelde)
                proxy = self.proxy_manager.get_proxy_dict()
                async with session.get(SAW_URL, proxy=proxy) as resp:
                    resp.raise_for_status()
                    html_content = await resp.text()

                soup = BeautifulSoup(html_content, "html.parser")

                # State'leri topla (__VIEWSTATE vs)
                viewstate = self._extract_input_value(soup, "__VIEWSTATE")
                viewstategenerator = self._extract_input_value(soup, "__VIEWSTATEGENERATOR")
                eventvalidation = self._extract_input_value(soup, "__EVENTVALIDATION")

                # Bulunan ilk tabloyu parse et (Öntanımlı olarak Geliş veya Gidiş)
                # SAW sitesinde genelde ilk yüklemede ikisi bir arada gizli divlerde gelmez.
                # Hangi state'te olduğumuzu anlamak için aktif tab'a bakarız:
                active_tab_elem = soup.select_one(".page-tabs .active")
                direction = DirectionEnum.ARRIVAL
                if active_tab_elem and "giden" in active_tab_elem.text.lower():
                    direction = DirectionEnum.DEPARTURE

                flights_batch1 = self._parse_html_table(soup, direction, target_date)
                if flights_batch1:
                    from core.db_client import upsert_flights
                    count1 = await upsert_flights(flights_batch1)
                    total += count1
                    dir_str = "Gidiş" if direction == DirectionEnum.DEPARTURE else "Geliş"
                    logger.info(f"[heas] SAW İlk yüklü ({dir_str}): {count1} uçuş yazıldı")

                # 2. İkinci Yön İçin POST isteği at
                # Eğer ilk yön ARRIVAL ise DEPARTURE için POST atalım
                target_direction = DirectionEnum.DEPARTURE if direction == DirectionEnum.ARRIVAL else DirectionEnum.ARRIVAL
                event_target = "ctl00$ContentPlaceHolder1$lbDepartures" if target_direction == DirectionEnum.DEPARTURE else "ctl00$ContentPlaceHolder1$lbArrivals"

                await asyncio.sleep(REQUEST_DELAY)

                payload = {
                    "__EVENTTARGET": event_target,
                    "__EVENTARGUMENT": "",
                    "__VIEWSTATE": viewstate,
                    "__VIEWSTATEGENERATOR": viewstategenerator,
                    "__EVENTVALIDATION": eventvalidation,
                }

                # ASP.NET AJAX isteği
                ajax_headers = DEFAULT_HEADERS.copy()
                ajax_headers["content-type"] = "application/x-www-form-urlencoded"
                ajax_headers["x-microsoftajax"] = "Delta=true"

                async with session.post(SAW_URL, data=payload, headers=ajax_headers, proxy=proxy) as resp2:
                    resp2.raise_for_status()
                    html_content2 = await resp2.text()

                soup2 = BeautifulSoup(html_content2, "html.parser")
                flights_batch2 = self._parse_html_table(soup2, target_direction, target_date)

                if flights_batch2:
                    from core.db_client import upsert_flights
                    count2 = await upsert_flights(flights_batch2)
                    total += count2
                    dir_str = "Gidiş" if target_direction == DirectionEnum.DEPARTURE else "Geliş"
                    logger.info(f"[heas] SAW İkinci yüklü ({dir_str}): {count2} uçuş yazıldı")

            except Exception as e:
                logger.error(f"[heas] SAW scraper hatası: {e}", exc_info=True)

        logger.info(f"[heas] Toplam: {total} uçuş kaydı yazıldı")
        return total

    def _extract_input_value(self, soup: BeautifulSoup, name: str) -> str:
        """HTML içinden hidden input değerini bulur."""
        input_el = soup.find("input", {"name": name})
        return input_el["value"] if input_el and "value" in input_el.attrs else ""

    def _parse_html_table(self, soup: BeautifulSoup, direction: DirectionEnum, target_date: date) -> list[FlightData]:
        """Sabiha Gökçen HTML tablosunu parse eder."""
        flights: list[FlightData] = []
        table = soup.select_one("table.feedtable")

        if not table:
            logger.warning("[heas] HTML tablosu (table.feedtable) bulunamadı.")
            return []

        tbody = table.find("tbody")
        if not tbody:
            return []

        rows = tbody.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            # Sütun sırası (SAW genelde şu formatta):
            # 0: Havayolu İkonu/Adı
            # 1: Uçuş Numarası (Örn: PC 1234)
            # 2: Şehir (Örn: AMSTERDAM)
            # 3: Saat (Örn: 09:00)
            # 4: Beklenen/Gerçekleşen Saat veya Durum (Örn: KAPI KAPANDI veya 09:25)

            airline_name = cols[0].text.strip()
            flight_number = cols[1].text.strip()
            city = cols[2].text.strip()
            planned_time_str = cols[3].text.strip()

            if not flight_number:
                continue

            # Durum sütununda bazen yeni saat, bazen metin yazar
            status_col_text = cols[4].text.strip()
            estimated_time_str = None
            status_text = status_col_text

            # Eğer durum sütunu HH:MM formatındaysa (tahmini saati gösteriyorsa)
            if ":" in status_col_text and len(status_col_text.replace(":", "").strip()) <= 4:
                estimated_time_str = status_col_text
                status_text = "Rötarlı" if estimated_time_str != planned_time_str else "Zamanında"

            # Parse DateTime
            scheduled_dt = self._combine_date_time(target_date, planned_time_str)
            if not scheduled_dt:
                continue

            estimated_dt = self._combine_date_time(target_date, estimated_time_str)

            # Rota:
            if direction == DirectionEnum.ARRIVAL:
                origin_city = city
                destination_city = "İstanbul"
            else:
                origin_city = "İstanbul"
                destination_city = city

            flight = FlightData(
                flight_number=flight_number,
                flight_date=target_date,
                airport_code="SAW",
                direction=direction,
                source=self.SOURCE,
                airport_name="Sabiha Gökçen Havalimanı",
                airline_code=self._extract_airline_code(flight_number),
                airline_name=airline_name if airline_name else None,
                origin_city=origin_city,
                destination_city=destination_city,
                scheduled_time=scheduled_dt,
                estimated_time=estimated_dt,
                status=_normalize_status(status_text),
                status_detail=status_text if status_text else None,
            )
            flights.append(flight)

        return flights

    def _extract_airline_code(self, flight_number: str) -> str | None:
        """Uçuş numarasından havayolu kodunu çıkarır. 'PC 1234' → 'PC'"""
        code = ""
        for ch in flight_number:
            if ch.isalpha():
                code += ch
            else:
                break
        return code.upper() if code else None

    def _combine_date_time(self, d: date, time_str: str | None) -> datetime | None:
        """'09:00' string'ini date ile birleştirip timezone ekler."""
        if not time_str or ":" not in time_str:
            return None
        try:
            hour, minute = map(int, time_str.split(":", 1))
            dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ_TR)
            return dt
        except ValueError:
            return None

    async def fetch_flights(
        self,
        session: aiohttp.ClientSession,
        airport_code: str,
        flight_date: date,
    ) -> list[FlightData]:
        pass

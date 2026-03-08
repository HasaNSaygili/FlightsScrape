"""
zonhav_scraper.py
─────────────────
ZONHAV — Zonguldak Çaycuma Havalimanı (ONQ).

API Keşfi:
  Zonguldak Havalimanı'nda anlık JSON API yok. Uçuşlar "wpDataTables" eklentisi ile
  WordPress sayfasında sunucu tarafında oluşturulmuş HTML tablo olarak (sezonluk takvim) sunuluyor.
  Aynı satırda hem geliş hem gidiş saati bulunduğundan tek bir satırdan 2 FlightData nesnesi çıkarılır.
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

API_URL = "https://zonguldakhavalimani.com.tr/seferler/"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

class ZonhavScraper(BaseScraper):
    """
    ZONHAV — Zonguldak Çaycuma Havalimanı (ONQ) Scraper.
    """

    SOURCE = SourceEnum.ZONHAV
    AIRPORT_CODES = ["ONQ"]

    async def run(self, flight_date: date | None = None) -> int:
        target_date = flight_date or date.today()
        total = 0

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=45),
            headers=DEFAULT_HEADERS,
        ) as session:
            try:
                await asyncio.sleep(REQUEST_DELAY)
                proxy = self.proxy_manager.get_proxy_dict()
                
                async with session.get(API_URL, proxy=proxy) as resp:
                    resp.raise_for_status()
                    html_content = await resp.text()

                flights = self._parse_html(html_content, target_date)
                
                if flights:
                    from core.db_client import upsert_flights
                    count = await upsert_flights(flights)
                    total += count
                    logger.info(f"[zonhav] ONQ: {count} uçuş yazıldı")
            except Exception as e:
                logger.error(f"[zonhav] Zonguldak URL isteğinde hata: {e}")

        logger.info(f"[zonhav] Toplam: {total} uçuş kaydı yazıldı")
        return total

    def _parse_html(self, html: str, target_date: date) -> list[FlightData]:
        soup = BeautifulSoup(html, "html.parser")
        flights: list[FlightData] = []
        
        # İç hatlar ve Dış hatlar tablolarını gez
        target_tables = ["wpdtSimpleTable-6", "wpdtSimpleTable-7"]
        
        for t_id in target_tables:
            table = soup.find("table", id=t_id)
            if not table:
                continue
                
            tbody = table.find("tbody")
            rows = tbody.find_all("tr") if tbody else table.find_all("tr")

            for row in rows:
                cols = row.find_all("td")
                
                # Zonguldak wpDataTable sütun yapısı:
                # 0: Hava Yolu (Eğer yoksa logo img)
                # 1: Tarih (Örn: 01.03.2026)
                # 2: İniş Yeri (Rota/Şehir)
                # 3: İniş Saati (14.50)
                # 4: Kalkış Saati (16.25)
                
                if len(cols) < 5:
                    continue
                    
                def get_text(idx):
                    return cols[idx].text.strip().replace("\n", "")

                date_str = get_text(1)
                
                # Sadece bugünkü uçuşları filtrele
                if date_str != target_date.strftime("%d.%m.%Y"):
                    continue

                airline_name = self._guess_airline(cols[0])
                city_desc = get_text(2)
                arr_time_str = get_text(3)
                dep_time_str = get_text(4)

                # arrival flight data creation
                arr_dt = self._combine_date_time(target_date, arr_time_str)
                if arr_dt:
                    flights.append(FlightData(
                        flight_number=f"ONQ-ARR-{airline_name[:2].upper() if airline_name else 'UKN'}-{arr_time_str.replace('.', '')}", # Dummy ID since actual is missing
                        flight_date=target_date,
                        airport_code="ONQ",
                        direction=DirectionEnum.ARRIVAL,
                        source=self.SOURCE,
                        airport_name="Zonguldak Çaycuma Havalimanı",
                        airline_code=None,
                        airline_name=airline_name,
                        origin_city=city_desc,
                        destination_city="Zonguldak",
                        scheduled_time=arr_dt,
                        estimated_time=None,
                        status=FlightStatusEnum.SCHEDULED, # Takvim usulü 
                    ))
                
                # departure flight data creation
                dep_dt = self._combine_date_time(target_date, dep_time_str)
                if dep_dt:
                    flights.append(FlightData(
                        flight_number=f"ONQ-DEP-{airline_name[:2].upper() if airline_name else 'UKN'}-{dep_time_str.replace('.', '')}", # Dummy ID 
                        flight_date=target_date,
                        airport_code="ONQ",
                        direction=DirectionEnum.DEPARTURE,
                        source=self.SOURCE,
                        airport_name="Zonguldak Çaycuma Havalimanı",
                        airline_code=None,
                        airline_name=airline_name,
                        origin_city="Zonguldak",
                        destination_city=city_desc,
                        scheduled_time=dep_dt,
                        estimated_time=None,
                        status=FlightStatusEnum.SCHEDULED,
                    ))

        return flights

    def _guess_airline(self, td) -> str | None:
        if not td: return None
        img = td.find("img")
        if img and img.get("alt"):
            return img.get("alt").strip()
        if img and img.get("src"):
            src = img.get("src").lower()
            if "thy" in src or "turkish" in src or "tk" in src: return "Turkish Airlines"
            if "sunexpress" in src or "xq" in src: return "SunExpress"
            if "corendon" in src: return "Corendon Airlines"
        return td.text.strip() or None

    def _combine_date_time(self, d: date, time_str: str) -> datetime | None:
        if not time_str:
            return None
        
        # time_str could be "14.50" or "14:50"
        time_str = time_str.replace(".", ":")
        
        parts = time_str.split(":")
        if len(parts) >= 2:
            try:
                hour = int(re.sub(r"\D", "", parts[0]))
                minute = int(re.sub(r"\D", "", parts[1][:2]))
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
        raise NotImplementedError("ZONHAV kendi run() metodunu kullanır.")

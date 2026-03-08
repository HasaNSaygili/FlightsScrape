"""
main.py
───────
10 scraper'ı asenkron ve eşzamanlı başlatan ana motor.
Her scraper kendi havalimanı listesinde döner,
hepsi birlikte çalışır (asyncio.gather).
"""

import asyncio
import logging
from datetime import date

# ─── Scraper importları ──────────────────────
from scrapers.dhmi_scraper import DhmiScraper
from scrapers.tav_scraper import TavScraper
from scrapers.iga_scraper import IgaScraper
from scrapers.heas_scraper import HeasScraper
from scrapers.fraport_tav_scraper import FraportTavScraper
from scrapers.yda_scraper import YdaScraper
from scrapers.favori_scraper import FavoriScraper
from scrapers.ic_ictas_scraper import IcIctasScraper
from scrapers.zonhav_scraper import ZonhavScraper
from scrapers.estu_scraper import EstuScraper

from core.proxy_manager import ProxyManager


# ─── Logging ─────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Tüm Scraper'ları Tanımla ───────────────

ALL_SCRAPERS = [
    DhmiScraper,    # 40+ DHMİ havalimanı
    IgaScraper,     # IST
    HeasScraper,    # SAW
    TavScraper,     # ADB, ESB, BJV, GZP
    FraportTavScraper, # AYT
    YdaScraper,     # DLM
    FavoriScraper,  # COV
    IcIctasScraper, # KZR
    EstuScraper,    # AOE
    ZonhavScraper,  # ONQ
]

async def run_all_scrapers(flight_date: date | None = None) -> dict[str, int]:
    """
    Tüm scraper'ları eşzamanlı çalıştırır.

    Returns:
        { scraper_adı: yazılan_kayıt_sayısı } sözlüğü
    """
    pm = ProxyManager()
    target_date = flight_date or date.today()
    results: dict[str, int] = {}

    # Her scraper'ı aynı anda başlat
    tasks = []
    for ScraperClass in ALL_SCRAPERS:
        scraper = ScraperClass(proxy_manager=pm)
        tasks.append((scraper.SOURCE.value, scraper.run(target_date)))

    logger.info(f"🛫 {len(tasks)} scraper başlatılıyor — Tarih: {target_date}")

    gathered = await asyncio.gather(
        *[task for _, task in tasks],
        return_exceptions=True,
    )

    for (name, _), result in zip(tasks, gathered):
        if isinstance(result, Exception):
            logger.error(f"❌ {name}: {result}")
            results[name] = 0
        else:
            results[name] = result
            logger.info(f"✅ {name}: {result} uçuş")

    total = sum(results.values())
    logger.info(f"🏁 Toplam: {total} uçuş kaydı yazıldı")
    return results


if __name__ == "__main__":
    asyncio.run(run_all_scrapers())

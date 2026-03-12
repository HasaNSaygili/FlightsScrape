"""
main.py
───────
10 scraper'ı asenkron ve eşzamanlı başlatan ana motor.
Her scraper kendi havalimanı listesinde döner,
hepsi birlikte çalışır (asyncio.gather).
"""

import asyncio #Python'un asenkron (eşzamanlı) çalışmasını sağlayan temel kütüphanedir.
import logging #Python'da programların çalışırken ürettikleri mesajları (logları) yönetmek için kullanılır.
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
logger = logging.getLogger(__name__) #__name__ değişkeni, Python'da o an çalıştırılan dosyanın adını tutar. 
#Bu satır, logger'a dosyanın adını verir. Böylece log mesajlarında hangi dosyadan geldiği görülebilir.


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
    pm = ProxyManager() #ProxyManager sınıfından bir nesne oluşturur. Bu nesne, proxy listesini yönetmek için kullanılır.
    target_date = flight_date or date.today() #Eğer flight_date None ise, bugünün tarihini kullanır.
    results: dict[str, int] = {} 

    # Her scraper'ı aynı anda başlat
    tasks = [] #Asenkron görevleri saklamak için bir liste oluşturur.
    for ScraperClass in ALL_SCRAPERS:
        scraper = ScraperClass(proxy_manager=pm)
        tasks.append((scraper.SOURCE.value, scraper.run(target_date)))
        #Listeye eklerken (isim, task) şeklinde ekleriz. Ama hemen çalıştırmayız. 
        #Çünkü run() metodu asenkron bir metottur.

    logger.info(f"🛫 {len(tasks)} scraper başlatılıyor — Tarih: {target_date}")

    gathered = await asyncio.gather( #await asyncio.gather() fonksiyonu, kendisine verilen tüm asenkron görevleri (tasks) aynı anda başlatır ve hepsinin bitmesini bekler.
        *[task for _, task in tasks], #Task isimlerini atlar sadece taskları alır.
        # * unpacking işlemi yapar. Listeyi dağıtır.
        return_exceptions=True, #Hata olursa programın durmasını engeller.
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



#Tasks listesindeki isimleri bir kenara bırakıp sadece iş paketlerini al (List comprehension), 
#bunları paketinden çıkarıp dağıt (* operator), 
#hepsini aynı anda internete gönder (gather) 
#ve biri hata yaparsa bile diğerlerini durdurma (return_exceptions); 
#ta ki hepsi işini bitirip geri dönene kadar burada bekle (await).


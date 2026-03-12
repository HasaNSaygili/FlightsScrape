"""
scheduler.py
────────────
Tüm scraper'ları saatlik otomatik çalıştırır.
Kullanım: python scheduler.py

Her saat başı tüm havalimanlarının verisini çekip Supabase'e yazar.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta

from main import run_all_scrapers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Kaç dakikada bir çalışsın (default: 60 dakika = 1 saat)
INTERVAL_MINUTES = 60


async def scheduler_loop():
    logger.info(f"⏰ Scheduler başlatıldı — her {INTERVAL_MINUTES} dakikada bir çalışacak")
    run_count = 0

    while True:
        run_count += 1
        TZ_TR = timezone(timedelta(hours=3))
        now_str = datetime.now(TZ_TR).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 Çalıştırma #{run_count} — {now_str} (UTC+3)")
        logger.info(f"{'='*60}")

        try:
            results = await run_all_scrapers()
            total = sum(results.values())
            logger.info(f"✅ #{run_count} tamamlandı: {total} toplam uçuş kaydedildi")
        except Exception as e:
            logger.error(f"❌ #{run_count} hata: {e}", exc_info=True)

        next_run = datetime.now(TZ_TR) + timedelta(minutes=INTERVAL_MINUTES)
        logger.info(f"⏳ Sonraki çalışma: {next_run.strftime('%H:%M:%S')} ({INTERVAL_MINUTES} dakika sonra)")
        await asyncio.sleep(INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    asyncio.run(scheduler_loop())

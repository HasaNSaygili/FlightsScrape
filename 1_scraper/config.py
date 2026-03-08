"""
config.py
─────────
Proje genelindeki yapılandırma ayarları.
- Supabase bağlantı bilgileri
- Proxy pool listesi
- Scraper genel ayarları
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── SUPABASE ──────────────────────────────────────────────────────────

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# ─── PROXY POOL ────────────────────────────────────────────────────────
# Proxy'lerinizi buraya ekleyin veya .env dosyasından çekin.
# Format: ["http://user:pass@ip:port", ...]

PROXY_POOL: list[str] = [
    # "http://user:pass@proxy1:8080",
    # "http://user:pass@proxy2:8080",
]

# ─── SCRAPER AYARLARI ──────────────────────────────────────────────────

# Her istek arasındaki bekleme süresi (saniye)
REQUEST_DELAY: float = 1.0

# Eşzamanlı maksimum istek sayısı
MAX_CONCURRENT_REQUESTS: int = 10

# İstek zaman aşımı (saniye)
REQUEST_TIMEOUT: int = 30

# Başarısız isteklerde yeniden deneme sayısı
MAX_RETRIES: int = 3

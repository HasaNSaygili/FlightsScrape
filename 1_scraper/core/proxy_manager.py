"""
proxy_manager.py
────────────────
Proxy pool'dan rotasyonlu IP seçen modül.
"""

from __future__ import annotations

import itertools
import random

from config import PROXY_POOL


class ProxyManager:
    """
    Proxy havuzundan sırayla veya rastgele proxy seçer.

    Kullanım:
        pm = ProxyManager()
        proxy = pm.get_next()       # Sıradaki proxy
        proxy = pm.get_random()     # Rastgele proxy
    """

    def __init__(self, proxies: list[str] | None = None):
        self._proxies = proxies or PROXY_POOL
        self._cycle = itertools.cycle(self._proxies) if self._proxies else None

    @property
    def has_proxies(self) -> bool:
        """Havuzda proxy var mı?"""
        return bool(self._proxies)

    def get_next(self) -> str | None:
        """Round-robin sırasıyla bir sonraki proxy'yi döndürür."""
        if self._cycle is None:
            return None
        return next(self._cycle)

    def get_random(self) -> str | None:
        """Havuzdan rastgele bir proxy seçer."""
        if not self._proxies:
            return None
        return random.choice(self._proxies)

    def get_proxy_dict(self) -> dict[str, str] | None:
        """aiohttp için proxy sözlüğü döndürür."""
        proxy = self.get_next()
        if proxy is None:
            return None
        return proxy

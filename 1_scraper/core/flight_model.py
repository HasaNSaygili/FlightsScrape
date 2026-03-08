"""
flight_model.py
───────────────
Supabase `flights` tablosuyla birebir eşleşen Pydantic v2 veri modeli.
Tüm scraper'lar ham API verisini bu modele dönüştürüp validate eder,
ardından db_client.py aracılığıyla Supabase'e yazar.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ─── ENUM'LAR ─────────────────────────────────────────────────────────

class DirectionEnum(str, Enum):
    """Uçuş yönü — SQL CHECK constraint ile eşleşir."""
    ARRIVAL = "arrival"
    DEPARTURE = "departure"


class SourceEnum(str, Enum):
    """Veri kaynağı (işletmeci) — SQL CHECK constraint ile eşleşir."""
    DHMI = "dhmi"
    TAV = "tav"
    IGA = "iga"
    HEAS = "heas"
    FRAPORT_TAV = "fraport_tav"
    YDA = "yda"
    FAVORI = "favori"
    IC_ICTAS = "ic_ictas"
    ZONHAV = "zonhav"
    ESTU = "estu"


class FlightStatusEnum(str, Enum):
    """
    Normalize edilmiş uçuş durumları.
    Her scraper kendi Türkçe/İngilizce durum metnini `status_detail`'e yazar,
    bu enum ise standart karşılığını `status`'a atar.
    """
    LANDED = "landed"
    DEPARTED = "departed"
    DELAYED = "delayed"
    CANCELLED = "cancelled"
    ON_TIME = "on_time"
    BOARDING = "boarding"
    SCHEDULED = "scheduled"
    DIVERTED = "diverted"
    UNKNOWN = "unknown"


# ─── ANA MODEL ────────────────────────────────────────────────────────

class FlightData(BaseModel):
    """
    Tek bir FIDS uçuş kaydının standart şablonu.

    Kullanım:
        flight = FlightData(
            flight_number="TK 2020",
            flight_date=date.today(),
            airport_code="IST",
            direction=DirectionEnum.DEPARTURE,
            source=SourceEnum.IGA,
            scheduled_time=datetime.now(),
            ...
        )
        db_dict = flight.to_db_dict()  # Supabase upsert için
    """

    # ── Zorunlu Alanlar (Natural Key) ──
    flight_number: str = Field(
        ...,
        min_length=2,
        max_length=10,
        description="Uçuş numarası, örn: 'TK2020'",
    )
    flight_date: date = Field(
        ...,
        description="Uçuşun tarihi (YYYY-MM-DD)",
    )
    airport_code: str = Field(
        ...,
        min_length=3,
        max_length=4,
        description="Havalimanı IATA kodu, örn: 'IST'",
    )

    # ── Yön & Kaynak ──
    direction: DirectionEnum
    source: SourceEnum
    airport_name: Optional[str] = Field(
        default=None,
        description="Havalimanı tam adı, örn: 'İstanbul Havalimanı'",
    )

    # ── Havayolu ──
    airline_code: Optional[str] = Field(
        default=None,
        max_length=3,
        description="Havayolu IATA kodu, örn: 'TK'",
    )
    airline_name: Optional[str] = Field(
        default=None,
        description="Havayolu tam adı, örn: 'Türk Hava Yolları'",
    )

    # ── Rota ──
    origin_code: Optional[str] = Field(
        default=None,
        max_length=4,
        description="Kalkış havalimanı IATA kodu",
    )
    origin_city: Optional[str] = Field(
        default=None,
        description="Kalkış şehri",
    )
    destination_code: Optional[str] = Field(
        default=None,
        max_length=4,
        description="Varış havalimanı IATA kodu",
    )
    destination_city: Optional[str] = Field(
        default=None,
        description="Varış şehri",
    )

    # ── Zaman Bilgileri ──
    scheduled_time: datetime = Field(
        ...,
        description="Planlanan kalkış/iniş saati (timezone-aware)",
    )
    estimated_time: Optional[datetime] = Field(
        default=None,
        description="Tahmini güncel saat",
    )
    actual_time: Optional[datetime] = Field(
        default=None,
        description="Gerçekleşen saat",
    )

    # ── Durum & Kapı ──
    status: Optional[FlightStatusEnum] = Field(
        default=None,
        description="Normalize edilmiş uçuş durumu",
    )
    status_detail: Optional[str] = Field(
        default=None,
        description="Ham/orijinal durum metni (Türkçe vb.)",
    )
    gate: Optional[str] = Field(
        default=None,
        description="Kapı bilgisi, örn: 'A12'",
    )
    terminal: Optional[str] = Field(
        default=None,
        description="Terminal bilgisi, örn: 'Terminal 1'",
    )
    remarks: Optional[str] = Field(
        default=None,
        description="Ekstra not veya açıklama",
    )

    # ── Validators ──

    @field_validator("flight_number")
    @classmethod
    def clean_flight_number(cls, v: str) -> str:
        """Boşluk ve tireleri temizle, büyük harfe çevir. 'TK 2020' → 'TK2020'"""
        return v.replace(" ", "").replace("-", "").upper()

    @field_validator("airport_code", "origin_code", "destination_code")
    @classmethod
    def uppercase_iata(cls, v: Optional[str]) -> Optional[str]:
        """IATA kodlarını büyük harfe çevir."""
        if v is not None:
            return v.strip().upper()
        return v

    @field_validator("airline_code")
    @classmethod
    def uppercase_airline(cls, v: Optional[str]) -> Optional[str]:
        """Havayolu kodunu büyük harfe çevir."""
        if v is not None:
            return v.strip().upper()
        return v

    # ── Export ──

    def to_db_dict(self) -> dict:
        """
        Supabase upsert için sözlük üretir.
        - Enum'lar → string value
        - datetime → ISO format string
        - date → ISO format string
        - None değerler korunur (Supabase NULL olarak yazar)
        """
        data = {}
        for field_name, value in self:
            if isinstance(value, Enum):
                data[field_name] = value.value
            elif isinstance(value, datetime):
                data[field_name] = value.isoformat()
            elif isinstance(value, date):
                data[field_name] = value.isoformat()
            else:
                data[field_name] = value
        return data

    class Config:
        # JSON schema'da örnek göster
        json_schema_extra = {
            "example": {
                "flight_number": "TK2020",
                "flight_date": "2026-03-08",
                "airport_code": "IST",
                "direction": "departure",
                "source": "iga",
                "airport_name": "İstanbul Havalimanı",
                "airline_code": "TK",
                "airline_name": "Türk Hava Yolları",
                "origin_code": "IST",
                "origin_city": "İstanbul",
                "destination_code": "ADB",
                "destination_city": "İzmir",
                "scheduled_time": "2026-03-08T14:30:00+03:00",
                "estimated_time": "2026-03-08T14:45:00+03:00",
                "actual_time": None,
                "status": "delayed",
                "status_detail": "Rötar",
                "gate": "A12",
                "terminal": "Terminal 1",
                "remarks": None,
            }
        }

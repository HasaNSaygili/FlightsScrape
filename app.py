import os
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from 1_scraper/.env
env_path = os.path.join(os.path.dirname(__file__), '1_scraper', '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

app = Flask(__name__)

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print(f"WARNING: Supabase credentials not found in {env_path}")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Airports list — sadece veritabanında gerçekten veri olan havalimanları
AIRPORTS = [
    {"code": "ALL", "name": "Tüm"},
    {"code": "IST", "name": "İstanbul (IST)"},
    {"code": "SAW", "name": "S. Gökçen (SAW)"},
    {"code": "ESB", "name": "Ankara (ESB)"},
    {"code": "ADB", "name": "İzmir (ADB)"},
    {"code": "AYT", "name": "Antalya (AYT)"},
    {"code": "ADA", "name": "Adana (ADA)"},
    {"code": "ADF", "name": "Adıyaman (ADF)"},
    {"code": "GZT", "name": "Gaziantep (GZT)"},
    {"code": "TZX", "name": "Trabzon (TZX)"},
    {"code": "DIY", "name": "Diyarbakır (DIY)"},
    {"code": "SZF", "name": "Samsun (SZF)"},
    {"code": "BJV", "name": "Bodrum (BJV)"},
    {"code": "DLM", "name": "Dalaman (DLM)"},
    {"code": "COV", "name": "Çukurova (COV)"},
    {"code": "GZP", "name": "Gazipaşa (GZP)"},
    {"code": "BAL", "name": "Batman (BAL)"},
    {"code": "MSR", "name": "Muş (MSR)"},
    {"code": "GKD", "name": "Gökçeada (GKD)"},
    {"code": "BXN", "name": "Bursa (BXN)"},
    {"code": "MLX", "name": "Malatya (MLX)"},
    {"code": "KYA", "name": "Konya (KYA)"},
    {"code": "ISE", "name": "Isparta (ISE)"},
    {"code": "IGD", "name": "Iğdır (IGD)"},
    {"code": "DNZ", "name": "Denizli (DNZ)"},
    {"code": "GNY", "name": "Şanlıurfa (GNY)"},
    {"code": "KCM", "name": "K.Maraş (KCM)"},
    {"code": "EDO", "name": "Balıkesir (EDO)"},
    {"code": "ERZ", "name": "Erzurum (ERZ)"},
    {"code": "NKT", "name": "Şırnak (NKT)"},
    {"code": "AFY", "name": "Afyon (AFY)"},
    {"code": "ONQ", "name": "Zonguldak (ONQ)"},
    {"code": "KSY", "name": "Kars (KSY)"},
    {"code": "RIZ", "name": "Rize-Artvin (RIZ)"},
    {"code": "NOP", "name": "Sinop (NOP)"},
    {"code": "CKZ", "name": "Çanakkale (CKZ)"},
    {"code": "HTY", "name": "Hatay (HTY)"},
    {"code": "VAS", "name": "Sivas (VAS)"},
    {"code": "CII", "name": "Çıldır (CII)"},
    {"code": "BGG", "name": "Bingöl (BGG)"},
    {"code": "AJI", "name": "Ağrı (AJI)"},
    {"code": "ERC", "name": "Erzincan (ERC)"},
    {"code": "KFS", "name": "Kastamonu (KFS)"},
    {"code": "BZI", "name": "Balıkesir (BZI)"},
    {"code": "USQ", "name": "Uşak (USQ)"},
]


def format_datetime(iso_string):
    if not iso_string:
        return ""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime("%H:%M")
    except:
        return iso_string

def format_date(iso_string):
    if not iso_string:
        return ""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime("%d.%m")
    except:
        return iso_string

app.jinja_env.filters['format_time'] = format_datetime
app.jinja_env.filters['format_date'] = format_date

@app.route('/')
def index():
    direction = request.args.get('direction', 'departure')
    airport_code = request.args.get('airport', 'ALL')
    search_query = request.args.get('search', '').lower().strip()
    page = int(request.args.get('page', 1))
    items_per_page = 20

    # Fetch flights
    # Türkiye saati (UTC+3) — Supabase timezone-aware datetime ile karşılaştırma için
    # Geniş aralık: 2 gün önce → 1 gün sonra (scraper dünkü veriyi çektiyse de göster)
    TZ_TR = timezone(timedelta(hours=3))
    now_tr = datetime.now(TZ_TR)
    start_time = (now_tr - timedelta(days=2)).isoformat()
    end_time = (now_tr + timedelta(days=1)).isoformat()

    try:
        query = supabase.table("flights")\
            .select("*")\
            .eq("direction", direction)\
            .gte("scheduled_time", start_time)\
            .lte("scheduled_time", end_time)\
            .order("scheduled_time", desc=False)\
            .limit(1000)

        if airport_code != "ALL":
            query = query.eq("airport_code", airport_code)

        response = query.execute()
        flights = response.data or []
    except Exception as e:
        print(f"Error fetching from Supabase: {e}")
        flights = []

    # Client-side style filtering in Python
    if search_query:
        if direction == 'arrival':
            # Arrivals focus on WHERE it arrived (destination)
            flights = [
                f for f in flights
                if search_query in (f.get('flight_number') or '').lower() or
                   search_query in (f.get('destination_city') or '').lower() or
                   search_query in (f.get('airline_name') or '').lower() or
                   search_query in (f.get('airport_name') or '').lower() or
                   search_query in (f.get('airport_code') or '').lower()
            ]
        else:
            # Departures focus on WHERE it left from (origin)
            flights = [
                f for f in flights
                if search_query in (f.get('flight_number') or '').lower() or
                   search_query in (f.get('origin_city') or '').lower() or
                   search_query in (f.get('airline_name') or '').lower() or
                   search_query in (f.get('airport_name') or '').lower() or
                   search_query in (f.get('airport_code') or '').lower()
            ]



    # Pagination
    total_flights = len(flights)
    total_pages = (total_flights + items_per_page - 1) // items_per_page
    if page < 1: page = 1
    if page > total_pages and total_pages > 0: page = total_pages
    
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    paginated_flights = flights[start_idx:end_idx]

    # Check if HTMX request
    if request.headers.get('HX-Request'):
        return render_template(
            'partials/fids_update.html',
            flights=paginated_flights,
            direction=direction,
            selected_airport=airport_code,
            airports=AIRPORTS,
            search_query=search_query,
            page=page,
            total_pages=total_pages,
            total_flights=total_flights
        )



    return render_template(
        'index.html',
        flights=paginated_flights,
        direction=direction,
        selected_airport=airport_code,
        airports=AIRPORTS,
        search_query=search_query,
        page=page,
        total_pages=total_pages,
        total_flights=total_flights
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)

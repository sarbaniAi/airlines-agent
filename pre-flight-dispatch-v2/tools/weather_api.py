"""
Real-time weather tool — fetches live airport weather from Open-Meteo API.
No API key required. Falls back to aviationweather.gov for METAR.
"""
import logging
import requests
import urllib3

try:
    import mlflow
    HAS_MLFLOW = True
except ImportError:
    HAS_MLFLOW = False

urllib3.disable_warnings()
logger = logging.getLogger("tools.weather_api")

# Airport coordinates (lat, lon) and ICAO codes
AIRPORTS = {
    "DEL": {"lat": 28.5562, "lon": 77.1000, "icao": "VIDP", "name": "Indira Gandhi International, Delhi", "country": "India"},
    "BOM": {"lat": 19.0896, "lon": 72.8656, "icao": "VABB", "name": "Chhatrapati Shivaji Maharaj International, Mumbai", "country": "India"},
    "BLR": {"lat": 13.1979, "lon": 77.7063, "icao": "VOBL", "name": "Kempegowda International, Bengaluru", "country": "India"},
    "MAA": {"lat": 12.9941, "lon": 80.1709, "icao": "VOMM", "name": "Chennai International", "country": "India"},
    "HYD": {"lat": 17.2403, "lon": 78.4294, "icao": "VOHS", "name": "Rajiv Gandhi International, Hyderabad", "country": "India"},
    "YYZ": {"lat": 43.6777, "lon": -79.6248, "icao": "CYYZ", "name": "Toronto Pearson International", "country": "Canada"},
    "LHR": {"lat": 51.4700, "lon": -0.4543, "icao": "EGLL", "name": "London Heathrow", "country": "United Kingdom"},
    "SIN": {"lat": 1.3502, "lon": 103.9944, "icao": "WSSS", "name": "Singapore Changi", "country": "Singapore"},
    "JFK": {"lat": 40.6413, "lon": -73.7781, "icao": "KJFK", "name": "John F. Kennedy International, New York", "country": "USA"},
    "SFO": {"lat": 37.6213, "lon": -122.3790, "icao": "KSFO", "name": "San Francisco International", "country": "USA"},
    "YVR": {"lat": 49.1947, "lon": -123.1792, "icao": "CYVR", "name": "Vancouver International", "country": "Canada"},
    "CDG": {"lat": 49.0097, "lon": 2.5479, "icao": "LFPG", "name": "Charles de Gaulle, Paris", "country": "France"},
    "DXB": {"lat": 25.2532, "lon": 55.3657, "icao": "OMDB", "name": "Dubai International", "country": "UAE"},
    "NRT": {"lat": 35.7647, "lon": 140.3864, "icao": "RJAA", "name": "Narita International, Tokyo", "country": "Japan"},
    "FRA": {"lat": 50.0379, "lon": 8.5622, "icao": "EDDF", "name": "Frankfurt Airport", "country": "Germany"},
}


def get_live_weather(airport_code: str) -> dict:
    """
    Fetch real-time weather for an airport using Open-Meteo API.
    Returns dict with: temperature_c, visibility_km, wind_speed_kts, wind_direction,
    ceiling_ft, conditions, metar_raw, airport_name, country, source.
    """
    airport = AIRPORTS.get(airport_code.upper())
    if not airport:
        return _fallback_weather(airport_code)

    span = None
    try:
        if HAS_MLFLOW:
            span = mlflow.start_span(name="weather_api", span_type="TOOL")
            span.set_inputs({"airport": airport_code, "airport_name": airport.get("name", "")})
    except Exception:
        span = None

    try:
        # Open-Meteo current weather API (free, no key)
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={airport['lat']}&longitude={airport['lon']}"
            f"&current=temperature_2m,relative_humidity_2m,weather_code,"
            f"wind_speed_10m,wind_direction_10m,wind_gusts_10m,"
            f"cloud_cover,visibility,surface_pressure"
            f"&timezone=auto"
        )
        resp = requests.get(url, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})

        # Parse Open-Meteo response
        temp_c = current.get("temperature_2m", 20)
        wind_speed_ms = current.get("wind_speed_10m", 0)  # m/s in open-meteo? Actually km/h
        wind_speed_kts = round(wind_speed_ms * 0.5399568, 0)  # km/h to knots
        wind_dir = current.get("wind_direction_10m", 0)
        wind_gusts_kts = round(current.get("wind_gusts_10m", 0) * 0.5399568, 0)
        visibility_m = current.get("visibility", 10000)  # meters
        visibility_km = round(visibility_m / 1000, 1)
        cloud_cover = current.get("cloud_cover", 0)  # percentage
        weather_code = current.get("weather_code", 0)
        humidity = current.get("relative_humidity_2m", 50)

        # Estimate ceiling from cloud cover (rough approximation)
        if cloud_cover > 90:
            ceiling_ft = 500 if visibility_km < 1 else 1000
        elif cloud_cover > 70:
            ceiling_ft = 1500 if visibility_km < 3 else 2500
        elif cloud_cover > 50:
            ceiling_ft = 3000
        else:
            ceiling_ft = 5000  # CAVOK-like

        # Decode WMO weather code to conditions string
        conditions, hazards = _decode_weather_code(weather_code)

        # Build synthetic METAR
        metar = _build_metar(airport["icao"], temp_c, wind_speed_kts, wind_dir,
                            visibility_km, ceiling_ft, conditions, humidity, wind_gusts_kts)

        weather_result = {
            "airport_code": airport_code,
            "airport_name": airport["name"],
            "country": airport["country"],
            "temperature_c": round(temp_c, 1),
            "visibility_km": visibility_km,
            "wind_speed_kts": int(wind_speed_kts),
            "wind_direction": int(wind_dir),
            "wind_gusts_kts": int(wind_gusts_kts),
            "ceiling_ft": ceiling_ft,
            "conditions": conditions,
            "hazards": hazards,
            "humidity": humidity,
            "cloud_cover": cloud_cover,
            "metar_raw": metar,
            "source": "Open-Meteo (Real-time)",
            "severity": _assess_severity(visibility_km, ceiling_ft, wind_speed_kts, conditions),
        }

        try:
            if span is not None:
                span.set_outputs({
                    "conditions": conditions,
                    "temperature": round(temp_c, 1),
                    "visibility_km": visibility_km,
                    "severity": weather_result["severity"],
                    "source": "Open-Meteo",
                })
                span.end()
        except Exception:
            pass

        return weather_result

    except Exception as e:
        logger.warning(f"Open-Meteo API failed for {airport_code}: {e}")

        try:
            if span is not None:
                span.set_outputs({"error": str(e), "source": "FALLBACK"})
                span.end()
        except Exception:
            pass

        return _fallback_weather(airport_code)


def _decode_weather_code(code: int) -> tuple:
    """Decode WMO weather code to aviation conditions string and hazards list."""
    hazards = []
    if code == 0:
        return "CAVOK", hazards
    elif code in (1, 2, 3):
        conditions = ["FEW", "SCT", "BKN"][code - 1]
        return conditions, hazards
    elif code in (45, 48):
        hazards.append("FOG")
        return "FG", hazards
    elif code in (51, 53, 55):
        hazards.append("DRIZZLE")
        return "DZ", hazards
    elif code in (56, 57):
        hazards.append("FREEZING_DRIZZLE")
        return "FZDZ", hazards
    elif code in (61, 63, 65):
        intensity = ["light", "moderate", "heavy"][code - 61 if code <= 63 else 2]
        hazards.append(f"RAIN_{intensity.upper()}")
        return "RA", hazards
    elif code in (66, 67):
        hazards.append("FREEZING_RAIN")
        return "FZRA", hazards
    elif code in (71, 73, 75):
        hazards.append("SNOW")
        return "SN", hazards
    elif code == 77:
        hazards.append("SNOW_GRAINS")
        return "SG", hazards
    elif code in (80, 81, 82):
        hazards.append("RAIN_SHOWERS")
        return "SHRA", hazards
    elif code in (85, 86):
        hazards.append("SNOW_SHOWERS")
        return "SHSN", hazards
    elif code in (95, 96, 99):
        hazards.append("THUNDERSTORM")
        if code >= 96:
            hazards.append("HAIL")
        return "TS", hazards
    else:
        return "SCT", hazards


def _assess_severity(vis_km, ceiling_ft, wind_kts, conditions):
    """Assess weather severity for aviation."""
    if conditions in ("TS", "TS+", "FZRA", "FZDZ"):
        return "RED"
    if vis_km < 0.8 or (ceiling_ft and ceiling_ft < 200):
        return "RED"
    if vis_km < 3.0 or (ceiling_ft and ceiling_ft < 1000) or wind_kts > 25:
        return "AMBER"
    return "GREEN"


def _build_metar(icao, temp, wind_kts, wind_dir, vis_km, ceiling, conditions, humidity, gusts):
    """Build a synthetic METAR string."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%d%H%MZ")

    wind_str = f"{int(wind_dir):03d}{int(wind_kts):02d}"
    if gusts > wind_kts + 5:
        wind_str += f"G{int(gusts):02d}"
    wind_str += "KT"

    if vis_km >= 10:
        vis_str = "9999"
    else:
        vis_str = f"{int(vis_km * 1000):04d}"

    if conditions == "CAVOK":
        wx_str = "CAVOK"
    else:
        cloud_str = f"{'BKN' if ceiling < 2000 else 'SCT'}{int(ceiling/100):03d}"
        wx_str = f"{conditions} {cloud_str}" if conditions != "SCT" else cloud_str

    dew = round(temp - (100 - humidity) / 5, 0)
    temp_str = f"{'M' if temp < 0 else ''}{abs(int(temp)):02d}/{'M' if dew < 0 else ''}{abs(int(dew)):02d}"

    return f"METAR {icao} {time_str} {wind_str} {vis_str} {wx_str} {temp_str}"


def _fallback_weather(airport_code: str) -> dict:
    """Fallback when API is unavailable — return unknown weather."""
    airport = AIRPORTS.get(airport_code.upper(), {})
    return {
        "airport_code": airport_code,
        "airport_name": airport.get("name", airport_code),
        "country": airport.get("country", "Unknown"),
        "temperature_c": None,
        "visibility_km": None,
        "wind_speed_kts": None,
        "wind_direction": None,
        "wind_gusts_kts": None,
        "ceiling_ft": None,
        "conditions": "UNKNOWN",
        "hazards": [],
        "humidity": None,
        "cloud_cover": None,
        "metar_raw": f"METAR {airport.get('icao', '????')} — DATA UNAVAILABLE",
        "source": "UNAVAILABLE",
        "severity": "AMBER",
    }

# weather_dashboard.py
# Author: Mohamed Elmarakby
# 
# Modern CLI weather dashboard with OpenWeather API integration.
# Features: auto-location, 3-day forecast, Rich UI, latency tracking.


import os
import sys
import time
import requests
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich.align import Align

# Setup
load_dotenv()
CONSOLE = Console()
API_KEY = os.getenv("OPENWEATHER_API_KEY")
if not API_KEY:
    sys.exit("ERROR: Missing OPENWEATHER_API_KEY in environment.")

CACHE_DIR = Path.home() / ".cache" / "weather_cli"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------
# API Helpers
# -----------------------------------------------------------
def _req(url, params):
    """Perform API request with retries and latency tracking."""
    for _ in range(3):
        try:
            t0 = time.time()
            r = requests.get(url, params=params, timeout=10)
            latency = int((time.time() - t0) * 1000)
            r.raise_for_status()
            return r.json(), latency
        except requests.RequestException:
            time.sleep(0.3)
    return None, 0


def get_weather_data(city: str, units: str):
    """Fetch current weather data."""
    return _req("https://api.openweathermap.org/data/2.5/weather",
                {"q": city, "appid": API_KEY, "units": units})


def get_forecast_data(city: str, units: str):
    """Fetch 3-day forecast data."""
    return _req("https://api.openweathermap.org/data/2.5/forecast",
                {"q": city, "appid": API_KEY, "units": units})


# -----------------------------------------------------------
# Data Summarization
# -----------------------------------------------------------
def summarize_forecast(forecast_data, days=3):
    """Summarize forecast into daily min/max/pop/description."""
    grouped = defaultdict(list)
    for e in forecast_data.get("list", []):
        d = datetime.fromtimestamp(e["dt"], tz=timezone.utc).date().isoformat()
        grouped[d].append(e)

    results = []
    for day in sorted(grouped.keys())[:days]:
        entries = grouped[day]
        temps = [i["main"]["temp"] for i in entries]
        pops = [i.get("pop", 0) for i in entries]
        desc = Counter(i["weather"][0]["description"] for i in entries).most_common(1)[0][0]
        results.append({
            "date": day,
            "min": min(temps),
            "max": max(temps),
            "pop": int((sum(pops) / len(pops)) * 100),
            "desc": desc.capitalize()
        })
    return results


# -----------------------------------------------------------
# Dashboard Rendering
# -----------------------------------------------------------
def render_dashboard(current, forecast, latencies, units):
    """Render a professional monochrome dashboard."""
    temp_unit = "°C" if units == "metric" else "°F"
    sys_data, main, wind = current["sys"], current["main"], current["wind"]
    weather = current["weather"][0]
    tz = timedelta(seconds=current.get("timezone", 0))
    local_time = datetime.now(timezone.utc) + tz

    header = Text(f"{current['name']}, {sys_data['country']}", style="bold white")
    sub = Text(f"Local: {local_time.strftime('%Y-%m-%d %H:%M')}  •  "
               f"Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
               style="grey70")

    # Current details
    details = Table.grid(padding=(0, 2))
    details.add_column("Label", justify="right", style="grey70")
    details.add_column("Value", justify="left", style="white")
    details.add_row("Condition", weather["main"])
    details.add_row("Description", weather["description"].capitalize())
    details.add_row("Temperature", f"{main['temp']:.1f}{temp_unit}")
    details.add_row("Feels Like", f"{main['feels_like']:.1f}{temp_unit}")
    details.add_row("Humidity", f"{main['humidity']}%")
    details.add_row("Pressure", f"{main['pressure']} hPa")
    details.add_row("Wind", f"{wind['speed']} m/s")
    details.add_row("Visibility", f"{current.get('visibility', 0)/1000:.1f} km")
    details.add_row("Clouds", f"{current['clouds']['all']}%")
    details.add_row("Sunrise", datetime.fromtimestamp(sys_data['sunrise']).strftime('%H:%M'))
    details.add_row("Sunset", datetime.fromtimestamp(sys_data['sunset']).strftime('%H:%M'))

    # Forecast Table
    ftab = Table(show_header=True, header_style="bold white", padding=(0, 2))
    for col in ["Date", "Min", "Max", "Pop", "Summary"]:
        ftab.add_column(col, justify="center" if col != "Summary" else "left", style="white")

    for f in forecast:
        ftab.add_row(f["date"],
                     f"{f['min']:.1f}{temp_unit}",
                     f"{f['max']:.1f}{temp_unit}",
                     f"{f['pop']}%",
                     f["desc"])

    footer = Text(f"API Latencies: current={latencies['current']}ms  "
                  f"forecast={latencies['forecast']}ms  |  Units: {units}",
                  style="grey62")

    layout = Table.grid(expand=True)
    layout.add_row(Align.center(header))
    layout.add_row(Align.center(sub))
    layout.add_row(Text(""))
    layout.add_row(details)
    layout.add_row(Text("\nFORECAST", style="bold white"))
    layout.add_row(ftab)
    layout.add_row(Text(""))
    layout.add_row(Align.center(footer))

    CONSOLE.print(Panel(layout, border_style="grey70", padding=(1, 2)))


def detect_city():
    """Auto-detect user's city using IP lookup."""
    try:
        res = requests.get("http://ip-api.com/json/", timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data.get("city")
    except requests.RequestException:
        pass
    return None


# -----------------------------------------------------------
# Main Loop with Retry
# -----------------------------------------------------------
def main():
    CONSOLE.print("[bold white]Weather Dashboard[/bold white]")
    CONSOLE.print("[white]Units (metric/imperial): [/white]", end="")
    units = input().strip().lower() or "metric"
    if units not in ["metric", "imperial"]:
        units = "metric"

    # Auto-detect user's city
    auto_city = detect_city() or "e.g. London"

    while True:
        CONSOLE.print(f"\n[white]Enter city name (e.g. {auto_city}) or 'q' to quit: [/white]", end="")
        city = input().strip()

        # Quit option
        if city.lower() in {"q", "quit", "exit"}:
            CONSOLE.print("\n[grey70]Goodbye.[/grey70]")
            break

        # Use auto-detected city if user presses Enter
        if not city:
            city = auto_city

        current, lat1 = get_weather_data(city, units)
        forecast, lat2 = get_forecast_data(city, units)
        latencies = {"current": lat1, "forecast": lat2}

        # Handle invalid city input
        if not current or not isinstance(current, dict) or current.get("cod") != 200:
            msg = current.get("message") if current and "message" in current else "City not found."
            CONSOLE.print(Panel.fit(
                f"[white]Error:[/white] {msg}\n[grey70]Please check the city name and try again.[/grey70]",
                title="[bold grey85]Weather Data Unavailable[/bold grey85]",
                border_style="grey50"
            ))
            continue

        if not forecast or not isinstance(forecast, dict) or forecast.get("cod") != "200":
            summarized = []
        else:
            summarized = summarize_forecast(forecast)

        render_dashboard(current, summarized, latencies, units)



if __name__ == "__main__":
    main()

import copy
import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.shortcuts import render

from wfcast.weather.models import City
from wfcast.weather.models import SearchHistory
from wfcast.weather.utils import fetch_geocoding_data
from wfcast.weather.utils import fetch_weather_api_data
from wfcast.weather.utils import parse_iso_strings_in_forecast_data
from wfcast.weather.utils import parse_session_location_data
from wfcast.weather.utils import prepare_location_data_for_session
from wfcast.weather.utils import process_raw_weather_data
from wfcast.weather.utils import update_city_and_history


logger = logging.getLogger(__name__)


MIN_AUTOCOMPLETE_QUERY_LENGTH = 2
AUTOCOMPLETE_CACHE_TIMEOUT = 3600  # 1 hour in seconds


def _handle_city_form_submission(request: HttpRequest) -> HttpResponseRedirect:
    """
    Handles the POST request when the main city search form is submitted.
    Sets location data in the session and redirects to fetch weather.
    """
    city_name_selected = request.POST.get("city", "").strip()
    lat_str = request.POST.get("lat")
    lon_str = request.POST.get("lon")

    if not city_name_selected:
        logger.info("City form submitted with no city name.")
        return redirect("city")

    location_data = prepare_location_data_for_session(
        city_name_selected,
        lat_str,
        lon_str,
    )
    request.session["location"] = location_data
    request.session.modified = True  # Good practice when setting/modifying session data

    return redirect("get_weather")


def _handle_autocomplete_request(request: HttpRequest) -> HttpResponse:
    """
    Handles HTMX GET requests for city autocomplete suggestions.
    Fetches data from a cache or API and renders a partial template.
    """
    query = request.GET.get("city", "").strip()

    if len(query) < MIN_AUTOCOMPLETE_QUERY_LENGTH:
        return HttpResponse("")  # Empty response clears HTMX target

    cache_key = f"autocomplete_{query.lower()}"
    cached_results: list[dict[str, Any]] | None = cache.get(cache_key)

    if cached_results is not None:
        return render(
            request,
            "weather/partials/autocomplete_results.html",
            {"results": cached_results},
        )

    api_results = fetch_geocoding_data(query)
    cache.set(cache_key, api_results, timeout=AUTOCOMPLETE_CACHE_TIMEOUT)

    return render(
        request,
        "weather/partials/autocomplete_results.html",
        {"results": api_results},
    )


def city_search_view(request: HttpRequest) -> HttpResponse:
    """
    Main view for city search.
    - Renders the city search page on GET.
    - Handles form submission (POST) to select a city.
    - Handles HTMX requests (GET with HX-Request header) for autocomplete.
    """
    if request.method == "POST":
        return _handle_city_form_submission(request)

    if request.headers.get("HX-Request"):  # Check for HTMX request header
        return _handle_autocomplete_request(request)

    # Standard GET request: render the main search page
    return render(request, "weather/city_search.html")


def get_weather_view(request: HttpRequest) -> HttpResponse:
    """
    Orchestrates fetching and displaying weather:
    1. Parses location from session.
    2. Fetches raw weather data.
    3. Processes raw data for display and session storage.
    4. Updates database (City, SearchHistory).
    5. Redirects to the result page.
    """
    session_location_input = request.session.get("location")

    parsed_location = parse_session_location_data(session_location_input)
    if not parsed_location:
        logger.warning("Failed to parse location data from session.")
        return redirect("city_search")

    lat = parsed_location["lat"]
    lon = parsed_location["lon"]

    raw_weather_data = fetch_weather_api_data(lat, lon)
    if not raw_weather_data:
        err_msg = (
            f"Failed to fetch weather API data for {parsed_location['display_name']}"
        )
        logger.error(err_msg)
        return redirect("city_search")

    processed_weather_data = process_raw_weather_data(raw_weather_data)
    if not processed_weather_data:
        err_msg = (
            f"Failed to process weather data for {parsed_location['display_name']}."
        )
        logger.error(err_msg)
        return redirect("city_search")

    request.session["weather_data"] = processed_weather_data
    request.session["location"] = {
        "display": parsed_location["display_name"],
        "lat": str(lat),
        "lon": str(lon),
        "name": parsed_location["name_component"],
        "admin1": parsed_location["admin1_component"],
        "country": parsed_location["country_component"],
    }
    request.session.modified = True

    update_city_and_history(request.user, parsed_location)

    return redirect("weather_results")


def weather_results_view(request: HttpRequest) -> HttpResponse:
    """
    Displays processed weather results.
    Retrieves location and weather data (with ISO date/time strings) from the session,
    converts date/time strings to datetime/date objects for template rendering.
    """
    location_from_session: dict[str, Any] | None = request.session.get("location")
    weather_data_from_session: dict[str, Any] | None = request.session.get(
        "weather_data",
    )

    if not weather_data_from_session:
        logger.warning("Weather data not found in session for weather_results_view.")
        return render(
            request,
            "weather/results.html",
            {"location": location_from_session, "weather": {}},
        )

    weather_for_template: dict[str, Any] = copy.deepcopy(weather_data_from_session)

    parse_iso_strings_in_forecast_data(
        weather_for_template.get("hourly_processed"),
        "time",
        is_date_only=False,
    )
    parse_iso_strings_in_forecast_data(
        weather_for_template.get("daily_processed"),
        "day",
        is_date_only=True,
    )

    context: dict[str, Any] = {
        "location": location_from_session,
        "weather": weather_for_template,
    }
    return render(request, "weather/results.html", context)


@login_required
def search_statistics(request):
    # Global statistics
    top_searches = SearchHistory.get_search_stats()

    # User-specific statistics
    user_searches = SearchHistory.get_user_search_stats(request.user)

    context = {
        "top_searches": top_searches,
        "user_searches": user_searches,
        "total_searches": SearchHistory.objects.count(),
        "unique_cities": City.objects.count(),
    }
    return render(request, "weather/statistics.html", context)

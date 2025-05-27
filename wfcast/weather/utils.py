from datetime import date
from datetime import datetime
import logging
from typing import Any

import requests

from wfcast.weather.models import City
from wfcast.weather.models import SearchHistory


logger = logging.getLogger(__name__)

WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_API_TIMEOUT = 10
GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
GEOCODING_API_TIMEOUT = 3  # seconds
GEOCODING_RESULT_COUNT = 5
GEOCODING_LANGUAGE = "en"
SEARCH_MIN_LETTERS = 2
ONE_LETTER = 1


def fetch_geocoding_data(query: str) -> list[dict[str, Any]]:
    """
    Fetches geocoding data from the Open-Meteo API for a given query.

    Args:
        query: The city name or search term.

    Returns:
        A list of result dictionaries from the API, or an empty list on failure.
    """
    api_results: list[dict[str, Any]] = []
    try:
        response = requests.get(
            GEOCODING_API_URL,
            params={
                "name": query,
                "count": GEOCODING_RESULT_COUNT,
                "language": GEOCODING_LANGUAGE,
            },
            timeout=GEOCODING_API_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()
        raw_results = data.get("results", [])

        for item in raw_results:
            city_name = item.get("name", "").strip()
            admin1 = item.get("admin1", "").strip()
            country_code = item.get("country_code", "").strip()
            city_name = city_name.replace("'", "").replace('"', "").strip()

            api_results.append(
                {
                    "city": city_name,
                    "admin1": admin1,
                    "country": country_code,
                    "display": f"{city_name}, {admin1}" if admin1 else city_name,
                    "full_display": f"{city_name}, {admin1}, {country_code}"
                    if admin1
                    else f"{city_name}, {country_code}",
                    "lat": item.get("latitude"),
                    "lon": item.get("longitude"),
                },
            )
    except requests.exceptions.Timeout:
        warn_msg = f"Timeout during geocoding API call for query: {query}"
        logger.warning(warn_msg)
    except requests.exceptions.RequestException as e:
        exc_msg = f"Error during geocoding API call for query '{query}': {e}"
        logger.exception(exc_msg)

    return api_results


def geocode_city_name(city_name_str: str) -> dict[str, Any] | None:
    """
    Geocodes a city name string using Open-Meteo Geocoding API.

    Returns:
        A dictionary with 'lat', 'lon', 'display_name', 'name_component',
        'admin1_component', 'country_component', or None if not found.
    """
    try:
        response = requests.get(
            GEOCODING_API_URL,
            params={
                "name": city_name_str,
                "count": GEOCODING_RESULT_COUNT,
                "language": GEOCODING_LANGUAGE,
            },
            timeout=GEOCODING_API_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("results"):
            item = data["results"][0]
            city = item.get("name", "").strip()
            admin1 = item.get("admin1", "").strip()
            country = item.get("country_code", "").strip()

            display_name_parts = [part for part in [city, admin1, country] if part]
            display_name = ", ".join(display_name_parts)

            return {
                "lat": float(item["latitude"]),
                "lon": float(item["longitude"]),
                "display_name": display_name,
                "name_component": city,
                "admin1_component": admin1,
                "country_component": country,
            }
    except requests.RequestException as e:
        exc_msg = f"Geocoding API failed for '{city_name_str}': {e}"
        logger.exception(exc_msg)
    except (ValueError, KeyError, IndexError) as e:
        exc_msg = f"Error processing geocoding response for '{city_name_str}': {e}"
        logger.exception(exc_msg)
    return None


def prepare_location_data_for_session(
    city_name_selected: str,
    lat_str: str | None,
    lon_str: str | None,
) -> dict[str, str | float | None]:
    """
    Prepares the location data dictionary to be stored in the session.
    Attempts to convert lat/lon to float, stores as string if successful
    for consistency.
    """
    location_data: dict[str, str | float | None] = {"display": city_name_selected}

    if lat_str and lon_str:
        try:
            # validation
            parsed_lat = float(lat_str)
            parsed_lon = float(lon_str)
            location_data["lat"] = str(parsed_lat)
            location_data["lon"] = str(parsed_lon)
        except ValueError:
            warn_msg = (
                f"Invalid lat/lon strings received for session:"
                f" lat='{lat_str}', lon='{lon_str}' for city:"
                f" {city_name_selected}"
            )
            logger.warning(warn_msg)
            location_data["lat"] = None  # Explicitly set to None if parsing fails
            location_data["lon"] = None
    else:
        location_data["lat"] = None
        location_data["lon"] = None

    return location_data


def parse_datetime_entry(entry_list, key_name, is_date_only=False):  # noqa: FBT002
    """
    Helper function to parse date/time strings within a list of dictionaries.
    Modifies the list in place.
    """
    if not isinstance(entry_list, list):
        warn_msg = (
            f"Expected a list for '{key_name}' processing, got {type(entry_list)}"
        )
        logger.warning(warn_msg)
        return

    for i, entry in enumerate(entry_list):
        if not isinstance(entry, dict):
            warn_msg = f"Item in '{key_name}' list is not a dict: {entry}"
            logger.warning(warn_msg)
            entry_list[i] = None
            continue

        value_str = entry.get(key_name)

        if isinstance(value_str, str):
            try:
                dt_obj = datetime.fromisoformat(value_str)
                entry[key_name] = dt_obj.date() if is_date_only else dt_obj
            except ValueError as e:
                exc_msg = (
                    f"Error parsing ISO string '{value_str}' for '{key_name}': {e}"
                )
                logger.exception(exc_msg)
                entry[key_name] = None
        elif not isinstance(value_str, (datetime, date if is_date_only else datetime)):
            warn_msg = (
                f"Unexpected type for '{key_name}':"
                f" {type(value_str)} in {entry}. Expected string."
            )
            logger.warning(warn_msg)
            entry[key_name] = None


def parse_session_location_data(  # noqa: C901,PLR0911,PLR0912,PLR0915
    session_data: dict[str, Any] | str | None,
) -> dict[str, Any] | None:
    """
    Parses location data from the session to extract lat, lon, and display components.
    Handles dict (from autocomplete) or string (direct input or "lat,lon").
    """
    if not session_data:
        logger.warning("No location data found in session.")
        return None

    lat: float | None = None
    lon: float | None = None
    # Provide sensible defaults
    default_display_name = "Unknown Location"
    name_component = "Unknown"
    admin1_component = ""
    country_component = "XX"

    if isinstance(session_data, dict):
        try:
            raw_lat = session_data.get("lat")
            raw_lon = session_data.get("lon")

            if raw_lat is not None and raw_lon is not None:
                lat = float(raw_lat)
                lon = float(raw_lon)
            else:  # lat/lon might be None if only the display name was provided
                info_msg = f"Missing lat/lon in session dict: {session_data}. "
                logger.info(info_msg)
                # Attempt to geocode based on the display name if lat/lon are missing
                display_name_from_dict = session_data.get("display")
                if display_name_from_dict:
                    geocoded = geocode_city_name(display_name_from_dict)
                    if geocoded:
                        return geocoded  # Return early with geocoded data
                return (
                    None  # Cannot proceed without lat/lon or display name for geocoding
                )

            display_name = session_data.get(
                "display",
                f"{lat:.4f},{lon:.4f}" if lat and lon else default_display_name,
            )

            # Prioritize components if they were stored, else parse from display_name
            name_component = session_data.get("name", "").strip()
            admin1_component = session_data.get("admin1", "").strip()
            country_component = session_data.get("country", "").strip()

            if not (
                name_component and country_component
            ):  # If components are missing, try parsing
                name_parts = [part.strip() for part in display_name.split(",")]
                name_component = name_parts[0] if name_parts else name_component
                if len(name_parts) > SEARCH_MIN_LETTERS:
                    admin1_component = name_parts[1]
                    country_component = name_parts[-1]
                elif len(name_parts) == SEARCH_MIN_LETTERS:
                    country_component = name_parts[1]
                elif (
                    len(name_parts) == ONE_LETTER and country_component == "XX"
                ):  # No country info from parsing
                    country_component = "XX"

        except (ValueError, KeyError, TypeError) as e:
            exc_msg = (
                f"Invalid dictionary location data from session: {session_data}."
                f" Error: {e}"
            )
            logger.exception(exc_msg)
            return None

    elif isinstance(session_data, str):
        display_name = session_data
        if "," in session_data and session_data.count(",") == 1:
            try:
                raw_lat_str, raw_lon_str = map(str.strip, session_data.split(","))
                lat = float(raw_lat_str)
                lon = float(raw_lon_str)
                name_component = (
                    session_data  # Use "lat,lon" as the name for City model default
                )
            except ValueError:
                warn_msg = (
                    f"Could not parse coordinates from string: {session_data}."
                    f" Geocoding as name."
                )
                logger.warning(warn_msg)

        if lat is None or lon is None:  # If not "lat,lon" or parsing failed
            geocoded = geocode_city_name(session_data)
            if not geocoded:
                warn_msg = f"Could not geocode location string: {session_data}"
                logger.warning(warn_msg)
                return None
            return geocoded  # geocoded already has all necessary parts
    else:
        err_msg = f"Invalid location data type in session: {type(session_data)}"
        logger.error(err_msg)
        return None

    if lat is None or lon is None:
        err_msg = f"Failed to determine lat/lon for session data: {session_data}."
        logger.error(err_msg)
        return None

    return {
        "lat": lat,
        "lon": lon,
        "display_name": display_name,
        "name_component": name_component,
        "admin1_component": admin1_component,
        "country_component": country_component,
    }


def fetch_weather_api_data(lat: float, lon: float) -> dict[str, Any] | None:
    """Fetches raw weather data from Open-Meteo forecast API."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,weather_code,precipitation_probability,"
        "windspeed_10m,winddirection_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "current_weather": "true",
        "timezone": "auto",
    }
    try:
        response = requests.get(
            WEATHER_API_URL,
            params=params,
            timeout=WEATHER_API_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        exc_msg = f"Weather API call failed for {lat},{lon}: {e}"
        logger.exception(exc_msg)
        return None


def process_raw_weather_data(raw_data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Processes raw weather API data:
    - Flattens hourly/daily into lists of dicts.
    - Converts datetime objects to ISO strings for session serialization.
    Returns processed data or None if input is invalid.
    """
    if not raw_data:
        return None

    processed_hourly_forecast: list[dict[str, Any]] = []
    hourly_api_data = raw_data.get("hourly", {})
    if hourly_api_data:
        # Ensure all expected lists are present and get their lengths
        times_str = hourly_api_data.get("time", [])
        temps = hourly_api_data.get("temperature_2m", [])
        codes = hourly_api_data.get("weather_code", [])
        precip = hourly_api_data.get("precipitation_probability", [])
        wind_s = hourly_api_data.get("windspeed_10m", [])
        wind_d = hourly_api_data.get("winddirection_10m", [])

        # Determine the number of full hourly records we can create
        num_hours = min(
            len(times_str),
            len(temps),
            len(codes),
            len(precip),
            len(wind_s),
            len(wind_d),
        )

        for i in range(num_hours):
            try:
                time_obj = datetime.fromisoformat(times_str[i])
                processed_hourly_forecast.append(
                    {
                        "time": time_obj.isoformat(),  # Store as ISO string
                        "temperature": temps[i],
                        "weather_code": codes[i],
                        "precipitation_probability": precip[i],
                        "windspeed": wind_s[i],
                        "winddirection": wind_d[i],
                    },
                )
            except (ValueError, TypeError, IndexError) as e:
                warn_msg = f"Skipping invalid hourly data at index {i}: {e}."
                logger.warning(warn_msg)
                continue

    processed_daily_forecast: list[dict[str, Any]] = []
    daily_api_data = raw_data.get("daily", {})
    if daily_api_data:
        times_str_daily = daily_api_data.get("time", [])
        temp_max = daily_api_data.get("temperature_2m_max", [])
        temp_min = daily_api_data.get("temperature_2m_min", [])
        codes_daily = daily_api_data.get("weather_code", [])

        num_days = min(
            len(times_str_daily),
            len(temp_max),
            len(temp_min),
            len(codes_daily),
        )

        for i in range(num_days):
            try:
                # Daily time is just a date string 'YYYY-MM-DD'
                date_obj = date.fromisoformat(times_str_daily[i])
                processed_daily_forecast.append(
                    {
                        "day": date_obj.isoformat(),  # Store as ISO string
                        "temp_max": temp_max[i],
                        "temp_min": temp_min[i],
                        "weather_code": codes_daily[i],
                    },
                )
            except (ValueError, TypeError, IndexError) as e:
                warn_msg = f"Skipping invalid daily data at index {i}: {e}."
                logger.warning(warn_msg)
                continue

    return {
        "current_weather": raw_data.get("current_weather"),
        "hourly_processed": processed_hourly_forecast,
        "daily_processed": processed_daily_forecast,
        "latitude": raw_data.get("latitude"),
        "longitude": raw_data.get("longitude"),
        "timezone": raw_data.get("timezone"),
        "elevation": raw_data.get("elevation"),
    }


def update_city_and_history(
    user: Any,  # Should be request.user
    parsed_location: dict[str, Any],
) -> None:
    """
    Updates or creates a City record and logs search history for authenticated users.
    Expects parsed_location to contain 'lat', 'lon', 'name_component', etc.
    """
    lat = parsed_location["lat"]
    lon = parsed_location["lon"]

    try:
        city_obj, created = City.objects.get_or_create(
            latitude=round(lat, 5),
            longitude=round(lon, 5),
            defaults={
                "name": parsed_location["name_component"],
                "country": parsed_location["country_component"],
                "admin1": parsed_location["admin1_component"],
                "full_display_name": parsed_location["display_name"],
            },
        )
        if (
            not created
        ):  # If city exists, check if components or display name need update
            changed = False
            if city_obj.name != parsed_location["name_component"]:
                city_obj.name = parsed_location["name_component"]
                changed = True
            if city_obj.admin1 != parsed_location["admin1_component"]:
                city_obj.admin1 = parsed_location["admin1_component"]
                changed = True
            if city_obj.country != parsed_location["country_component"]:
                city_obj.country = parsed_location["country_component"]
                changed = True
            if city_obj.full_display_name != parsed_location["display_name"]:
                city_obj.full_display_name = parsed_location["display_name"]
                changed = True

            if changed:
                city_obj.save()

        if hasattr(user, "is_authenticated") and user.is_authenticated:
            SearchHistory.objects.create(user=user, city=city_obj)

    except Exception as e:
        exc_msg = (
            f"Database error during city/history update for"
            f" {parsed_location.get('display_name', f'{lat},{lon}')}: {e}"
        )
        logger.exception(exc_msg)


def parse_iso_strings_in_forecast_data(
    forecast_list: list[dict[str, Any]] | None,
    datetime_key: str,
    is_date_only: bool = False,  # noqa: FBT001,FBT002
) -> None:
    """
    Parses ISO date/datetime strings within a list of forecast dictionaries,
    converting them to datetime or date objects in place.

    Args:
        forecast_list: A list of dictionaries (e.g., hourly or daily forecast items).
                       Can be None if the key is missing from weather data.
        datetime_key: The key in each dictionary that holds the ISO string.
        is_date_only: If True, converts to a date object; otherwise, a datetime object.
    """
    if not isinstance(forecast_list, list):
        if forecast_list is not None:
            warn_msg = (
                f"Expected a list for '{datetime_key}' processing,"
                f" got {type(forecast_list)}. Skipping."
            )
            logger.warning(warn_msg)
        return

    for i, entry in enumerate(forecast_list):
        if not isinstance(entry, dict):
            warn_msg = (
                f"Item in '{datetime_key}' list is not a dict: {entry}."
                f" Skipping item at index {i}."
            )
            logger.warning(warn_msg)
            continue

        value_str = entry.get(datetime_key)

        if isinstance(value_str, str):
            try:
                dt_obj = datetime.fromisoformat(value_str)
                entry[datetime_key] = dt_obj.date() if is_date_only else dt_obj
            except ValueError:
                exc_msg = (
                    f"Error parsing ISO string '{value_str}' for"
                    f" '{datetime_key}' in entry: {entry}. Setting to None."
                )
                logger.exception(exc_msg)
                entry[datetime_key] = None
        elif not isinstance(
            value_str,
            (
                date if is_date_only else datetime,
                datetime if not is_date_only else date,
            ),
        ):
            warn_msg = (
                f"Unexpected type for '{datetime_key}': {type(value_str)}"
                f" in {entry}. Expected string. Setting to None."
            )
            logger.warning(warn_msg)
            entry[datetime_key] = None

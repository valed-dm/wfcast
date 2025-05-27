from django.urls import path

from wfcast.weather import views
from wfcast.weather.views import CitySearchView


urlpatterns = [
    path("", views.weather_results_view, name="weather_results"),
    path("city/", CitySearchView.as_view(), name="city_search"),
    path("get-weather/", views.get_weather_view, name="get_weather"),
    path("statistics/", views.search_statistics, name="search_statistics"),
]

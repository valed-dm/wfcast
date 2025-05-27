from django.urls import path

from wfcast.weather import views


urlpatterns = [
    path("", views.weather_results_view, name="weather_results"),
    path("city/", views.city_search_view, name="city_search"),
    path("get-weather/", views.get_weather_view, name="get_weather"),
    path("statistics/", views.search_statistics, name="search_statistics"),
]

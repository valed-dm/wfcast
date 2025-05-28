from typing import Any
from typing import cast

from django.db import models
from django.db.models import ForeignKey

from wfcast.users.models import User


class City(models.Model):
    name = models.CharField(max_length=100)
    admin1 = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    population = models.IntegerField(default=0, blank=True, null=True)
    timezone = models.CharField(max_length=50, blank=True, default="")
    full_display_name = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "admin1", "country"],
                name="unique_city_name_admin1_country",
            ),
            models.UniqueConstraint(
                fields=["latitude", "longitude"],
                name="unique_city_lat_lon",
            ),
        ]
        verbose_name_plural = "Cities"

    def __str__(self) -> str:
        if self.full_display_name:
            return cast("str", self.full_display_name)
        if self.admin1:
            return f"{self.name}, {self.admin1}, {self.country}"
        return f"{self.name}, {self.country}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Automatically populate full_display_name
        if self.admin1:
            self.full_display_name = f"{self.name}, {self.admin1}, {self.country}"
        else:
            self.full_display_name = f"{self.name}, {self.country}"
        super().save(*args, **kwargs)


class SearchHistory(models.Model):
    user: ForeignKey[User]
    city: ForeignKey[City]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    city = models.ForeignKey(City, on_delete=models.CASCADE)
    searched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-searched_at"]
        verbose_name_plural = "Search Histories"

    def __str__(self) -> str:
        return (
            f"{self.user.username if self.user else 'Anonymous'}"
            f" searched {self.city} at"
            f" {self.searched_at.strftime('%Y-%m-%d %H:%M')}"
        )

    @classmethod
    def get_search_stats(cls):
        """Returns top 10 most searched cities with counts"""
        return (
            cls.objects.values("city__full_display_name")
            .annotate(search_count=models.Count("id"))
            .order_by("-search_count")[:10]
        )

    @classmethod
    def get_user_search_stats(cls, user):
        """Returns a user's search history"""
        return (
            cls.objects.filter(user=user)
            .select_related("city")
            .order_by("-searched_at")[:20]
        )

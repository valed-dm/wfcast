from django import forms


class CityForm(forms.Form):
    city = forms.CharField(
        label="",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter city name or coordinates (lat,lon)",
                "class": "form-control",
                "id": "city-input",
            },
        ),
    )

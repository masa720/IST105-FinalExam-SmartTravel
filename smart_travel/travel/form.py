from django import forms

class TravelForm(forms.Form):
    start_city = forms.CharField(max_length=100)
    end_city = forms.CharField(max_length=100)
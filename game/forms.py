
from django import forms

from game.models import Room


class CreateRoomForm(forms.ModelForm):
    alias = forms.CharField(max_length=50)

    class Meta:
        model = Room
        fields = ['script'] 

class JoinRoomForm(forms.Form):
    code = forms.CharField(max_length=6)
    alias = forms.CharField(max_length=50)
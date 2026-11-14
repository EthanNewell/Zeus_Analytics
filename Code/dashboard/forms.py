from django import forms

from cases.models import Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["outcome", "comment"]
        widgets = {
            "comment": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Укажите основания и реквизиты документов"}
            )
        }

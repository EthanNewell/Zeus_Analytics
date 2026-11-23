from django import forms

from cases.models import Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["outcome", "comment"]
        widgets = {
            "outcome": forms.RadioSelect,
            "comment": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": "input",
                    "placeholder": "Что проверено, какие документы открыты, к какому выводу пришли",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["outcome"].choices = Review._meta.get_field("outcome").choices

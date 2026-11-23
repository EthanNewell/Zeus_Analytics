from django import forms

from cases.models import DocumentKind, Review
from cases.sources import SOURCES


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


class DocumentForm(forms.Form):
    """The upload window: one file, its type, where it came from and a free note."""

    file = forms.FileField(label="Файл")
    kind = forms.ChoiceField(
        label="Тип документа",
        required=False,
        choices=[("", "тип документа"), *DocumentKind.choices],
        widget=forms.Select(attrs={"class": "input", "aria-label": "Тип документа"}),
    )
    source = forms.ChoiceField(
        label="Источник",
        required=False,
        widget=forms.Select(attrs={"class": "input", "aria-label": "Источник"}),
    )
    note = forms.CharField(
        label="Дополнительная информация",
        required=False,
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "class": "input",
                "rows": 5,
                "placeholder": "дополнительная информация по документу",
                "aria-label": "Дополнительная информация",
            }
        ),
    )
    case = forms.UUIDField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].choices = [
            ("", "источник"),
            *((source.key, source.name) for source in SOURCES),
            ("other", "Другой источник"),
        ]

    def source_name(self):
        key = self.cleaned_data.get("source")
        return dict(self.fields["source"].choices).get(key, "") if key else ""

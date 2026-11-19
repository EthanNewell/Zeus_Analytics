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


class EvidenceForm(forms.Form):
    ORIGINS = [
        ("unknown", "Происхождение требует уточнения"),
        ("author_marked_real", "Реальный документ из первоисточника"),
        ("synthetic", "Синтетический пример"),
    ]
    title = forms.CharField(
        label="Название",
        max_length=200,
        widget=forms.TextInput(
            attrs={"class": "input", "placeholder": "Например: выписка ЕГРН от 12.02.2026"}
        ),
    )
    url = forms.URLField(
        label="Ссылка",
        required=False,
        max_length=500,
        assume_scheme="https",
        widget=forms.URLInput(attrs={"class": "input", "placeholder": "https://…"}),
    )
    file = forms.FileField(label="Файл", required=False)
    source_reference = forms.CharField(
        label="Источник и реквизиты",
        required=False,
        max_length=500,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Росреестр, запрос № …"}),
    )
    origin = forms.ChoiceField(
        label="Происхождение",
        choices=ORIGINS,
        initial="unknown",
        widget=forms.Select(attrs={"class": "input"}),
    )

    def clean(self):
        data = super().clean()
        if not data.get("url") and not data.get("file"):
            raise forms.ValidationError("Приложите файл или укажите ссылку.")
        return data

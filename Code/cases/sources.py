"""The one registry of data sources named by the research tables.

A source is matched against the «Источники данных: …» notes of every import, so the
page shows which indicators actually rest on it. Access to these systems through an API
is not claimed: the team works with the tables prepared from them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    url: str
    gives: str
    matches: tuple[str, ...]


SOURCES = (
    Source(
        "nspd",
        "НСПД — Национальная система пространственных данных",
        "https://nspd.gov.ru",
        "Границы и координаты участков, кадастровые номера, зоны.",
        ("НСПД",),
    ),
    Source(
        "egrn",
        "Росреестр, сведения ЕГРН",
        "https://rosreestr.gov.ru",
        "Правообладатели, вид и дата регистрации права, категория и ВРИ, выписки об объекте.",
        ("ЕГРН", "Росреестр"),
    ),
    Source(
        "gko",
        "Фонд данных государственной кадастровой оценки",
        "https://rosreestr.gov.ru",
        "Кадастровая стоимость до и после изменений, даты её определения и применения.",
        ("ГКО", "кадастровой оценки"),
    ),
    Source(
        "egrul",
        "ЕГРЮЛ / ЕГРИП, ФНС",
        "https://egrul.nalog.ru",
        "Учредители и руководители организаций, ИНН — для проверки связи покупателя с должностным лицом.",
        ("ЕГРЮЛ",),
    ),
    Source(
        "torgi",
        "ГИС «Торги»",
        "https://torgi.gov.ru",
        "Извещения, число участников, начальная и итоговая цена, договоры.",
        ("Торги", "torgi"),
    ),
    Source(
        "donland",
        "Официальный портал Правительства Ростовской области, раздел «Документы»",
        "https://www.donland.ru/documents/",
        "Распоряжения о переводе категорий, постановления об изменении ПЗЗ и генпланов.",
        ("Правительства Ростовской", "donland"),
    ),
    Source(
        "municipal",
        "Сайты администраций муниципальных образований",
        "",
        "Муниципальные акты, извещения о предоставлении участков.",
        ("администраций",),
    ),
    Source(
        "protocols",
        "Протоколы комиссий",
        "",
        "Кто участвовал в решении и как голосовал: комиссии по ПЗЗ и градостроительной деятельности.",
        ("протокол",),
    ),
)


def sources_with_usage(batches):
    """Each source with the indicator codes whose imported notes name it."""
    rows = []
    for source in SOURCES:
        codes = sorted(
            {
                batch.indicator
                for batch in batches
                if any(
                    token.lower() in (batch.sources_note + " " + batch.notes).lower()
                    for token in source.matches
                )
            },
            key=lambda code: int(code[1:]),
        )
        rows.append({"source": source, "codes": codes})
    return rows

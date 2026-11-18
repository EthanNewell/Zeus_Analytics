"""The one registry of indicator tables: columns, keys, links and wording.

Import reads tables through it, analysis attaches a rule to each code, the card and the
methodology page take labels from it. Adding an indicator = one entry here + one rule.
"""

import hashlib
import re
from dataclasses import dataclass, field

from .facts import (
    PRESENT,
    cadastral_numbers,
    fact_value,
    normalize_header,
    parse_points,
    parse_wkt_polygon,
    region_for,
)


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    kind: str = "text"  # text | date | number | points | wkt
    calculated: bool = False  # derived in the source table; the rule recomputes it
    mark: bool = False  # the research author's answer for this row (control set)
    document: bool = False  # a document / legal basis shown under «Документы»
    party: str = ""  # role of a participant shown under «Участники»
    timeline: str = ""  # event label on the case timeline
    required: bool = False

    @property
    def normalized(self):
        return normalize_header(self.header)


@dataclass(frozen=True)
class CaseSpec:
    reference: str
    title: str
    cadastral_number: str = ""
    object_kind: str = ""
    address: str = ""
    area_sq_m: float | None = None
    geometry: list | None = None


@dataclass(frozen=True)
class Indicator:
    code: str
    title: str
    short: str
    question: str
    kind: str  # main | context
    threshold: str
    limitations: str
    columns: tuple[Column, ...]
    key_column: str
    title_column: str
    resolve_cases: object = field(repr=False, default=None)

    def column(self, key):
        return next(column for column in self.columns if column.key == key)

    @property
    def label(self):
        return f"{self.code_display} · {self.short}"

    @property
    def code_display(self):
        return "И" + self.code[1:]


def _plot(facts, *, cadastral_key="cadastral", address_key=None, area_key=None, kind=""):
    numbers = cadastral_numbers(fact_value(facts, cadastral_key))
    if not numbers:
        return []
    number = numbers[0]
    address = fact_value(facts, address_key) if address_key else ""
    area = fact_value(facts, area_key) if area_key else None
    return [
        CaseSpec(
            reference=number,
            title=address or f"Земельный участок {number}",
            cadastral_number=number,
            object_kind=kind or "Земельный участок",
            address=address or "",
            area_sq_m=area if isinstance(area, int | float) else None,
        )
    ]


def _object_text_cases(facts, key):
    """И4/И6: the object is a free-text description with an embedded cadastral number."""
    text = fact_value(facts, key) or ""
    numbers = cadastral_numbers(text)
    kind = re.split(r"\s\d|\s\(", text.split(",")[0])[0].strip() if text else ""
    if numbers:
        address = _address_from_object(text)
        return [
            CaseSpec(
                reference=numbers[0],
                title=address or f"Объект {numbers[0]}",
                cadastral_number=numbers[0],
                object_kind=kind,
                address=address,
            )
        ]
    address = _address_from_object(text)
    return [
        CaseSpec(
            reference=_text_reference(text),
            title=address or text,
            object_kind=kind,
            address=address,
        )
    ]


def _address_from_object(text):
    parts = [part.strip() for part in text.replace("(", ",").replace(")", ",").split(",")]
    kept = [
        part
        for part in parts
        if part
        and "КН" not in part
        and "кв. м" not in part
        and not part.lower().startswith(("земельный участок", "нежилое", "с земельным"))
        and not part.lower().startswith("для ")
    ]
    return ", ".join(kept)


def _text_reference(text):
    return "ОБ-" + hashlib.sha1(text.encode()).hexdigest()[:8].upper()


def resolve_i1(facts):
    return _plot(facts, kind=fact_value(facts, "object_kind") or "Земельный участок")


def resolve_i2(facts):
    numbers = cadastral_numbers(fact_value(facts, "plots"))
    geometry = None
    if facts.get("geometry", {}).get("state") == PRESENT:
        geometry = parse_wkt_polygon(facts["geometry"]["value"])
    if numbers:
        return [
            CaseSpec(reference=number, title=f"Земельный участок {number}", cadastral_number=number)
            for number in numbers
        ]
    location = fact_value(facts, "location") or ""
    municipality = fact_value(facts, "municipality") or ""
    act = fact_value(facts, "approval_act") or fact_value(facts, "prep_act") or location
    return [
        CaseSpec(
            reference=_text_reference(f"{municipality}|{act}"),
            title=(location or municipality)[:120],
            object_kind="Территория изменения документа",
            address=f"{municipality}, {location}".strip(", "),
            geometry=geometry,
        )
    ]


def resolve_i3(facts):
    return _plot(facts, address_key="address", area_key="area")


def resolve_i4(facts):
    return _object_text_cases(facts, "object")


def resolve_i6(facts):
    return _object_text_cases(facts, "object")


def resolve_i8(facts):
    cases = _plot(facts)
    if cases and facts.get("coords", {}).get("state") == PRESENT:
        spec = cases[0]
        return [
            CaseSpec(
                reference=spec.reference,
                title=spec.title,
                cadastral_number=spec.cadastral_number,
                object_kind=spec.object_kind,
                geometry=parse_points(facts["coords"]["value"]),
            )
        ]
    return cases


def resolve_i10(facts):
    return [
        CaseSpec(reference=number, title=f"Земельный участок {number}", cadastral_number=number)
        for number in cadastral_numbers(fact_value(facts, "comment"))
    ]


C = Column
INDICATORS = {
    item.code: item
    for item in [
        Indicator(
            code="I1",
            title="Приобретение участка не более чем за 12 месяцев до смены категории",
            short="Покупка до смены категории",
            question="Не приобретён ли участок незадолго до перевода в более «дорогую» категорию?",
            kind="main",
            threshold="Смена категории не раньше регистрации права и не позднее 12 месяцев после неё. Окно 12 месяцев — настройка пилота, не правовая норма.",
            limitations="Дата присвоения кадастрового номера не заменяет дату приобретения права. Близость дат сама по себе не доказывает осведомлённость покупателя.",
            key_column="cadastral",
            title_column="cadastral",
            resolve_cases=resolve_i1,
            columns=(
                C("number", "№"),
                C("object_kind", "Вид объекта недвижимости"),
                C("status", "Статус объекта"),
                C("cadastral", "Кадастровый номер", required=True),
                C(
                    "cn_date",
                    "Дата присвоения кадастрового номера",
                    "date",
                    timeline="Присвоен кадастровый номер",
                ),
                C("ownership_form", "Форма собственности"),
                C("holder", "Правообладатель (по выписке ЕГРН)", party="Правообладатель"),
                C("right_kind", "Вид права"),
                C("right_number", "Номер государственной регистрации права", document=True),
                C(
                    "right_date",
                    "Дата государственной регистрации права",
                    "date",
                    timeline="Регистрация права",
                ),
                C("category_before", "Категория до перевода"),
                C("category_after", "Категория после перевода"),
                C("act", "Акт о переводе", document=True),
                C(
                    "category_change_date",
                    "Дата изменения категории",
                    "date",
                    timeline="Смена категории",
                ),
                C("days", "Дней от регистрации права до смены категории", calculated=True),
                C("mark", "Покупка ≤ 12 мес. до смены категории", mark=True),
            ),
        ),
        Indicator(
            code="I2",
            title="Адресная правка ПЗЗ или генплана под участки одного владельца",
            short="Точечная правка ПЗЗ / генплана",
            question="Не изменена ли зона ради участков одного правообладателя?",
            kind="main",
            threshold="Участки основного владельца занимают не меньше 80 % площади изменённой зоны. Порог 80 % — допущение исследования.",
            limitations="Индикатор передан «под вопросом»: нужны приложения к актам (границы зоны, правообладатели). Пример генплана не переносится автоматически на ПЗЗ.",
            key_column="approval_act",
            title_column="location",
            resolve_cases=resolve_i2,
            columns=(
                C("number", "№"),
                C("doc_kind", "Вид документа"),
                C("municipality", "Муниципальное образование", required=True),
                C("base_doc", "Исходный утверждённый документ", document=True),
                C(
                    "prep_act",
                    "Акт о подготовке изменений",
                    document=True,
                    timeline="Акт о подготовке изменений",
                ),
                C("protocol", "Протокол комиссии / общественных обсуждений", document=True),
                C(
                    "approval_act",
                    "Акт об утверждении изменений",
                    document=True,
                    timeline="Утверждение изменений",
                    required=True,
                ),
                C("justification", "Заявленное обоснование"),
                C("location", "Местоположение изменяемой территории"),
                C("zone_before", "Зона ДО изменений"),
                C("zone_after", "Зона ПОСЛЕ изменений"),
                C("geometry", "Геометрия изменённой зоны (WKT, WGS84)", "wkt"),
                C("zone_area", "Площадь изменённой зоны, га", "number"),
                C("owner_area", "Площадь участков основного владельца в зоне, га", "number"),
                C("owner_share", "Доля основного владельца в зоне", calculated=True),
                C("plots_count", "Кол-во участков в зоне", "number"),
                C("plots", "Кадастровые номера участков в зоне"),
                C(
                    "holders_prep",
                    "Правообладатели на дату акта о подготовке",
                    party="Правообладатели на дату подготовки",
                ),
                C(
                    "holders_approval",
                    "Правообладатели на дату утверждения",
                    party="Правообладатели на дату утверждения",
                ),
                C(
                    "owner_reg_date",
                    "Дата регистрации права основного владельца",
                    "date",
                    timeline="Регистрация права основного владельца",
                ),
                C("neighbors", "Соседние участки (КН)"),
                C("neighbor_holders", "Правообладатели соседних участков"),
                C("neighbor_zone", "Зона соседних участков после изменений"),
                C("mark", "Признак точечной правки (доля ≥ 80%)", mark=True),
            ),
        ),
        Indicator(
            code="I3",
            title="Рост кадастровой стоимости после смены категории и продажа с выгодой",
            short="Выгода после смены категории",
            question="Не реализована ли выгода от смены категории последующей продажей?",
            kind="context",
            threshold="КС после смены категории выше прежней, новая КС применяется не раньше смены категории, продажа — не раньше смены категории.",
            limitations="Контекстный признак: помогает восстановить механизм выгоды, но сам не формирует сигнал высокого приоритета. Рост КС — изменение оценки, а не доказательство прибыли.",
            key_column="cadastral",
            title_column="cadastral",
            resolve_cases=resolve_i3,
            columns=(
                C("number", "№"),
                C("cadastral", "Кадастровый номер", required=True),
                C("address", "Адрес (местоположение)"),
                C("area", "Площадь, кв. м", "number"),
                C("change_type", "Тип изменения"),
                C(
                    "holder",
                    "Правообладатель на дату смены категории",
                    party="Правообладатель на дату смены категории",
                ),
                C("right", "Вид, номер и дата регистрации права", document=True),
                C("category_before", "Категория до"),
                C("category_after", "Категория после"),
                C(
                    "category_change_date",
                    "Дата смены категории",
                    "date",
                    timeline="Смена категории",
                ),
                C("ks_before", "КС до, руб.", "number"),
                C("ks_before_det", "Дата определения КС до", "date"),
                C("ks_before_start", "Дата начала применения КС до", "date"),
                C("ks_after", "КС после, руб.", "number"),
                C("ks_after_det", "Дата определения КС после", "date"),
                C(
                    "ks_after_start",
                    "Дата начала применения КС после",
                    "date",
                    timeline="Применяется новая кадастровая стоимость",
                ),
                C("ks_egrn_date", "Дата внесения КС в ЕГРН", "date"),
                C("ks_basis", "Основание определения КС после", document=True),
                C("ks_delta", "Изменение КС, руб.", calculated=True),
                C("ks_ratio", "Рост КС, раз", calculated=True),
                C(
                    "ks_days",
                    "Дней от смены категории до начала применения новой КС (< 0 — изменение раньше смены)",
                    calculated=True,
                ),
                C("split_date", "Дата раздела (дробления)", "date", timeline="Раздел участка"),
                C("split_count", "Кол-во образованных участков", "number"),
                C("split_numbers", "КН образованных участков"),
                C(
                    "resale_date",
                    "Дата перепродажи (перехода права)",
                    "date",
                    timeline="Перепродажа",
                ),
                C("new_holder", "Новый правообладатель", party="Новый правообладатель"),
                C("deal_price", "Цена сделки, руб.", "number"),
                C(
                    "profit_sale",
                    "Продажа после смены категории с выгодой (рост КС)",
                    calculated=True,
                ),
                C("mark", "Соответствие индикатору", mark=True),
            ),
        ),
        Indicator(
            code="I4",
            title="Единственный участник или обход обязательных условий предоставления",
            short="Единственный участник торгов",
            question="Не получено ли имущество без реальной конкуренции или в обход условий?",
            kind="main",
            threshold="Один участник торгов либо описанные признаки обхода обязательных условий. Рост цены на торгах — отрицательный признак.",
            limitations="Один участник сам по себе не доказывает обход условий. Для помещений и зданий применимость к земельному сценарию проверяется отдельно.",
            key_column="object",
            title_column="object",
            resolve_cases=resolve_i4,
            columns=(
                C("number", "№"),
                C("object", "Объект (вид, адрес, кадастровый номер, площадь)", required=True),
                C(
                    "seller",
                    "Правообладатель (продавец / арендодатель)",
                    party="Продавец / арендодатель",
                ),
                C("method", "Способ предоставления и правовое основание", document=True),
                C("contract", "Вид договора, номер и дата", document=True, timeline="Договор"),
                C("participants", "Число участников", "number"),
                C("start_price", "Начальная цена, руб.", "number"),
                C("final_price", "Итоговая цена (цена договора), руб.", "number"),
                C(
                    "counterparty",
                    "Контрагент (победитель / единственный участник)",
                    party="Контрагент",
                ),
                C("bypass", "Признаки обхода обязательных условий"),
                C("mark", "Соответствие индикатору", mark=True),
            ),
        ),
        Indicator(
            code="I6",
            title="Приобретение связанным лицом до начала процедуры при участии должностного лица",
            short="Связанное лицо до процедуры",
            question="Не купил ли участок человек, связанный с чиновником, который потом участвовал в решении?",
            kind="main",
            threshold="Право зарегистрировано раньше начала процедуры, связь покупателя с участником решения подтверждена совпадением ИНН в ЕГРЮЛ (в том числе через цепочку юрлиц или прежних учредителей).",
            limitations="Совпадение одной фамилии — гипотеза, а не связь: результат «недостаточно данных» до подтверждения документами (ЕГРЮЛ, анкета, ЗАГС). Корректная контрольная цифра ИНН не подтверждает существование лица.",
            key_column="object",
            title_column="object",
            resolve_cases=resolve_i6,
            columns=(
                C("number", "№"),
                C("object", "Объект (вид, адрес, кадастровый номер)", required=True),
                C("buyer", "Покупатель (ФИО / наименование, ИНН)", party="Покупатель"),
                C(
                    "founders",
                    "Учредители и руководитель покупателя по ЕГРЮЛ (текущие и прежние)",
                    party="Учредители и руководитель покупателя",
                ),
                C(
                    "purchase_date",
                    "Дата регистрации права покупателя",
                    "date",
                    timeline="Регистрация права покупателя",
                ),
                C("procedure", "Процедура (вид, акт)", document=True),
                C("procedure_start", "Дата начала процедуры", "date", timeline="Начало процедуры"),
                C("days", "Дней от покупки до начала процедуры", calculated=True),
                C(
                    "official",
                    "Должностное лицо, участвовавшее в решении (ФИО, ИНН, должность, роль)",
                    party="Должностное лицо в решении",
                ),
                C("surname_match", "Совпадение фамилии"),
                C("inn_match", "Совпадение ИНН в ЕГРЮЛ"),
                C("link_level", "Уровень достоверности связи", calculated=True),
                C("mark", "Соответствие индикатору", mark=True),
            ),
        ),
        Indicator(
            code="I8",
            title="Аномалия формы границ участка",
            short="Аномалия границ",
            question="Нет ли у участка «хвостов», выступов или вклиниваний, выдающих прирезку?",
            kind="main",
            threshold="Коэффициент заполнения = площадь контура / площадь наименьшего описанного прямоугольника (с поворотом). Меньше 0,85 — аномалия. Считается по координатам, а не по площадям из таблицы.",
            limitations="Порог 0,85 — методическое допущение, требует калибровки. Изломанность границ (п. 6 ст. 11.9 ЗК РФ) — признак для проверки, а не нарушение.",
            key_column="cadastral",
            title_column="cadastral",
            resolve_cases=resolve_i8,
            columns=(
                C("number", "№"),
                C("cadastral", "Кадастровый номер", required=True),
                C("shape", "Форма участка"),
                C("coords", "Координаты характерных точек (WGS-84: широта долгота)", "points"),
                C("area", "Площадь участка, кв. м", "number"),
                C("rect_area", "Площадь описанного прямоугольника, кв. м", "number"),
                C("fill", "Коэффициент заполнения", calculated=True),
                C("mark", "Индикатор аномалии границ", mark=True),
            ),
        ),
        Indicator(
            code="I10",
            title="Повторяемость должностного лица в других индикаторах",
            short="Повтор должностного лица",
            question="Не встречается ли одно и то же должностное лицо в нескольких подозрительных эпизодах?",
            kind="main",
            threshold="Лицо фигурирует в иных индикаторах больше одного раза.",
            limitations="Все лица в наборе синтетические. Для расчёта на реальных данных нужны идентификаторы лиц и исключение повторного счёта одного эпизода.",
            key_column="person",
            title_column="person",
            resolve_cases=resolve_i10,
            columns=(
                C("number", "№"),
                C("person", "ФИО должностного лица", required=True),
                C("repeats", "Число повторений в иных индикаторах", "number"),
                C("comment", "Комментарий"),
                C("mark", "Соответствие индикатору", mark=True),
            ),
        ),
    ]
}


def detect(headers):
    """Pick the indicator whose columns best match a header row; None if unsure."""
    present = {normalize_header(header) for header in headers if header}
    best, best_score = None, 0.0
    for indicator in INDICATORS.values():
        wanted = {column.normalized for column in indicator.columns if column.key != "number"}
        score = len(wanted & present) / len(wanted)
        if score > best_score:
            best, best_score = indicator, score
    return best if best_score >= 0.8 else None


def region_of(spec):
    return region_for(spec.cadastral_number, spec.address)

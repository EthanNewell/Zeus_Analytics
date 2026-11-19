"""Замер скорости анализа: демо-набор как есть и размноженный в N раз.

Работает только во временной базе SQLite, в пути которой есть «bench»: скрипт дописывает
в базу копии записей и объектов. Перед запуском база готовится по README
(migrate, bootstrap_roles, demo_users, load_tables demo_data --user head).

    DB_ENGINE=sqlite DJANGO_SETTINGS_MODULE=config.settings.local SQLITE_PATH=/tmp/bench/db.sqlite3 \
        .venv/bin/python tools/bench_scale.py [--factor 100] [--runs 5] [--user head]

Копия записи получает свой ключ («исходный ключ #n»), копия объекта — свой идентификатор,
поэтому число объектов растёт вместе с числом записей. Факты копий совпадают с исходными.
Время — полный вызов analysis.services.run_analysis: чтение записей, расчёт правил,
сохранение результатов и итогов объектов. Результаты прошлых запусков остаются в базе,
как в сервисе.
"""

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.db import transaction  # noqa: E402

from analysis.services import run_analysis  # noqa: E402
from cases.models import Case, Record  # noqa: E402


def measure(actor, runs):
    times, last = [], None
    for _ in range(runs):
        started = time.perf_counter()
        last = run_analysis(actor=actor)
        times.append((time.perf_counter() - started) * 1000)
    return times, last


def report(name, times, run):
    series = ", ".join(f"{value:.1f}" for value in times)
    print(
        f"{name}: записей {run.records_count}, объектов {run.cases_count}, "
        f"сработало {run.triggered_count}, сверка {run.agreed_count}/{run.compared_count}"
    )
    print(f"  прогоны, мс: {series}")
    print(
        f"  медиана {statistics.median(times):.1f} мс, "
        f"минимум {min(times):.1f}, максимум {max(times):.1f}"
    )


@transaction.atomic
def multiply(factor):
    """Add factor-1 copies of every record and of every case, linked the same way."""
    records = list(Record.objects.prefetch_related("cases"))
    cases = list(Case.objects.all())
    through = Record.cases.through
    for n in range(1, factor):
        case_copy = {}
        for case in cases:
            copy = Case(
                reference=f"{case.reference}#{n}",
                title=case.title,
                cadastral_number=case.cadastral_number,
                object_kind=case.object_kind,
                address=case.address,
                region=case.region,
                area_sq_m=case.area_sq_m,
                geometry=case.geometry,
                origin=case.origin,
                is_demonstration=case.is_demonstration,
                source_reference=case.source_reference,
            )
            case_copy[case.pk] = copy
        Case.objects.bulk_create(case_copy.values())
        record_copies, links = [], []
        for record in records:
            copy = Record(
                indicator=record.indicator,
                source_key=f"{record.source_key[:190]} #{n}",
                title=record.title,
                batch_id=record.batch_id,
                sheet=record.sheet,
                row_number=record.row_number,
                facts=record.facts,
                author_mark=record.author_mark,
                is_demonstration=record.is_demonstration,
            )
            record_copies.append(copy)
            links += [
                through(record_id=copy.pk, case_id=case_copy[case.pk].pk)
                for case in record.cases.all()
            ]
        Record.objects.bulk_create(record_copies)
        through.objects.bulk_create(links)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--factor", type=int, default=100)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--user", default="head")
    args = parser.parse_args()
    database = settings.DATABASES["default"]
    if "sqlite" not in database["ENGINE"] or "bench" not in str(database["NAME"]):
        sys.exit("Нужна временная база SQLite с «bench» в пути: скрипт дописывает копии записей.")
    actor = get_user_model().objects.get(username=args.user)
    if Record.objects.filter(source_key__contains=" #").exists():
        sys.exit("База уже размножена: создайте чистую.")

    run_analysis(actor=actor)  # прогрев: импорт модулей, соединение
    times, run = measure(actor, args.runs)
    report("Демо-набор", times, run)

    started = time.perf_counter()
    multiply(args.factor)
    print(f"Размножение ×{args.factor}: {time.perf_counter() - started:.1f} с")
    run_analysis(actor=actor)  # прогрев на новом объёме
    times, run = measure(actor, args.runs)
    report(f"Набор ×{args.factor}", times, run)


if __name__ == "__main__":
    main()

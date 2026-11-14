# Код прозрачности — каркас Django

Запускаемый каркас для команды из пяти разработчиков: Django 5.2 LTS, Python 3.12, MySQL 8.4 и серверные шаблоны.

## Что реализовано

- Пользователь `accounts.User`, вход, выход по POST и группа `Specialist` с явными разрешениями.
- Закрытые по умолчанию маршруты; CSRF, проверка прав, защищённая выдача вложений.
- Минимальные модели `Case`, `Evidence`, `Review`, миграции, реестр с поиском и пагинацией, карточка, история проверки и CSV-выгрузка с защитой от формул.
- Явно синтетические примеры, создаваемые командой `seed_demo`, без заданных паролей и вымышленных результатов правил.
- Контракты модулей `imports` и `analysis`, проверки состояния, request ID и журналы запросов без тела формы и query string.
- Docker для локальной среды, конфигурация HTTPS-стенда, CI с MySQL.

Импорт CSV и земельные правила ещё не реализованы: их адаптеры возвращают понятный отказ с HTTP 501 и не изменяют данные. Полная предметная схема, происхождение каждого поля, снимки фактов для анализа и `AnalysisRun`/`RuleResult` в БД — следующие задачи №2 и №3. Сейчас выгрузка содержит исходные сведения каркаса и `analysis_status=not_run`.

## Быстрый запуск с Docker и MySQL

Нужны Docker Engine/Desktop и Docker Compose v2 с поддержкой `--wait`. Все команды этого раздела выполняются из `Code/`.

```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose exec web python manage.py migrate
docker compose exec web python manage.py bootstrap_roles
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo
```

Откройте [приложение](http://localhost:8000/) и войдите под созданной учётной записью. Пароль задаётся интерактивно; пароля по умолчанию нет. В [администрировании](http://localhost:8000/admin/) можно создать обычного пользователя и включить его в группу `Specialist`. Пользователю не нужны флаги staff/superuser для работы с реестром.

`.env.example` содержит только локальные примеры секретов. Для общей среды используйте отдельные значения. Django не загружает `.env` самостоятельно: Compose передаёт переменные процессу.

Код включается в локальный образ при сборке. После изменений выполните `docker compose up -d --build --wait`; после изменений моделей отдельно примените миграции и обновите роли. Том БД сохраняется между пересборками. `docker compose down` останавливает среду; флаг `-v` удаляет данные и для обычной остановки не нужен.

## Запуск без Docker для локальной проверки

SQLite включается только явно и не заменяет MySQL-проверки CI. Нужен Python 3.12; установите инструменты в отдельное окружение:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
export DB_ENGINE=sqlite
export DJANGO_SETTINGS_MODULE=config.settings.local
python manage.py migrate
python manage.py bootstrap_roles
python manage.py createsuperuser
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

Этот режим использует `local.sqlite3`, локальный ключ разработки и `DEBUG=True`. Для нативного MySQL установите клиентские заголовки, `pkg-config` и `requirements-mysql.txt`, задайте `DB_ENGINE=mysql` и `MYSQL_*` в окружении. Базовый режим базы — MySQL; SQLite не включается автоматически при ошибке соединения.

## Проверки

```bash
ruff check .
ruff format --check .
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
python manage.py test --settings=config.settings.test
```

Для проверки без сервера БД задайте `DB_ENGINE=sqlite` перед этими командами. CI запускает их с MySQL 8.4 и создаёт отдельную тестовую базу. Пользователю тестовой среды нужны права на её создание; пользователь приложения на стенде не получает таких прав и не использует root.

Зависимости зафиксированы в `requirements.txt`, драйвер — в `requirements-mysql.txt`, инструменты разработки — в `requirements-dev.txt`. При обновлении сначала измените `.in`, затем выполните `pip-compile requirements.in` и `pip-compile requirements-dev.in`, проверьте обе среды. Версия драйвера обновляется отдельно в `requirements-mysql.txt`.

## Модули и владельцы

| Модуль | Назначение | Владелец |
|---|---|---|
| `accounts`, `core`, `config` | Доступ, настройки, CI, стенд | №1 |
| `cases`, `imports` | Предметные данные, миграции, импорт | №2 |
| `analysis` | Правила и сохранение результатов | №3 |
| `dashboard`: реестр | Список, поиск, загрузка | №4 |
| `dashboard`: карточка | История, документы, выгрузка | №5 |

Модели `Case`, `Evidence`, `Review` — начальная точка интеграции, не полная земельная модель. Набор случаев пока общий для одного подразделения. Перед добавлением нескольких подразделений потребуется фильтрация всех чтений, записей и выгрузок по принадлежности.

Соглашения: [conventions.md](docs/conventions.md). Подключение модулей: [contracts.md](docs/contracts.md). Стенд и восстановление: [deploy.md](docs/deploy.md). Проверка выпуска: [smoke-check.md](docs/smoke-check.md).

## Проверки состояния

- `/health/live/` — публичный GET, 200 при работающем процессе; без запроса к БД.
- `/health/ready/` — публичный GET, 200 только при доступной БД и отсутствии неприменённых миграций; иначе 503 без технических подробностей.

Проверка контейнера использует live, поэтому первый запуск возможен до миграций. Перед открытием пользовательского трафика обязательна ready. Статика отдаётся WhiteNoise из версии образа, вложения — только через проверяющее права представление.

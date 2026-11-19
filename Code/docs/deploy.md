# Стенд, выпуск и восстановление

Конфигурация готова для одного сервера с Docker Compose v2. Сервер, домен, реестр образов и доступ к Git-хостингу должны быть предоставлены командой. Удалённый стенд автоматически не создаётся.

## Подготовка

1. Направить домен на сервер, открыть 80/443. БД и web не публикуют порты; SSH ограничивается средствами хостинга.
2. Получить TLS-сертификат для домена выбранным в организации способом. Сохранить `fullchain.pem` и `privkey.pem` в `deploy/tls/`, с правами доступа только у администратора сервера. Каталог исключён из Git и Docker-контекста. Продление сертификата настраивается отдельно; после продления перезагрузить proxy.
3. Скопировать `.env.staging.example` в `.env.staging`, заменить все примеры, задать домен и HTTPS-origin. Секрет Django — случайная строка не менее 50 символов; пароли MySQL различаются. Файл хранить с правами 600 вне публикации.
4. Зафиксировать образ приложения по SHA/digest. Сборка из `Code/`: `docker build -t registry.example.org/team/transparency:COMMIT_SHA .`. Проверить образ в CI и опубликовать в своём реестре либо передать через `docker save`/`docker load`. Записать адрес/тег в `APP_IMAGE`, коммит — в `APP_VERSION`.

`scripts/staging.sh` — сокращение для `docker compose --env-file .env.staging -f compose.staging.yaml`. Команды выполняются из `Code/`. Для публикации образа и реального сервера здесь не заданы учётные данные.

## Первый выпуск

```bash
sh scripts/staging.sh config --quiet
sh scripts/staging.sh pull
sh scripts/staging.sh up -d --wait db
sh scripts/staging.sh run --rm web python manage.py check --deploy --fail-level WARNING
sh scripts/staging.sh run --rm web python manage.py migrate --plan
sh scripts/staging.sh run --rm web python manage.py migrate --noinput
sh scripts/staging.sh run --rm web python manage.py bootstrap_roles
sh scripts/staging.sh run --rm web python manage.py createsuperuser
sh scripts/staging.sh run --rm web python manage.py demo_users
sh scripts/staging.sh run --rm -v /путь/к/таблицам:/data:ro web python manage.py load_tables /data --user head
sh scripts/staging.sh up -d --wait web
sh scripts/staging.sh exec -T web python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health/ready/', timeout=5)"
sh scripts/staging.sh up -d proxy
```

`demo_users` и `load_tables` — только по явному решению команды; рестарт ничего не загружает. Пароли `demo_users` печатаются один раз — сохраните их в менеджере паролей. Статика собрана в образе и отдаётся WhiteNoise. Проверьте `https://ВАШ-ДОМЕН/health/ready/`, вход и [smoke-check](smoke-check.md). Не считайте Docker health-check подтверждением применённых миграций: он использует live.

Встроенные HSTS-настройки ограничены одним хостом и одним часом. Проверки Django `security.W005` и `security.W021` явно исключены: стенд не управляет соседними поддоменами и не включается в браузерный preload list. Остальные предупреждения блокируют выпуск. Прокси перезаписывает `X-Forwarded-Proto`; прямого доступа к Gunicorn снаружи нет. В Nginx ограничены запросы входа и readiness. Лимит тела запроса — 3 МиБ; при изменении лимитов импорта согласованно обновить `client_max_body_size`, настройки Django и измерить обработку.

## Обновление

1. Убедиться, что CI прошёл. Записать старый образ, digest, переменные и список миграций. Подготовить новый `APP_IMAGE`/`APP_VERSION`, загрузить образ.
2. Остановить внешний трафик и процессы записи: `sh scripts/staging.sh stop proxy web`. В текущей конфигурации пользователи увидят недоступность стенда на время обновления; если нужна страница обслуживания, её отдельно настраивают на внешнем балансировщике.
3. Сделать согласованную копию БД и файлов по следующему разделу. Проверить план миграций и возможность отката.
4. Выполнить check deploy, migrate и bootstrap_roles отдельными `run --rm web` командами, как выше. Сбой прекращает выпуск; трафик не открывается.
5. `sh scripts/staging.sh up -d --wait web`; проверить ready из контейнера. Затем `sh scripts/staging.sh up -d --force-recreate proxy`, чтобы прокси разрешил актуальный адрес web.
6. Проверить внешний HTTPS и короткий пользовательский сценарий. Записать коммит, digest, миграции, время и исполнителя в журнал выпуска.

Миграции выполняются одним процессом. Gunicorn не запускает миграции при старте. `MYSQL_*` в уже созданном томе не переинициализируют пользователей: смена пароля требует отдельного изменения в MySQL и согласованного обновления окружения.

## Резервная копия

После остановки web/proxy, пока другие процессы не пишут в БД и файлы, создать каталог копии с ограниченным доступом. Снимок БД и вложений должен относиться к одному состоянию. Пример для заранее созданного пустого каталога `backups/release-copy/`:

```bash
mkdir -p backups/release-copy
chmod 700 backups backups/release-copy
sh scripts/staging.sh exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysqldump -u "$MYSQL_USER" --single-transaction --no-tablespaces --set-gtid-purged=OFF "$MYSQL_DATABASE"' > backups/release-copy/database.sql
sh scripts/staging.sh run --rm --no-deps -T --entrypoint tar web czf - -C /app/media . > backups/release-copy/media.tar.gz
chmod 600 backups/release-copy/*
```

Каждый выпуск использует новый каталог, чтобы не перезаписать прежнюю копию. Сохранить также конфигурацию без секретов, SHA/digest, список миграций и способ безопасного восстановления секретов. Проверить код возврата каждой команды и наличие файлов. Копия переносится в отдельное защищённое хранилище; место, срок хранения и ответственный фиксируются командой до реального показа.

## Восстановление

Сначала восстановить копию в отдельном Compose-проекте с **другим именем проекта, новыми томами и без публичного proxy**. Указать в `.env.staging` образ, соответствующий копии; работающий стенд должен использовать свою сохранённую конфигурацию. Для пробного восстановления:

```bash
sh scripts/staging.sh -p transparency-restore up -d --wait db
sh scripts/staging.sh -p transparency-restore exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -u "$MYSQL_USER" "$MYSQL_DATABASE"' < backups/release-copy/database.sql
sh scripts/staging.sh -p transparency-restore run --rm --no-deps -T --entrypoint tar web xzf - -C /app/media < backups/release-copy/media.tar.gz
sh scripts/staging.sh -p transparency-restore run --rm --no-deps web python manage.py migrate --check
sh scripts/staging.sh -p transparency-restore run --rm --no-deps -p 127.0.0.1:8766:8000 web
```

Последняя команда запускает восстановленное приложение в переднем плане, только на localhost. Чтобы проверить ready без внешнего HTTPS, в другом терминале выполните `curl --fail http://127.0.0.1:8766/health/ready/`. Пользовательский интерфейс настроен на HTTPS: для его проверки используйте отдельный тестовый домен и TLS-прокси в изолированной среде либо согласованную локальную конфигурацию для синтетических данных. Сам пробный стенд не открывает производственные порты и не использует прежние тома.

Действующие тома не удалять. Команды восстановления на рабочем стенде выполняются после остановки записи и выбора проверенной копии. Возврат старого образа не отменяет миграции: при совместимой схеме достаточно вернуть образ, при несовместимой нужен план возврата схемы либо восстановление согласованной копии БД и вложений. После появления новых записей восстановление старой копии требует отдельно учесть эти записи.

До финального релиза №2 подтверждает пробное восстановление, №1 — запуск выбранного образа на восстановленной БД. Резерв показа — локальный Compose, тот же образ и синтетический набор.

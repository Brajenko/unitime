# Квест 7 - миграция для фиксации слота

Проект: Unitime - поиск общего времени встречи учебной команды.
Дата занятия: 14.11.2026.
Очно работал: Константин Барайщук. Репозиторий: https://github.com/Brajenko/unitime (ветка `quest-7-migrations`)

## Политика миграций

СУБД - PostgreSQL 16; модели описаны в [`backend/app/models.py`](backend/app/models.py). Alembic читает их через [`backend/alembic/env.py`](backend/alembic/env.py). Ревизии хранятся в [`backend/alembic/versions/`](backend/alembic/versions/): `0001_initial` -> `0002_users_teams` -> [`0003_fixed_slots`](backend/alembic/versions/0003_fixed_slots.py). Порядок определяет `down_revision` внутри каждого файла. Ранее применённые файлы не меняем; следующая правка схемы получает новую ревизию.

Новая таблица `fixed_slots` хранит команду, автора, начало и конец встречи. Ограничение PostgreSQL `EXCLUDE USING gist` запрещает пересекающиеся интервалы в одной команде, в том числе при одновременных запросах. Соседние встречи допустимы благодаря интервалу `[)`. `btree_gist` нужен для сравнения UUID команды в GiST. `CHECK` запрещает пустой или обратный интервал и бесконечные даты. Откат удаляет таблицу и **все записи фиксаций**, поэтому его применяют лишь на тестовой БД или после отдельного бэкапа. Расширение при откате сохраняется: оно может использоваться другими объектами.

Для будущих изменений сначала меняем модель, затем на актуальной *отдельной* базе выполняем `alembic revision --autogenerate -m "описание"`. Полученный файл проверяем вручную: `upgrade`, `downgrade`, `revision`, `down_revision`, ограничения и неожиданные удаления. Alembic не гарантирует автогенерацию специальных ограничений. Команды из каталога `backend`: `alembic history --verbose`, `alembic current`, `alembic heads`, `alembic show 0003_fixed_slots`, `alembic upgrade head`. `DATABASE_URL` должен явно указывать нужную БД: [`env.py`](backend/alembic/env.py) берёт адрес из окружения и перекрывает им `alembic.ini`.

Alembic ведёт таблицу `alembic_version` с колонкой `version_num`: в линейной истории она содержит текущую ревизию. Успешное повторное `upgrade head` не применяет её снова. Перед выпуском ответственный участник команды проверяет новую ревизию на отдельной БД; при ошибке выпуск останавливается, состояние БД проверяется, исправление выпускается новой ревизией. Рабочий контейнер API сейчас сам выполняет `alembic upgrade head` при старте: сначала должен быть готов PostgreSQL, затем проходит миграция, затем запускается приложение. Поэтому **обычный `docker compose up` с этой веткой обновит основную БД `slot`**. Для квеста используется отдельный Compose-проект.

## Проверка на отдельной БД

Команды выполняются из корня репозитория. Не запускайте интеграционный `pytest` с `RUN_INTEGRATION=1` против `slot`: существующий тест очищает таблицы. Если имя `slot_migration_test` уже занято, не удаляйте базу - используйте новое имя и замените его во всех командах.

```powershell
docker compose up -d postgres
docker compose exec -T postgres createdb -U slot slot_migration_test
docker compose run --rm --no-deps --build -e DATABASE_URL=postgresql+psycopg://slot:slot@postgres:5432/slot_migration_test api alembic upgrade 0002_users_teams
docker compose exec -T postgres psql -U slot -d slot_migration_test -c "SELECT version_num FROM alembic_version"
```

Добавляем известного пользователя и команду в БД версии `0002`:

```powershell
docker compose exec -T postgres psql -U slot -d slot_migration_test -v ON_ERROR_STOP=1 -c "INSERT INTO app_users(id,email,password_hash) VALUES ('00000000-0000-0000-0000-000000000001','quest7@example.test','test-only'); INSERT INTO teams(id,name,invite_token,owner_id) VALUES ('00000000-0000-0000-0000-000000000002','Quest 7 team','quest7-test-token','00000000-0000-0000-0000-000000000001'); INSERT INTO team_members(id,team_id,user_id) VALUES ('00000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000001')"
docker compose run --rm --no-deps -e DATABASE_URL=postgresql+psycopg://slot:slot@postgres:5432/slot_migration_test api alembic upgrade head
docker compose run --rm --no-deps -e DATABASE_URL=postgresql+psycopg://slot:slot@postgres:5432/slot_migration_test api alembic upgrade head
docker compose exec -T postgres psql -U slot -d slot_migration_test -c "SELECT version_num FROM alembic_version; SELECT id,email FROM app_users; SELECT id,name FROM teams; SELECT conname,contype FROM pg_constraint WHERE conrelid='fixed_slots'::regclass ORDER BY conname"
```

Автоматическая проверка ограничений в контейнере API после `upgrade head`:

```powershell
docker compose run --rm --no-deps -e DATABASE_URL=postgresql+psycopg://slot:slot@postgres:5432/slot_migration_test -e RUN_MIGRATION_TEST=1 api python -B -m pytest -q tests/test_fixed_slots_migration.py
```

Проверка встреч: один слот 10–11, соседний 11–12 и слот другой команды с тем же временем принимаются; пересечение внутри команды отклоняется кодом `23P01`, неверный интервал - `23514`, неизвестный автор или команда - `23503`. Для одновременной проверки два соединения вставляют пересекающиеся встречи в одну команду: после подтверждения первой транзакции вторая получает `23P01`. В таблице остаётся одна из конфликтующих записей. Откат проверяется **только** на одноразовой тестовой БД командой `alembic downgrade 0002_users_teams`; затем `upgrade head` вновь создаёт пустую таблицу. Для проверки создания с нуля используйте вторую новую базу и `upgrade head`.

### Фактический результат

Проверено 14.11.2026 на отдельном временном контейнере PostgreSQL 16 с БД `slot_migration_test`. Основная БД `slot` не обновлялась.

- `alembic upgrade 0002_users_teams` создал исходную схему; перед новой миграцией добавлены пользователь, команда и участник.
- `alembic upgrade head` применил `0003_fixed_slots`; повторный запуск завершился без изменений.
- Исходные записи сохранились: по одному пользователю, команде и участнику. В БД есть `CHECK`, `EXCLUDE`, оба внешних ключа и первичный ключ таблицы `fixed_slots`.
- `RUN_MIGRATION_TEST=1 python -B -m pytest -q tests/test_fixed_slots_migration.py` - `1 passed`. Приняты соседние интервалы и одинаковое время разных команд; отклонены пересечение в команде, обратный интервал и неизвестный автор.
- `alembic check` - `No new upgrade operations detected`.
- `alembic downgrade 0002_users_teams` и повторный `alembic upgrade head` завершились успешно. Откат удаляет записи из `fixed_slots`, поэтому проверялся только на тестовой БД.

## Политика резервного копирования

Копируем PostgreSQL целиком в custom-архив `pg_dump -Fc`: в нём находятся пользователи, команды, подключения календарей, интервалы занятости, фиксированные встречи и `alembic_version`. Пользовательских файлов вне БД сейчас нет. Шифрованные секреты подключений можно прочитать после восстановления только с прежним `APP_SECRET`; его и рабочий `.env` ответственный участник хранит отдельно от дампов и Git. Если в проекте появятся загружаемые файлы, потребуется копировать их вместе с БД в одном согласованном окне и проверять оба набора при восстановлении.

Для текущего учебного сервиса выбираем **RPO 24 часа**: допустима потеря изменений не более чем за сутки. **RTO 2 часа**: за это время ответственный участник разворачивает PostgreSQL, восстанавливает архив, проверяет данные и запускает приложение. Частота — ежедневно в 03:00 по Москве. Срок хранения — 7 суток; скрипт сохраняет самую новую копию с корректной SHA-256 даже если она старше 7 суток. Это небольшая команда и сервис без непрерывных критичных операций; при реальных требованиях к сохранности частоту нужно повысить.

Для будущего развёртывания: запуск по расписанию на сервере, директория на **другом сервере или диске** (например, защищённая сетевая папка `\\backup-host\unitime`), доступ только ответственным за эксплуатацию. Задача по расписанию должна сохранять код возврата и журнал; ненулевой код или отсутствие нового `BACKUP_OK` к утру сообщается ответственному участнику. Ответственный участник раз в месяц восстанавливает последнюю копию в отдельную пустую БД и сверяет известные записи и версию схемы. Очистка выполняется только после успешной копии и сначала в режиме просмотра. Внешнее хранилище, расписание и уведомления **пока не настроены**; локальная проверка создания, восстановления и очистки выполнена ниже. Дампы и файлы SHA-256 исключены из Git через [`.gitignore`](.gitignore).

Команды выполняются из корня проекта на Windows с Python из `backend/.venv`. Для безопасного повторения используется отдельный Compose-проект `unitime-quest7-demo` с собственным томом и [дополнительным Compose-файлом](docker-compose.quest7.yml). Порт `55432` нужен только локальному Alembic. Если он занят, измените его в дополнительном файле и в `DATABASE_URL` ниже.

```powershell
docker compose -f docker-compose.yml -f docker-compose.quest7.yml -p unitime-quest7-demo up -d postgres
cd backend
$env:DATABASE_URL='postgresql+psycopg://slot:slot@127.0.0.1:55432/slot'
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\alembic.exe upgrade 0002_users_teams
cd ..
```

Добавьте тестовые записи в БД версии `0002`, затем примените новую миграцию и проверьте версию:

```powershell
docker compose -p unitime-quest7-demo exec -T postgres psql -U slot -d slot -v ON_ERROR_STOP=1 -c "INSERT INTO app_users(id,email,password_hash) VALUES ('00000000-0000-0000-0000-000000000001','quest7@example.test','test-only'); INSERT INTO teams(id,name,invite_token,owner_id) VALUES ('00000000-0000-0000-0000-000000000002','Quest 7 team','quest7-test-token','00000000-0000-0000-0000-000000000001'); INSERT INTO team_members(id,team_id,user_id) VALUES ('00000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000001')"
cd backend
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe upgrade head
cd ..
docker compose -p unitime-quest7-demo exec -T postgres psql -U slot -d slot -c "SELECT version_num FROM alembic_version"
```

Известный слот для проверки восстановления (вставляется после `0003`):

```powershell
docker compose -p unitime-quest7-demo exec -T postgres psql -U slot -d slot -c "INSERT INTO fixed_slots(id,team_id,created_by,starts_at,ends_at) VALUES ('00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000001','2026-11-16 10:00+03','2026-11-16 11:00+03')"
```

Скрипт [quest7_backup.py](scripts/quest7_backup.py) создаёт архив, проверяет его командой `pg_restore --list`, записывает SHA-256, восстанавливает **только в новую БД с именем `*_restore_test`**, а очистку сначала показывает без удаления. Для реальной эксплуатации вместо `backups/quest7-demo` укажите путь внешнего хранилища. Этот локальный каталог игнорируется Git.

```powershell
backend\.venv\Scripts\python.exe -B scripts\quest7_backup.py backup --project unitime-quest7-demo --database slot --directory backups\quest7-demo
$dump=(Get-ChildItem backups\quest7-demo\*.dump | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
backend\.venv\Scripts\python.exe -B scripts\quest7_backup.py restore --project unitime-quest7-demo --dump $dump --target slot_restore_test
docker compose -p unitime-quest7-demo exec -T postgres psql -U slot -d slot_restore_test -c "SELECT version_num FROM alembic_version; SELECT id,email FROM app_users; SELECT id,name FROM teams; SELECT id,starts_at,ends_at FROM fixed_slots"
backend\.venv\Scripts\python.exe -B scripts\quest7_backup.py prune --directory backups\quest7-retention-test --keep-days 7
backend\.venv\Scripts\python.exe -B scripts\quest7_backup.py prune --directory backups\quest7-retention-test --keep-days 7 --apply
```

`restore` требует новую пустую БД и сам её создаёт. При повторе используйте новое имя, например `slot_second_restore_test`; скрипт не перезаписывает существующую БД. Для проверки очистки подготовьте копии с известным возрастом:

```powershell
$source=(Get-ChildItem backups\quest7-demo\*.dump | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$target='backups\quest7-retention-test'
New-Item -ItemType Directory -Force -Path $target | Out-Null
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
foreach ($pair in @(@('11111111',0),@('22222222',2),@('33333333',9))) {
    $path=Join-Path $target "unitime-$stamp-$($pair[0]).dump"
    Copy-Item -LiteralPath $source -Destination $path
    Copy-Item -LiteralPath "$source.sha256" -Destination "$path.sha256"
    (Get-Item -LiteralPath $path).LastWriteTimeUtc=(Get-Date).ToUniversalTime().AddDays(-[int]$pair[1])
}
```

Теперь выполните обе команды `prune` из блока выше. Скрипт удаляет только архивы своего формата и их SHA-файлы, не трогает повреждённые или неизвестные файлы; если нет ни одной копии с корректной SHA-256, он не удаляет ничего.

### Фактический результат проверки бэкапов — 14.11.2026

- На изолированном Compose-проекте миграции `0001` → `0002` → `0003` применились к заполненной БД; повторный `upgrade head` ничего не изменил. `alembic_version.version_num = 0003_fixed_slots`.
- `backup` создал `unitime-20261114T112404Z-5047e6d6.dump`, SHA-256 `6de3e689501cac6d95a93ecd6332375c308b84e49d687f91beae1b1bf8a7359f`. `pg_restore --list` успешно прочитал архив.
- `restore` создал отдельную БД `slot_restore_test`. В ней проверены: пользователь `00000000-0000-0000-0000-000000000001` / `quest7@example.test`, команда `00000000-0000-0000-0000-000000000002` / `Quest 7 team`, один участник и слот `00000000-0000-0000-0000-000000000004` с временем 07:00–08:00 UTC (10:00–11:00 МСК). Версия миграции также `0003_fixed_slots`.
- На тестовых копиях возрастом 0, 2 и 9 дней просмотр показал `KEEP`, `KEEP`, `WOULD_DELETE`. После `--apply`: `KEEP`, `KEEP`, `DELETE`; удалена только 9-дневная копия, две более свежие и их SHA-файлы остались. Исходный дамп не затронут.

Для 3-минутной защиты покажите [миграцию](backend/alembic/versions/0003_fixed_slots.py), `SELECT version_num FROM alembic_version` в тестовой БД, запрос к `slot_restore_test` выше и вывод `prune` до/после. Тестовые дампы лежат только локально и не входят в репозиторий. Функция фиксации встречи в API и интерфейсе относится к следующей задаче, квест 7 требует схему и проверку её миграции.

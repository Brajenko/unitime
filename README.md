# Модуль занятости

Веб-приложение: регистрация по email и паролю, команды со ссылкой-приглашением, подключение календарей (Google / Яндекс / Apple или публичная ссылка на .ics), сетка занятости команды. Зелёным подсвечено всё время, куда встанет слот выбранной длины; при наведении слот достраивается от клетки. Названия событий в базу не пишутся.

## Запуск

```bash
cp .env.example .env
docker compose up --build
```

Откройте [http://localhost:3000](http://localhost:3000).

Одна команда поднимает Postgres, Redis, API, воркер, планировщик (`beat`, опрос календарей раз в 15 минут) и веб.

## OAuth-приложения (Google и Яндекс)

Это не хостинг. Нужны только клиентский id и секрет, как у любого «Войти через …».

### Google

1. Создайте проект в [Google Cloud Console](https://console.cloud.google.com/).
2. Включите **Google Calendar API**.
3. OAuth consent screen: External, статус Testing, добавьте тестовые email.
4. Credentials → OAuth client ID → Web application.
5. Authorized redirect URI: `http://localhost:3000/api/auth/google/callback`
6. Пропишите в `.env`:

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:3000/api/auth/google/callback
```

Запрашиваются `calendar.calendarlist.readonly` и `calendar.freebusy`: список календарей и занятость без названий.

### Яндекс

1. Зарегистрируйте приложение на [oauth.yandex.ru](https://oauth.yandex.ru/).
2. Тип: для авторизации пользователей, платформа Web.
3. Redirect URI: `http://localhost:3000/api/auth/yandex/callback`
4. Права: `calendar:all` и `login:email`.
5. В `.env`:

```
YANDEX_CLIENT_ID=...
YANDEX_CLIENT_SECRET=...
YANDEX_REDIRECT_URI=http://localhost:3000/api/auth/yandex/callback
```

После входа сервис ходит в CalDAV `https://caldav.yandex.ru` с заголовком `Authorization: OAuth …`.

### Apple

OAuth для iCloud Calendar нет. На шаге подключения:

1. Включите двухфакторную аутентификацию Apple ID.
2. [account.apple.com](https://account.apple.com) → Sign-In and Security → App-Specific Passwords.
3. Вставьте email и пароль приложения в форму.

Обычный пароль Apple ID сервер отклонит.

## Как пользоваться

0. Зарегистрируйтесь, создайте команду и отправьте участникам ссылку-приглашение из боковой панели.
1. На сетке нажмите **Подключить календарь**.
2. Выберите плитку, войдите в аккаунт (для Apple — пароль приложения).
3. Отметьте календари галочками → **Подключить**.
4. На сетке появятся градации «сколько календарей свободны» и синяя рамка предложенного слота.

Кнопка **Обновить** ставит ту же задачу воркеру. Стрелки листают недели.

## Публичная ссылка на календарь

Плитка «Ссылка на календарь» принимает публичный `.ics` (`https://` или `webcal://`) без входа в аккаунт. Это запасной путь: файл скачивается целиком, календари не выбираются. Сервер не ходит на внутренние адреса (защита от SSRF), URL хранится зашифрованно.

## Проверки без браузера

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Сквозной тест API на реальном Postgres (Redis подменяется fakeredis):

```bash
RUN_INTEGRATION=1 DATABASE_URL=postgresql+psycopg://slot:slot@localhost:5432/slot pytest tests/test_api_integration.py
```

Property-тест алгоритма слотов (10 000 случайных расписаний против поминутного эталона) входит в обычный `pytest`.

Проверка приватности: после привязки календаря в дампе не должно быть ни паролей, ни названий событий.

```bash
docker compose exec postgres pg_dump -U slot slot | grep -iE "<пароль приложения>|<название события>"
```

Нагрузка на `/api/grid`: `loadtest/grid.js` (k6), три прогона — без кеша (`GRID_CACHE_ENABLED=false`), с кешем, с ETag.

## Стек

FastAPI, Celery, Redis, PostgreSQL (`tstzrange`), React + Vite. Секреты шифруются AES-GCM ключом из `APP_SECRET`.

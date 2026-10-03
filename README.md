# Модуль занятости

Веб-приложение: вход в Google / Яндекс / Apple, выбор календарей, сетка недели и подсветка часов, где ни в одном выбранном календаре нет событий. Названия событий в базу не пишутся.

## Запуск

```bash
cp .env.example .env
docker compose up --build
```

Откройте [http://localhost:3000](http://localhost:3000).

Одна команда поднимает Postgres, Redis, API, воркер синхронизации и веб.

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

1. На сетке нажмите **Подключить календарь**.
2. Выберите плитку, войдите в аккаунт (для Apple — пароль приложения).
3. Отметьте календари галочками → **Подключить**.
4. На сетке появятся градации «сколько календарей свободны» и синяя рамка предложенного слота.

Кнопка **Обновить** ставит ту же задачу воркеру. Стрелки листают недели.

## Проверки без браузера

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## Стек

FastAPI, Celery, Redis, PostgreSQL (`tstzrange`), React + Vite. Секреты шифруются AES-GCM ключом из `APP_SECRET`.

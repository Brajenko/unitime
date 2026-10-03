# Настройка интеграций календарей для хостинга

Инструкция для выкладки приложения на публичный адрес. Локальный стенд (`localhost:3000`) здесь не рассматривается: у провайдеров в консоли должны быть **боевые** URL, иначе вход в Google и Яндекс не завершится.

Apple-приложение в консоли разработчика **не регистрируется**. OAuth-клиенты нужны только для Google и Яндекса.

## Что должно совпасть

Пусть публичный адрес приложения — `https://app.example.com` (без завершающего `/`).

Во всех трёх местах значения должны быть одинаковыми:

| Где | Значение |
| --- | --- |
| Браузер пользователя | `https://app.example.com` |
| `.env` хоста: `PUBLIC_URL` | `https://app.example.com` |
| Google / Яндекс: Redirect URI | `https://app.example.com/api/auth/<провайдер>/callback` |

`http://` на проде не используйте: Google отклоняет redirect на HTTP, кроме `localhost`. Нужны TLS и проксирование `/api/` на FastAPI (как в `frontend/nginx.conf`).

После смены `.env` пересоздайте контейнеры `api` и `worker` — переменные читаются при старте процесса.

## Переменные окружения хоста

```
APP_SECRET=<длинная случайная строка>
PUBLIC_URL=https://app.example.com
CORS_ORIGINS=https://app.example.com

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://app.example.com/api/auth/google/callback

YANDEX_CLIENT_ID=...
YANDEX_CLIENT_SECRET=...
YANDEX_REDIRECT_URI=https://app.example.com/api/auth/yandex/callback
```

`APP_SECRET` шифрует токены и пароли приложений в базе (AES-GCM). Смена ключа без миграции сделает уже сохранённые привязки нечитаемыми — пользователям придётся подключить календари заново.

Секреты в git не кладите. На хосте задайте их через секрет-хранилище или `.env` вне репозитория.

---

## Google Calendar

Приложение ходит в **Google Calendar API v3**: список календарей (`calendarList.list`) и занятость (`freeBusy.query`). Названия событий не запрашиваются и не хранятся.

### 1. Проект и API

1. [Google Cloud Console](https://console.cloud.google.com/) → создайте или выберите проект.
2. **APIs & Services → Library** → включите **Google Calendar API**.

Без включённого API вход может пройти, а синхронизация сетки — нет.

### 2. Экран согласия OAuth

**APIs & Services → OAuth consent screen.**

- User type: **External**.
- App name, support email, developer contact — обязательны.
- Authorized domain: домен из `PUBLIC_URL` (для `https://app.example.com` это `example.com`).
- Scopes (их запрашивает бэкенд):
  - `https://www.googleapis.com/auth/calendar.calendarlist.readonly`
  - `https://www.googleapis.com/auth/calendar.freebusy`
  - `openid`
  - `email`

**Пока приложение в статусе Testing**, войти могут только email из списка **Test users**. Добавьте туда операторов, которым нужна проверка.

**Для хостинга с произвольными пользователями** нажмите **Publish app**. Для чувствительных Calendar-scope Google может запросить проверку OAuth (верификация бренда). До публикации оставляйте Testing и тестовые ящики.

### 3. OAuth-клиент

**APIs & Services → Credentials → Create credentials → OAuth client ID.**

- Type: **Web application**.
- Authorized JavaScript origins:
  - `https://app.example.com`
- Authorized redirect URIs — **байт в байт**:
  - `https://app.example.com/api/auth/google/callback`

Не добавляйте путь без `/api`, другой порт, `www`, если его нет в `PUBLIC_URL`, и не смешивайте `http`/`https`.

Скопируйте Client ID и Client secret в `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.

Локальный redirect `http://localhost:3000/api/auth/google/callback` можно оставить **вторым** URI в том же клиенте, если тот же проект используют и для разработки.

### 4. Проверка после выкладки

1. Откройте `https://app.example.com/connect` → **Google**.
2. Должен открыться аккаунт Google, затем согласие на список календарей и free/busy.
3. После возврата выберите календари → **Подключить**.
4. На сетке нажмите **Обновить**. Ошибка `google_config` значит, что на хосте пустые `GOOGLE_CLIENT_*`.

---

## Яндекс Календарь

Тип приложения в [oauth.yandex.ru](https://oauth.yandex.ru/): **для авторизации пользователей**, платформа **Web**. Не выбирайте «для доступа к API»: там нельзя задать свой Redirect URI и нет `login:email`.

После входа бэкенд ходит в CalDAV `https://caldav.yandex.ru` с заголовком `Authorization: OAuth …`.

### 1. Регистрация

1. [Создать приложение](https://oauth.yandex.ru/) → **Для авторизации пользователей**.
2. Платформа: **Веб-сервисы**.
3. Redirect URI — **байт в байт**:
   - `https://app.example.com/api/auth/yandex/callback`
4. Доступы:
   - `calendar:all` — календари и занятость;
   - `login:email` — кто вошёл.

Списка тестовых пользователей у Яндекса нет: войдёт любой аккаунт, который согласится на права.

### 2. Переменные

ClientID и пароль приложения → `YANDEX_CLIENT_ID` / `YANDEX_CLIENT_SECRET`.  
`YANDEX_REDIRECT_URI` должен совпадать со строкой в кабинете OAuth.

Для разработки можно добавить второй Redirect URI `http://localhost:3000/api/auth/yandex/callback` в том же приложении.

### 3. Проверка после выкладки

1. `https://app.example.com/connect` → **Яндекс**.
2. Экран согласия Яндекса (не страница `?error=yandex_config`).
3. Выбор календарей → **Подключить** → **Обновить** на сетке.

---

## Apple / iCloud Calendar

Отдельного OAuth-приложения Apple и ключей на хосте **нет**. Каждый пользователь подключает свой iCloud через **пароль приложения**.

Что должен сделать пользователь (не администратор хоста):

1. Включить двухфакторную аутентификацию Apple ID.
2. [account.apple.com](https://account.apple.com) → Sign-In and Security → **App-Specific Passwords**.
3. Создать пароль, в форме приложения ввести **email Apple ID** и этот пароль (не пароль от Apple ID).

Сервер находит CalDAV через well-known iCloud (`caldav.icloud.com` и редирект на `pNN-caldav.icloud.com`) и забирает только интервалы занятости.

На хосте ничего регистрировать не нужно. Обычный пароль Apple ID iCloud отклонит.

---

## Сеть и прокси

Пользователь открывает один origin. Колбэки OAuth приходят на тот же хост:

```
GET https://app.example.com/api/connections/google/start
GET https://app.example.com/api/auth/google/callback
GET https://app.example.com/api/connections/yandex/start
GET https://app.example.com/api/auth/yandex/callback
POST https://app.example.com/api/connections/apple
```

Требования:

- HTTPS до пользователя.
- `/api/` проксируется на API (порт 8000 внутри compose).
- Заголовок `X-Forwarded-Proto` желателен, чтобы редиректы не уезжали на `http`.
- Воркер Celery должен иметь исходящий доступ к:
  - `accounts.google.com`, `oauth2.googleapis.com`, `www.googleapis.com`
  - `oauth.yandex.ru`, `login.yandex.ru`, `caldav.yandex.ru`
  - `caldav.icloud.com` и `pNN-caldav.icloud.com`

Синхронизация выполняется воркером, не в HTTP-запросе. Если Redis или worker не запущены, вход пройдёт, а сетка не обновится.

---

## Что сохраняется

В PostgreSQL пишутся только интервалы занятости (`uid`, начало/конец), без названий событий. Токены Google/Яндекс и пароль приложения Apple хранятся зашифрованными ключом `APP_SECRET`.

---

## Чеклист перед открытием пользователям

- [ ] `PUBLIC_URL` и `CORS_ORIGINS` — HTTPS-origin приложения
- [ ] Google Calendar API включён
- [ ] Redirect URI Google совпадает с `GOOGLE_REDIRECT_URI`
- [ ] Яндекс: тип «для авторизации», те же URI и права `calendar:all` + `login:email`
- [ ] `APP_SECRET` уникальный и сохранён вне git
- [ ] После правки `.env`: `docker compose up -d --force-recreate api worker`
- [ ] Плитки Google и Яндекс открывают экраны согласия провайдера
- [ ] Apple принимает app-specific password и показывает список календарей
- [ ] «Обновить» на сетке меняет занятость без `auth_failed`

Локальные URI (`http://localhost:3000/...`) на проде не подставляйте. Их можно держать **дополнительными** в кабинетах Google и Яндекса для разработки.

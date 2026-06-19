# Альтернативная продакшн-структура для `altair-school.ru`

> Этот вариант сохранен как reference для прямого односерверного контура.
> Текущая боевая схема проекта описана в `deploy/altair-edu/README.md`.

Этот вариант рассчитан на схему, где:

- домен `altair-school.ru` смотрит на внешний сервер
- `Flask` и `Gunicorn` работают на этом же сервере
- `PostgreSQL` уже доступен на сервере
- PWA и web push работают с боевого `HTTPS`-домена

## Когда этот вариант уместен

Для некоторых установок это может быть быстрее и безопаснее, чем схема
"внешняя оболочка -> локальный сервер":

- нет лишнего сетевого прыжка между внешним и локальным контуром
- `PWA`, `push` и `badge` работают с одного домена
- меньше точек отказа
- проще сопровождать резервные копии, логи и сертификаты

## Рекомендуемая структура на сервере

```text
/srv/school-tracker/
  current/                    # текущая версия проекта
  shared/.env.production      # боевые переменные окружения
  uploads/                    # загружаемые файлы
  secrets/firebase-service-account.json
  venv/
```

## Поток запросов

```text
Браузер / телефон
  -> https://altair-school.ru
  -> Nginx
  -> Gunicorn
  -> Flask
  -> PostgreSQL
```

## Что ставится на сервер

1. `python3`, `python3-venv`, `nginx`, `postgresql-client`
2. виртуальное окружение
3. зависимости из `requirements.txt`
4. `.env.production` на основе `.env.production.example`
5. systemd unit из `systemd/school-tracker.service`
6. Nginx-конфиг из `nginx/altair-school.ru.conf`
7. Let's Encrypt сертификат

## Базовые команды

### Подготовка

```bash
sudo mkdir -p /srv/school-tracker/shared /srv/school-tracker/uploads /srv/school-tracker/secrets
sudo chown -R www-data:www-data /srv/school-tracker
python3 -m venv /srv/school-tracker/venv
```

### Код и зависимости

```bash
sudo mkdir -p /srv/school-tracker/current
sudo rsync -av --delete ./ /srv/school-tracker/current/
/srv/school-tracker/venv/bin/pip install -r /srv/school-tracker/current/requirements.txt
```

### Переменные окружения

```bash
sudo cp /srv/school-tracker/current/.env.production.example /srv/school-tracker/shared/.env.production
sudo nano /srv/school-tracker/shared/.env.production
```

Важно заполнить:

- `SECRET_KEY`
- `DATABASE_URL`
- `APP_BASE_URL=https://altair-school.ru`
- `UPLOAD_FOLDER=/srv/school-tracker/uploads`
- `FIREBASE_SERVICE_ACCOUNT_FILE`
- все `FIREBASE_WEB_*`
- `FIREBASE_WEB_VAPID_KEY`

### Миграция / инициализация

```bash
cd /srv/school-tracker/current
set -a
source /srv/school-tracker/shared/.env.production
set +a
/srv/school-tracker/venv/bin/flask --app run repair-runtime-columns
```

### Systemd

```bash
sudo cp /srv/school-tracker/current/deploy/altair-school/systemd/school-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable school-tracker
sudo systemctl start school-tracker
sudo systemctl status school-tracker
```

### Nginx

```bash
sudo cp /srv/school-tracker/current/deploy/altair-school/nginx/altair-school.ru.conf /etc/nginx/sites-available/altair-school.ru.conf
sudo ln -s /etc/nginx/sites-available/altair-school.ru.conf /etc/nginx/sites-enabled/altair-school.ru.conf
sudo nginx -t
sudo systemctl reload nginx
```

### Let's Encrypt

```bash
sudo apt-get update
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d altair-school.ru -d www.altair-school.ru
```

## Проверки после запуска

Открыть:

- `https://altair-school.ru/healthz`
- `https://altair-school.ru/login`
- `https://altair-school.ru/static/manifest.webmanifest`

Проверить отдельно:

- вход в систему
- загрузку файлов
- push-токен PWA
- badge-счетчик после создания тестового уведомления

## Что хранить только на сервере

- `.env.production`
- Firebase service account
- SMTP-пароли
- токены бота

Не класть их в git.

## Если нужен резервный локальный доступ

Локальный сервер можно оставить как запасной, но он не должен быть второй "боевой" копией с отдельным планировщиком и отдельной папкой `uploads`. Боевой основной контур для PWA должен быть один: `https://altair-school.ru`.

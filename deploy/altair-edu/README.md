# Продакшн-схема для `altair-edu.ru`

Эта схема рассчитана на текущий контур:

- домен `altair-edu.ru` смотрит на внешний `VPS`
- на `VPS` работает только `nginx` и `WireGuard`
- приложение, `Gunicorn`, база и файлы остаются на школьном сервере
- внешний сервер только принимает `HTTPS` и проксирует трафик в школу через туннель

## Поток запросов

```text
Браузер / телефон
  -> https://altair-edu.ru
  -> внешний VPS (nginx)
  -> WireGuard
  -> школьный сервер (nginx -> gunicorn -> Flask)
  -> локальная база и файлы в школе
```

## Что хранится в школе

- `PostgreSQL`
- `uploads`
- `.env`
- `Firebase service account`
- само приложение и `gunicorn`

Внешний `VPS` не должен хранить базу или пользовательские файлы как постоянное хранилище.

## Что должно быть на VPS

1. `nginx`
2. `certbot`
3. `wireguard`
4. конфиг из `nginx/altair-edu.ru.conf`

## Что должно быть на школьном сервере

1. приложение в `~/school-tracker-pwa`
2. `gunicorn` на `127.0.0.1:8000`
3. локальный `nginx`, который обслуживает приложение на `10.99.0.2:80`
4. `APP_BASE_URL=https://altair-edu.ru`
5. `SESSION_COOKIE_SECURE=1`

## Базовые шаги переноса на новый домен

### 1. DNS

- `A` запись `altair-edu.ru` -> публичный IP `VPS`
- `A` запись `www.altair-edu.ru` -> тот же IP

### 2. Конфиг на VPS

```bash
sudo cp deploy/altair-edu/nginx/altair-edu.ru.conf /etc/nginx/sites-available/altair-edu.ru
sudo ln -sfn /etc/nginx/sites-available/altair-edu.ru /etc/nginx/sites-enabled/altair-edu.ru
sudo rm -f /etc/nginx/sites-enabled/altair-school.ru
sudo nginx -t
sudo systemctl reload nginx
```

### 3. Сертификат на VPS

```bash
sudo certbot certonly --nginx \
  --cert-name altair-edu.ru \
  -d altair-edu.ru -d www.altair-edu.ru \
  --key-type rsa \
  --rsa-key-size 2048
sudo nginx -t
sudo systemctl reload nginx
```

### 4. `.env` на школьном сервере

```bash
cd ~/school-tracker-pwa
sed -i 's#^APP_BASE_URL=.*#APP_BASE_URL=https://altair-edu.ru#' .env
grep '^APP_BASE_URL=' .env
sudo systemctl restart school-tracker-pwa
```

## Проверки

На `VPS`:

```bash
curl -I http://altair-edu.ru
curl -I https://altair-edu.ru
curl -I https://www.altair-edu.ru
```

Нормально, если:

- `http://altair-edu.ru` -> `301` на `https`
- `https://www.altair-edu.ru` -> `301` на `https://altair-edu.ru`
- `https://altair-edu.ru` -> `302` на `/login` или `200`

## Дальнейшее масштабирование

Эта схема не мешает росту на несколько школ:

- `1324.altair-edu.ru`
- `547.altair-edu.ru`

Для каждой школы лучше держать:

- отдельный локальный сервер
- отдельный туннель `WireGuard`
- отдельное правило маршрутизации на внешнем `VPS`

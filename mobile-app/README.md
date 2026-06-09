# Мобильное приложение

Flutter-приложение для Android и iPhone поверх существующего API портала.

## Что уже подключено

- вход через `/mobile/api/auth/login`;
- профиль через `/mobile/api/me`;
- уведомления через `/mobile/api/notifications`;
- мои инциденты через `/mobile/api/incidents/mine`;
- создание инцидента через `/mobile/api/incidents`;
- выбор класса и учеников через `/mobile/api/classes`.

## Первый запуск

На обычном терминале Mac, где Flutter может обновлять свой кэш:

```bash
cd "/Users/aleksandr/Documents/Школьный портал/school-tracker/mobile-app"
flutter create --platforms=android,ios --org ru.school1324 .
flutter pub get
flutter run
```

По умолчанию приложение подключается к серверу:

```text
http://10.172.85.55/mobile/api
```

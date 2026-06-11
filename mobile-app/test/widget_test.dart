import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:school_support_mobile/main.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

class FakePortalApi extends PortalApi {
  FakePortalApi() : super('http://example.test/mobile/api');

  @override
  Future<Map<String, dynamic>> login(String username, String password) async =>
      {
        'username': username,
        'fio': 'Тестовый пользователь',
        'role': 'Сотрудник',
        'permissions': <String, dynamic>{},
      };

  @override
  Future<Map<String, dynamic>> notifications() async => {
    'ok': true,
    'unread': 0,
    'items': <dynamic>[],
  };

  @override
  Future<Map<String, dynamic>> incidentMeta() async => {
    'ok': true,
    'categories': ['Нарушение дисциплины'],
  };

  @override
  Future<List<dynamic>> classes({int? grade}) async => [
    {'id': 1, 'name': '5А', 'grade': 5},
  ];

  @override
  Future<Map<String, dynamic>> taskMeta() async => {
    'ok': true,
    'can_create': true,
    'priorities': ['обычный'],
    'task_types': [
      {'id': 1, 'name': 'поручение'},
    ],
    'users': [
      {'id': 1, 'fio': 'Ответственный сотрудник'},
    ],
  };
}

void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  testWidgets('shows the employee login screen', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          api: FakePortalApi(),
          apiBaseUrl: 'http://example.test/mobile/api',
          onServerChanged: (_) async {},
          onLogin: (_) async {},
        ),
      ),
    );
    await tester.pump();

    expect(find.text('АЛЬТАИР'), findsOneWidget);
    expect(find.text('Логин'), findsOneWidget);
    expect(find.text('Пароль'), findsOneWidget);
    expect(find.text('Войти'), findsOneWidget);
  });

  test('shows a useful local network error', () {
    final message = describePortalError(
      const SocketException('Operation not permitted'),
    );

    expect(message, contains('сервер портала'));
    expect(message, contains('локальной сети'));
    expect(message, contains('Operation not permitted'));
  });

  testWidgets('new incident form has a Material screen', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: NewIncidentScreen(api: FakePortalApi())),
    );
    await tester.pumpAndSettle();

    expect(find.text('Новый инцидент'), findsOneWidget);
    expect(find.text('Категория'), findsOneWidget);
    expect(find.text('Класс'), findsOneWidget);
    expect(find.text('Отправить'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('successful login replaces the login screen cleanly', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: AppRoot(
          api: FakePortalApi(),
          apiBaseUrl: 'http://example.test/mobile/api',
          onServerChanged: (_) async {},
        ),
      ),
    );

    await tester.pump();
    await tester.pump();
    await tester.enterText(find.byType(TextField).first, 'admin');
    await tester.enterText(find.byType(TextField).last, 'password');
    await tester.tap(find.text('Войти'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Быстрый вход'), findsOneWidget);
    expect(find.text('Защитите вход в приложение'), findsOneWidget);
    expect(find.text('Войти'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('new task uses the task form', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: NewTaskScreen(api: FakePortalApi())),
    );
    await tester.pumpAndSettle();

    expect(find.text('Новая задача'), findsOneWidget);
    expect(find.text('Название задачи'), findsOneWidget);
    expect(find.text('Ответственный'), findsOneWidget);
    expect(find.text('Создать задачу', skipOffstage: false), findsOneWidget);
    expect(find.text('Новый инцидент'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}

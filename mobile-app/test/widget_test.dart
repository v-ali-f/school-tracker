import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:school_support_mobile/main.dart';

class FakePortalApi extends PortalApi {
  FakePortalApi() : super('http://example.test/mobile/api');

  @override
  Future<Map<String, dynamic>> incidentMeta() async => {
    'ok': true,
    'categories': ['Нарушение дисциплины'],
  };

  @override
  Future<List<dynamic>> classes({int? grade}) async => [
    {'id': 1, 'name': '5А', 'grade': 5},
  ];
}

void main() {
  testWidgets('shows the employee login screen', (tester) async {
    await tester.pumpWidget(const SchoolSupportApp());

    expect(find.text('Система сопровождения'), findsOneWidget);
    expect(find.text('Логин'), findsOneWidget);
    expect(find.text('Пароль'), findsOneWidget);
    expect(find.text('Войти'), findsOneWidget);
  });

  test('shows a useful local network error', () {
    final message = describePortalError(
      const SocketException('Operation not permitted'),
    );

    expect(message, contains('http://10.172.85.55/mobile/api'));
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
}

import 'package:flutter_test/flutter_test.dart';
import 'package:school_support_mobile/main.dart';

void main() {
  testWidgets('shows the employee login screen', (tester) async {
    await tester.pumpWidget(const SchoolSupportApp());

    expect(find.text('Система сопровождения'), findsOneWidget);
    expect(find.text('Логин'), findsOneWidget);
    expect(find.text('Пароль'), findsOneWidget);
    expect(find.text('Войти'), findsOneWidget);
  });
}

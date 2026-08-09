// Smoke test for the KinJo mobile client.
//
// This replaces the `flutter create` counter template, which was left in place
// untouched: it imported `package:mobile/main.dart` (the package is
// `kinjo_mobile`) and instantiated `MyApp` (the app class is `KinJoApp`), so it
// failed to compile and `flutter test` could not run at all. It also asserted
// on a counter widget that has never existed in this app.

import 'package:flutter_test/flutter_test.dart';

import 'package:kinjo_mobile/main.dart';

void main() {
  testWidgets('unauthenticated launch shows the login screen',
      (WidgetTester tester) async {
    // No stored user, so the app should route to the login screen rather than
    // any role shell.
    await tester.pumpWidget(const KinJoApp(initialUser: null));
    await tester.pump();

    expect(find.byType(MobileLoginScreen), findsOneWidget);
    expect(find.text('تسجيل الدخول'), findsWidgets);
  });
}

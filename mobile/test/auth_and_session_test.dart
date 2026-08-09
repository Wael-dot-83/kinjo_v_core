import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kinjo_mobile/core/api/api_service.dart';
import 'package:kinjo_mobile/main.dart';
import 'package:kinjo_mobile/models/user_model.dart';

void main() {
  group('Authentication & Session Security Tests', () {
    test('ApiException correctly identifies rate limiting (429)', () {
      final exc = ApiException(
        statusCode: 429,
        message: 'لقد تجاوزت عدد المحاولات المسموح بها.',
      );
      expect(exc.isRateLimited, isTrue);
      expect(exc.isUnauthorized, isFalse);
      expect(exc.statusCode, 429);
    });

    test('ApiException correctly identifies unauthorized credentials (401)', () {
      final exc = ApiException(
        statusCode: 401,
        message: 'اسم المستخدم أو كلمة المرور غير صحيحة.',
      );
      expect(exc.isUnauthorized, isTrue);
      expect(exc.isRateLimited, isFalse);
    });

    test('ApiException correctly identifies forbidden actions (403)', () {
      final exc = ApiException(
        statusCode: 403,
        message: 'غير مصرح لك بإجراء هذه العملية.',
      );
      expect(exc.isForbidden, isTrue);
    });

    test('UserRole parsing correctly maps role strings and enums', () {
      expect(UserRoleExtension.fromString('PARENT'), UserRole.parent);
      expect(UserRoleExtension.fromString('SUPERVISOR'), UserRole.supervisor);
      expect(UserRoleExtension.fromString('MANAGER'), UserRole.manager);
      expect(UserRoleExtension.fromString('ADMIN'), UserRole.admin);
      expect(UserRoleExtension.fromString('UNKNOWN'), UserRole.unknown);

      expect(UserRole.parent.value, 'PARENT');
      expect(UserRole.supervisor.value, 'SUPERVISOR');
      expect(UserRole.manager.value, 'MANAGER');
      expect(UserRole.admin.value, 'ADMIN');
    });

    testWidgets('ADMIN user login attempt renders clear unsupported-mobile guidance screen',
        (WidgetTester tester) async {
      final adminUser = UserModel(
        id: 999,
        username: 'admin_test',
        email: 'admin@kinjo.jo',
        role: UserRole.admin,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: RoleShellScreen(user: adminUser),
        ),
      );
      await tester.pump();

      expect(find.text('غير مصرح'), findsOneWidget);
      expect(find.text('دور الحساب غير مدعوم على تطبيق الهاتف.'), findsOneWidget);
      expect(find.text('حسابات المسؤولين (ADMIN) مخصصة فقط للوحة التحكم عبر الويب.'), findsOneWidget);
      expect(find.text('تسجيل الخروج'), findsOneWidget);
    });
  });
}

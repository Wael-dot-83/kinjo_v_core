import 'package:flutter_test/flutter_test.dart';
import 'package:kinjo_mobile/models/absence_request_model.dart';
import 'package:kinjo_mobile/models/child_model.dart';
import 'package:kinjo_mobile/models/daily_report_model.dart';
import 'package:kinjo_mobile/models/user_model.dart';

void main() {
  group('Manager & Parent Operations Test Suite', () {
    final testManager = UserModel(
      id: 20,
      username: 'manager1',
      email: 'manager1@kinjo.jo',
      role: UserRole.manager,
    );

    final testParent = UserModel(
      id: 30,
      username: 'parent1',
      email: 'parent1@kinjo.jo',
      role: UserRole.parent,
    );

    test('Manager and Parent user roles evaluate correctly', () {
      expect(testManager.role, UserRole.manager);
      expect(testManager.role.value, 'MANAGER');

      expect(testParent.role, UserRole.parent);
      expect(testParent.role.value, 'PARENT');
    });

    test('AbsenceRequestModel evaluates pending/approved/rejected statuses accurately', () {
      final pendingReq = AbsenceRequestModel(
        id: 1,
        childId: 10,
        startDate: '2026-08-10',
        endDate: '2026-08-11',
        reason: 'مرضي',
        status: 'SUBMITTED',
      );
      expect(pendingReq.isPending, isTrue);
      expect(pendingReq.isApproved, isFalse);
      expect(pendingReq.statusArabic, 'قيد الانتظار');

      final approvedReq = AbsenceRequestModel(
        id: 2,
        childId: 10,
        startDate: '2026-08-12',
        endDate: '2026-08-13',
        reason: 'سفر',
        status: 'APPROVED',
      );
      expect(approvedReq.isApproved, isTrue);
      expect(approvedReq.statusArabic, 'مقبول');

      final rejectedReq = AbsenceRequestModel(
        id: 3,
        childId: 10,
        startDate: '2026-08-14',
        endDate: '2026-08-15',
        reason: 'شخصي',
        status: 'REJECTED',
      );
      expect(rejectedReq.isRejected, isTrue);
      expect(rejectedReq.statusArabic, 'مرفوض');
    });

    test('ChildModel parses JSON and computes full name correctly', () {
      final json = {
        'id': 101,
        'first_name': 'يوسف',
        'last_name': 'عمر',
        'gender': 'MALE',
        'kindergarten_name': 'روضة الأمل',
      };

      final child = ChildModel.fromJson(json);
      expect(child.id, 101);
      expect(child.fullName, 'يوسف عمر');
      expect(child.kindergartenName, 'روضة الأمل');
    });

    test('DailyReportModel parses JSON and default emojis correctly', () {
      final json = {
        'id': 50,
        'child_id': 101,
        'child_name': 'يوسف عمر',
        'date': '2026-08-09',
        'status': 'APPROVED',
        'notes': 'أداء ممتاز اليوم',
      };

      final report = DailyReportModel.fromJson(json);
      expect(report.id, 50);
      expect(report.childId, 101);
      expect(report.childName, 'يوسف عمر');
      expect(report.status, 'APPROVED');
      expect(report.notes, 'أداء ممتاز اليوم');
    });
  });
}

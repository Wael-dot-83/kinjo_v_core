import 'package:flutter_test/flutter_test.dart';
import 'package:kinjo_mobile/models/roster_model.dart';
import 'package:kinjo_mobile/models/user_model.dart';

void main() {
  group('Supervisor Daily Report Roster Test Suite', () {
    final testSupervisor = UserModel(
      id: 10,
      username: 'supervisor1',
      email: 'supervisor1@kinjo.jo',
      role: UserRole.supervisor,
    );

    test('UserModel identifies supervisor role correctly', () {
      expect(testSupervisor.role, UserRole.supervisor);
      expect(testSupervisor.role.value, 'SUPERVISOR');
    });

    test('RosterEntryModel handles skip toggle and per-child overrides', () {
      final entry = RosterEntryModel(
        childId: 5,
        childName: 'عمر علي',
        mood: 'happy',
        notes: 'ملاحظة خاصة',
      );

      expect(entry.skip, isFalse);
      entry.skip = true;
      expect(entry.skip, isTrue);

      final json = entry.toJson();
      expect(json['skip'], isTrue);
      expect(json['mood'], 'happy');
      expect(json['notes'], 'ملاحظة خاصة');
    });

    test('RosterBatchResponseModel correctly calculates created, skipped, failed counts', () {
      final json = {
        'date': '2026-08-09',
        'created': 2,
        'skipped': 1,
        'failed': 1,
        'results': [
          {'child_id': 1, 'status': 'created', 'report_id': 101},
          {'child_id': 2, 'status': 'created', 'report_id': 102},
          {'child_id': 3, 'status': 'skipped', 'detail': 'Skipped by supervisor'},
          {'child_id': 4, 'status': 'failed', 'code': 409, 'detail': 'Report already exists'},
        ]
      };

      final response = RosterBatchResponseModel.fromJson(json);
      expect(response.created, 2);
      expect(response.skipped, 1);
      expect(response.failed, 1);
      expect(response.results.length, 4);
      expect(response.results[3].code, 409);
    });
  });
}

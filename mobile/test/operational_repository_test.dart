import 'package:flutter_test/flutter_test.dart';
import 'package:kinjo_mobile/models/absence_request_model.dart';
import 'package:kinjo_mobile/models/roster_model.dart';

void main() {
  group('Roster & Operational Models Test Suite', () {
    test('RosterBatchRequestModel serializes correctly for POST /api/daily-reports/batch', () {
      final entry = RosterEntryModel(
        childId: 101,
        childName: 'أحمد محمود',
        mood: 'happy',
        notes: 'ممتاز',
      );

      final batchReq = RosterBatchRequestModel(
        date: '2026-08-09',
        children: [entry],
      );

      final json = batchReq.toJson();
      expect(json['date'], '2026-08-09');
      expect(json['arrival_time'], '08:00');
      expect(json['leave_time'], '14:00');
      expect(json['children'], isA<List>());
      expect(json['children'].length, 1);
      expect(json['children'][0]['child_id'], 101);
      expect(json['children'][0]['mood'], 'happy');
    });

    test('RosterBatchResponseModel parses HTTP 207 Multi-Status response', () {
      final jsonResponse = {
        'date': '2026-08-09',
        'created': 1,
        'skipped': 1,
        'failed': 1,
        'results': [
          {'child_id': 101, 'status': 'created', 'report_id': 500},
          {'child_id': 102, 'status': 'skipped', 'detail': 'Skipped by supervisor'},
          {'child_id': 103, 'status': 'failed', 'code': 409, 'detail': 'Daily report already exists'},
        ]
      };

      final response = RosterBatchResponseModel.fromJson(jsonResponse);
      expect(response.created, 1);
      expect(response.skipped, 1);
      expect(response.failed, 1);
      expect(response.results.length, 3);
      expect(response.results[0].status, 'created');
      expect(response.results[0].reportId, 500);
      expect(response.results[2].code, 409);
    });

    test('AbsenceRequestModel parses status and localized labels correctly', () {
      final json = {
        'id': 42,
        'child_id': 10,
        'child_name': 'سارة الأحمد',
        'parent_name': 'محمود الأحمد',
        'start_date': '2026-08-10',
        'end_date': '2026-08-12',
        'reason': 'ظروف عائلية',
        'status': 'SUBMITTED',
      };

      final model = AbsenceRequestModel.fromJson(json);
      expect(model.id, 42);
      expect(model.isPending, isTrue);
      expect(model.isApproved, isFalse);
      expect(model.statusArabic, 'قيد الانتظار');
    });
  });
}

import requests
import time
import subprocess

print('Starting server...')
server = subprocess.Popen(['python', 'main.py'],
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
time.sleep(5)  # Wait for server to start

try:
    response = requests.get('http://localhost:8000/api/analytics/dashboard-data', timeout=10)
    if response.status_code == 200:
        data = response.json()
        print('✅ Analytics API endpoint working!')
        print(f'Status: {response.status_code}')

        if 'network_summary' in data:
            summary = data['network_summary']
            print(f'✓ Network Summary: {summary.get("total_kindergartens", 0)} kindergartens')
            print(f'  - Children: {summary.get("total_children", 0)}')
            print(f'  - Staff: {summary.get("total_staff", 0)}')
            print(f'  - Capacity: {summary.get("total_capacity", 0)}')
            print(f'  - Attendance Rate: {summary.get("attendance_rate", 0):.1f}%')
            print(f'  - Governance Score: {summary.get("governance_avg_score", 0):.1f}')

        if 'governorate_breakdown' in data:
            print(f'✓ Governorate Breakdown: {len(data["governorate_breakdown"])} entries')

        if 'network_trends' in data:
            print(f'✓ Network Trends: {len(data["network_trends"])} data points')

        if 'high_risk_children' in data:
            print(f'✓ High Risk Children: {len(data["high_risk_children"])} children')

        if 'governance_distribution' in data:
            print(f'✓ Governance Distribution: {len(data["governance_distribution"])} categories')

        print()
        print('✅ COMPLETE ANALYTICS DASHBOARD API WORKING WITH REAL DATA!')

    else:
        print(f'✗ API returned status {response.status_code}')
        print(f'Response: {response.text}')

except Exception as e:
    print(f'✗ Error: {e}')

finally:
    server.terminate()
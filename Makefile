.PHONY: lint lint-py-strict fmt lint-js fmt-js test test-p0 test-full check ci-local clean

lint:
	ruff check .

lint-py-strict:
	ruff check data_quality_service.py predictive_analytics.py email_service.py api/auth/password_reset_service.py api/analytics/scope_domain.py api/attendance/summary_domain.py --select F401,F841,I001

lint-js:
	npm run lint:js

fmt:
	ruff format .
	ruff check --fix .

fmt-js:
	npm run format:js

test-p0:
	pytest -m "p0" --timeout=30 -q

test-full:
	pytest tests/ --timeout=30 -q

test: test-p0

check: lint lint-py-strict lint-js test-p0

ci-local: lint lint-py-strict lint-js test-full

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov coverage.xml

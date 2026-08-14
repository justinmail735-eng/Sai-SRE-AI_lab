.PHONY: check test observability-generate demo-up demo-verify demo-traffic demo-fault-errors demo-fault-latency demo-recover demo-down

check:
	python3 scripts/reliability_check.py

test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

observability-generate:
	python3 agents/observability_agent.py --spec reliability/services/checkout-api.json --output-dir observability/generated/checkout-api

demo-up:
	docker compose -f observability/local/docker-compose.yml up --build -d

demo-verify:
	python3 scripts/live_stack_check.py

demo-traffic:
	python3 scripts/load_generator.py --duration 60

demo-fault-errors:
	curl -fsS -X POST 'http://localhost:8080/admin/fault?mode=errors'

demo-fault-latency:
	curl -fsS -X POST 'http://localhost:8080/admin/fault?mode=latency'

demo-recover:
	curl -fsS -X POST 'http://localhost:8080/admin/fault?mode=none'

demo-down:
	docker compose -f observability/local/docker-compose.yml down --volumes --remove-orphans

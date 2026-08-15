.PHONY: check test observability-generate agent-governance agent-investigate chaos-plan chaos-k8s evidence-check terraform-fmt terraform-validate terraform-test gitops-validate security-check k8s-validate k8s-up k8s-verify k8s-down demo-up demo-verify demo-traffic demo-fault-errors demo-fault-latency demo-recover demo-down

check:
	python3 scripts/reliability_check.py

test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

observability-generate:
	python3 agents/observability_agent.py --spec reliability/services/checkout-api.json --output-dir observability/generated/checkout-api

agent-governance:
	python3 scripts/governance_check.py

agent-investigate:
	mkdir -p build/agent-demo
	python3 agents/incident_investigator.py --base-url http://127.0.0.1:8080 --incident-id INC-LIVE-DEMO --output build/agent-demo/investigation.json

chaos-plan:
	python3 scripts/k8s_chaos_check.py

chaos-k8s:
	python3 scripts/k8s_chaos_check.py --execute --acknowledge DELETE-ONE-LOCAL-CHECKOUT-POD --output build/chaos/k8s-result.json

evidence-check:
	python3 scripts/evidence_check.py

terraform-fmt:
	terraform fmt -recursive infrastructure

terraform-validate:
	python3 scripts/terraform_validate.py --skip-tests

terraform-test:
	python3 scripts/terraform_validate.py

gitops-validate:
	python3 scripts/gitops_validate.py

security-check: gitops-validate
	mkdir -p build/security
	syft dir:. --source-name sentinelsre --source-version dev -o cyclonedx-json=build/security/sentinelsre-sbom.cdx.json
	trivy fs --scanners vuln,misconfig,secret --severity HIGH,CRITICAL --exit-code 1 --skip-dirs .git --skip-dirs build .

k8s-validate:
	helm lint platform/helm/checkout-api
	python3 scripts/k8s_validate.py

k8s-up:
	kind create cluster --config platform/kind/cluster.yaml
	kind load docker-image local-checkout-api:latest --name sentinelsre
	kubectl create namespace sentinelsre --dry-run=client -o yaml | kubectl apply -f -
	helm upgrade --install checkout platform/helm/checkout-api --namespace sentinelsre --values platform/helm/checkout-api/values-kind.yaml --wait --timeout 3m

k8s-verify:
	kubectl rollout status deployment/checkout-checkout-api -n sentinelsre --timeout=2m
	python3 scripts/k8s_runtime_check.py

k8s-down:
	kind delete cluster --name sentinelsre

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

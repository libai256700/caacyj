.PHONY: domain-sync-gate domain-sync-gate-fast business-graph-gate business-graph-governance-check

PYTHON ?= python3
DENSE_MODE ?= full
DOMAINS ?=
DOMAIN_FLAGS = $(foreach domain,$(DOMAINS),--domain $(domain))

domain-sync-gate:
	$(PYTHON) scripts/run_domain_sync_gate.py --dense-mode $(DENSE_MODE) $(DOMAIN_FLAGS)

domain-sync-gate-fast:
	$(PYTHON) scripts/run_domain_sync_gate.py --dense-mode sample $(DOMAIN_FLAGS)

business-graph-gate:
	bash scripts/run_business_graph_sync_gate.sh

business-graph-governance-check:
	$(PYTHON) scripts/eval_multihop_business_graph.py
	$(PYTHON) scripts/govern_multihop_bridges.py
	$(PYTHON) scripts/govern_type_conflicts.py
	$(PYTHON) scripts/govern_job_company_duplicates.py
	$(PYTHON) scripts/check_business_graph_governance.py

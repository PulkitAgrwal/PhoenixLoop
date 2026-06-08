.PHONY: help dev test lint clean seed deploy demo

BACKEND_VENV := backend/.venv/bin
BACKEND_PYTHON := $(BACKEND_VENV)/python
API_URL ?= http://localhost:8000

help:
	@echo "PhoenixLoop — Make targets"
	@echo "  make dev     Build and start the backend + frontend via docker compose"
	@echo "  make test    Run backend pytest + frontend lint + frontend tsc"
	@echo "  make lint    Run ruff on backend + ESLint on frontend"
	@echo "  make clean   docker compose down -v (wipes the DB volume)"
	@echo "  make seed    POST /api/demo/seed against $$API_URL (default $(API_URL))"
	@echo "  make deploy  Deploy both Cloud Run services (PROJECT_ID, REGION env vars)"
	@echo "  make demo    docker compose up + seed + open localhost:3000"

dev:
	docker compose up --build

test:
	@echo "--- backend pytest ---"
	cd backend && PYTHONPATH=. GOOGLE_API_KEY=$${GOOGLE_API_KEY:-test} PHOENIX_API_KEY=$${PHOENIX_API_KEY:-test} $(BACKEND_PYTHON) -m pytest tests/ -x --tb=short
	@echo "--- frontend lint ---"
	cd frontend && npm run lint
	@echo "--- frontend tsc ---"
	cd frontend && npx tsc --noEmit

lint:
	@echo "--- backend ruff ---"
	cd backend && $(BACKEND_VENV)/ruff check src/ --select E,F,I --ignore E501
	@echo "--- frontend lint ---"
	cd frontend && npm run lint

clean:
	docker compose down -v

seed:
	@echo "POST $(API_URL)/api/demo/seed"
	@curl -fsS -X POST -H "Idempotency-Key: make-seed" $(API_URL)/api/demo/seed | head -c 4096
	@echo

deploy:
	@./deploy_cloud_run.sh $(PROJECT_ID) $(REGION)

demo:
	@docker compose up -d
	@echo "Waiting for backend to become healthy..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -fsS $(API_URL)/api/health > /dev/null 2>&1; then \
			echo "Backend healthy"; break; \
		fi; \
		sleep 2; \
	done
	@curl -fsS -X POST -H "Idempotency-Key: make-demo" $(API_URL)/api/demo/seed | head -c 200
	@echo
	@command -v open >/dev/null && open http://localhost:3000 || xdg-open http://localhost:3000 || echo "Open http://localhost:3000 manually"

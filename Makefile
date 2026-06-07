.PHONY: help dev test lint clean seed

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

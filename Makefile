.PHONY: dev prod migrate worker logs shell clean test

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

prod:
	docker compose up -d --build

migrate:
	docker compose exec backend alembic upgrade head

worker:
	docker compose up --build --scale worker=4 worker

logs:
	docker compose logs -f backend worker

shell:
	docker compose exec backend bash

clean:
	docker compose down -v
	rm -rf data/rrd/* data/thumb/*

test:
	docker compose exec backend pytest -v

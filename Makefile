.PHONY: install run lint format build package-install

install:
	uv sync

run:
	uv run project

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

build:
	uv build

package-install: build
	uv pip install --reinstall --no-deps --no-index --find-links dist finalproject-Kositskaya-M26-555

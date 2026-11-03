.PHONY: bootstrap lint test ios-test pipeline tf-fmt

bootstrap:
	uv sync --all-packages
	uv run pre-commit install || true

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	terraform fmt -check -recursive infra

test:
	uv run pytest

ios-test:
	xcodebuild -project ios/ThinkBible.xcodeproj -scheme ThinkBible \
	  -destination 'platform=iOS Simulator,name=iPhone 16' test

BOOK ?= mark
STAGE ?= all
ENV ?= dev
pipeline:
	uv run --package thinkbible-pipeline python -m thinkbible_pipeline.cli --book $(BOOK) --stage $(STAGE) --env $(ENV)

tf-fmt:
	terraform fmt -recursive infra

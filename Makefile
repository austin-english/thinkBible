.PHONY: bootstrap lint test ios-test pipeline publish sources-pull tf-fmt

PIPELINE = uv run --package thinkbible-pipeline thinkbible-pipeline

bootstrap:
	uv sync --all-packages
	uv run pre-commit install || true

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	@if find infra -name '*.tf' 2>/dev/null | grep -q .; then \
	  terraform fmt -check -recursive infra; \
	else echo "terraform fmt: no .tf files yet, skipping"; fi

test:
	uv run pytest

ios-test:
	xcodebuild -project ios/ThinkBible.xcodeproj -scheme ThinkBible \
	  -destination 'platform=iOS Simulator,name=iPhone 16' test

BOOK ?= mark
STAGE ?= all
ENV ?= dev

# Run pipeline stages locally (see specs/001-content-pack-pipeline/contracts/cli.md).
pipeline:
	$(PIPELINE) run --book $(BOOK) --stage $(STAGE)

# Publish an approved book to an environment (dev or prod).
publish:
	$(PIPELINE) publish --book $(BOOK) --env $(ENV)

# Download the frozen source snapshot from S3 into content/sources/ and verify it.
sources-pull:
	$(PIPELINE) sources pull

tf-fmt:
	terraform fmt -recursive infra

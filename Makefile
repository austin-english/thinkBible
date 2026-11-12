.PHONY: bootstrap lint test ios-test pipeline publish promote status lambda-bundle sources-pull tf-fmt

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

# Run pipeline stages in AWS and wait for them (specs/001-content-pack-pipeline/contracts/cli.md).
# For a few sections in-process: $(PIPELINE) run --book mark --stage generate --local --sections ...
pipeline:
	$(PIPELINE) run --book $(BOOK) --stage $(STAGE) --env $(ENV) --wait

# Book status, latest runs and spend; opens the scorecard (review.html).
status:
	$(PIPELINE) status --book $(BOOK) --env $(ENV) --open

# Publish the book's drafts to dev (a passing run that includes `report` does this itself).
publish:
	$(PIPELINE) publish --book $(BOOK)

# Copy the book's current dev version to production (gated: scorecard, calibration, publish check).
promote:
	$(PIPELINE) promote --book $(BOOK)

# Build the pipeline Lambda bundle (pipeline/out/lambda.zip), then `terraform apply` in infra/envs/$(ENV).
lambda-bundle:
	uv run python pipeline/scripts/build_bundle.py

# Download the frozen source snapshot from S3 into content/sources/ and verify it.
sources-pull:
	$(PIPELINE) sources pull

tf-fmt:
	terraform fmt -recursive infra

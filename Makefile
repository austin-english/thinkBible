.PHONY: bootstrap lint test ios-test pipeline publish promote status lambda-bundle deploy sources-publish sources-pull tf-fmt

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

# Run pipeline stages in AWS and wait for them (specs/001-content-pack-pipeline/contracts/cli.md).
# For a few sections in-process: $(PIPELINE) run --book mark --stage generate --local --sections ...
pipeline:
	$(PIPELINE) run --book $(BOOK) --stage $(STAGE) --wait

# Book status, latest runs and spend; opens the scorecard (review.html).
status:
	$(PIPELINE) status --book $(BOOK) --open

# Publish the book's drafts to the draft channel (a passing run with `report` does this itself).
publish:
	$(PIPELINE) publish --book $(BOOK)

# Copy the book's current draft version to the live channel (gated: scorecard, calibration, check).
promote:
	$(PIPELINE) promote --book $(BOOK)

# Build the pipeline Lambda bundle (pipeline/out/lambda.zip), then `terraform apply` in infra/.
lambda-bundle:
	uv run python pipeline/scripts/build_bundle.py

# Build the bundle and apply the Terraform in infra/ (after code, config or prompt changes).
deploy: lambda-bundle
	terraform -chdir=infra apply

# Upload the frozen source snapshot after an import, then prove S3 holds exactly that snapshot.
# Stops at the first failing step. Never touches the local cache.
sources-publish:
	$(PIPELINE) sources check
	$(PIPELINE) verify
	$(PIPELINE) sources push
	$(PIPELINE) verify --remote

# Download the frozen source snapshot from S3 into content/sources/ and verify it.
sources-pull:
	$(PIPELINE) sources pull

tf-fmt:
	terraform fmt -recursive infra

#!/usr/bin/env bash
# Build the Lambda package for the ask service (ADR 0003). Does not deploy.
#
# Produces dist/ask-lambda.zip containing:
#   homeroom/          the package (src/homeroom)
#   corpus/            the committed CDE definitions (hash-checked at load)
#   bundle/            the evidence bundle (index.json + schools/*.json), built
#                      from the acquired files by `homeroom.ask.evidence`
#   site-packages      the `anthropic` SDK and its dependencies for arm64
#
# Requires: uv, zip, and data/out/ask built from the acquired files
# (`make data` then the evidence command in deploy/ask/README.md). The zip is
# ~9 MB compressed (the bundle is 206 MB on disk and compresses to ~8 MB);
# Lambda's limit is 250 MB unzipped, which the bundle's 206 MB plus the SDK
# fits under, but not by much: if a fourth data source lands, move the bundle
# to S3 and read one school per request instead of packaging it.
set -euo pipefail
cd "$(dirname "$0")/../.."

BUNDLE="${HOMEROOM_ASK_BUNDLE:-data/out/ask}"
test -f "$BUNDLE/index.json" || { echo "no bundle at $BUNDLE/index.json" >&2; exit 1; }
python3 - "$BUNDLE" <<'PY'
import json, sys
index = json.load(open(f"{sys.argv[1]}/index.json"))
if index.get("is_fixture"):
    sys.exit("refusing to package a fixture bundle: that is not real data")
print(f"bundle: {index['schools']} schools, fixture={index['is_fixture']}")
PY

rm -rf dist/ask-build dist/ask-lambda.zip
mkdir -p dist/ask-build
uv pip install --python 3.12 --target dist/ask-build \
  --python-platform aarch64-manylinux2014 --only-binary :all: \
  "anthropic>=1.0,<2" >/dev/null
cp -R src/homeroom dist/ask-build/homeroom
cp -R corpus dist/ask-build/corpus
mkdir -p dist/ask-build/bundle
cp "$BUNDLE/index.json" dist/ask-build/bundle/
cp -R "$BUNDLE/schools" dist/ask-build/bundle/schools
find dist/ask-build -name "__pycache__" -type d -prune -exec rm -rf {} +
( cd dist/ask-build && zip -qr ../ask-lambda.zip . )
du -sh dist/ask-build dist/ask-lambda.zip
echo "built dist/ask-lambda.zip; nothing deployed"

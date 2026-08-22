#!/usr/bin/env bash
# Build the Lambda package for the ask service (ADR 0003). Does not deploy.
#
# Produces dist/ask-lambda.zip containing:
#   homeroom/          the package (src/homeroom)
#   corpus/            the committed CDE definitions (hash-checked at load)
#   bundle/            the evidence bundle (index.json + schools/*.json), built
#                      from the acquired files by `homeroom.ask.evidence`
#   site-packages      the `anthropic` SDK with its `bedrock` extra (boto3 and
#                      botocore, which AnthropicBedrock signs requests with) and
#                      the rest of its dependencies, for arm64
#
# Requires: uv, zip, and data/out/ask built from the acquired files
# (`make data` then the evidence command in deploy/ask/README.md). Lambda's
# limit is 250 MB unzipped and this package measures ~240 MB of it, almost all
# of it the evidence bundle. That margin is thin on purpose-free grounds: it is
# what is left, not what was chosen. A fourth data source, or anything that
# grows the bundle, does not fit, and the fix is to move the bundle to S3 and
# read one school per request (a small change to
# `homeroom.ask.evidence.load_school`) rather than to drop schools or trim
# data. The script prints the measured size so the margin is never a guess.
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
# The bedrock extra, not the bare SDK: `anthropic.AnthropicBedrock` signs with
# botocore, and the Lambda runtime's own boto3 is an implicit dependency on a
# version nobody here pinned.
uv pip install --python 3.12 --target dist/ask-build \
  --python-platform aarch64-manylinux2014 --only-binary :all: \
  "anthropic[bedrock]>=1.0,<2" >/dev/null
cp -R src/homeroom dist/ask-build/homeroom
cp -R corpus dist/ask-build/corpus
mkdir -p dist/ask-build/bundle
cp "$BUNDLE/index.json" dist/ask-build/bundle/
cp -R "$BUNDLE/schools" dist/ask-build/bundle/schools
find dist/ask-build -name "__pycache__" -type d -prune -exec rm -rf {} +
( cd dist/ask-build && zip -qr ../ask-lambda.zip . )
# Lambda measures the unzipped package, so measure that, not the directory's
# disk usage: `du` rounds every file up to a block and overstates a tree of
# 10,000 small JSON files by tens of megabytes. Sizing in python keeps this
# script working anywhere that can already run the fixture check above.
python3 - dist/ask-build <<'SIZE'
import pathlib, sys
limit = 250 * 1024 * 1024
root = pathlib.Path(sys.argv[1])
total = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
print(f"unzipped: {total} bytes ({total / 1048576:.1f} MB, "
      f"{100 * total / limit:.1f}% of Lambda's 250 MB limit)")
if total > limit:
    sys.exit("package exceeds Lambda's 250 MB unzipped limit: move the bundle "
             "to S3 and read one school per request; do not drop schools")
SIZE
du -sh dist/ask-lambda.zip
echo "built dist/ask-lambda.zip"

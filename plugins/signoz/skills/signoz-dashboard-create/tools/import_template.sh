#!/usr/bin/env bash
# Fetch a dashboard template JSON from the pinned SigNoz/dashboards commit.
#
# Usage:
#   import_template.sh <path>
#
# where <path> is the template path within the upstream repo
# (e.g. postgresql/postgresql.json). Writes the raw response body to
# stdout. On HTTP/network failure or invalid JSON, writes a short
# message to stderr and exits non-zero.
#
# Requires: bash, curl, jq.

set -euo pipefail

PINNED_SHA="61d374c50f9e1383e0eba3584fb81498f38c1f8d"
BASE_URL="https://raw.githubusercontent.com/SigNoz/dashboards"
FETCH_TIMEOUT_SECONDS=30

if [[ $# -ne 1 || "$1" == "-h" || "$1" == "--help" ]]; then
    echo "Usage: $0 <path>" >&2
    exit 2
fi

PATH_ARG="${1#/}"

# URL-encode path while preserving '/'. Use jq for safe percent-encoding,
# then restore '/' separators.
ENCODED="$(jq -rn --arg s "$PATH_ARG" '$s | @uri' | sed 's|%2F|/|g')"
URL="$BASE_URL/$PINNED_SHA/$ENCODED"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

HTTP_CODE="$(curl -sS -o "$TMP" -w '%{http_code}' --max-time "$FETCH_TIMEOUT_SECONDS" "$URL" || true)"

if [[ -z "$HTTP_CODE" || "$HTTP_CODE" == "000" ]]; then
    echo "Network error fetching $PATH_ARG" >&2
    exit 1
fi

if [[ "$HTTP_CODE" -lt 200 || "$HTTP_CODE" -ge 300 ]]; then
    echo "HTTP $HTTP_CODE fetching $PATH_ARG" >&2
    exit 1
fi

if ! jq empty "$TMP" >/dev/null 2>&1; then
    echo "Fetched body for $PATH_ARG is not valid JSON" >&2
    exit 1
fi

cat "$TMP"
# Ensure trailing newline.
[[ "$(tail -c1 "$TMP" | xxd -p)" == "0a" ]] || echo

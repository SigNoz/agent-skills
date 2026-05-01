#!/usr/bin/env bash
# Search the bundled dashboard template catalog.
#
# Usage:
#   search_templates.sh "<query>" [--limit N] [--category NAME]
#                                 [--list-categories] [--catalog PATH]
#
# Emits a JSON array to stdout. Each entry has: id, title, path,
# description, category, score. Returns an empty array on no match.
#
# Requires: bash, jq.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_CATALOG="$SCRIPT_DIR/../templates.json"

QUERY=""
LIMIT=5
CATEGORY=""
LIST_CATEGORIES=0
CATALOG="$DEFAULT_CATALOG"

usage() {
    sed -n '2,11p' "$0" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --limit) LIMIT="$2"; shift 2 ;;
        --limit=*) LIMIT="${1#*=}"; shift ;;
        --category) CATEGORY="$2"; shift 2 ;;
        --category=*) CATEGORY="${1#*=}"; shift ;;
        --list-categories) LIST_CATEGORIES=1; shift ;;
        --catalog) CATALOG="$2"; shift 2 ;;
        --catalog=*) CATALOG="${1#*=}"; shift ;;
        -h|--help) usage ;;
        --) shift; break ;;
        -*) echo "Unknown option: $1" >&2; usage ;;
        *)
            if [[ -z "$QUERY" ]]; then
                QUERY="$1"
            else
                echo "Unexpected positional arg: $1" >&2; usage
            fi
            shift
            ;;
    esac
done

if [[ ! -f "$CATALOG" ]]; then
    echo "Catalog not found: $CATALOG" >&2
    exit 1
fi

if [[ "$LIST_CATEGORIES" -eq 1 ]]; then
    jq '[.[].category | select(. != null and . != "")] | unique' "$CATALOG"
    exit 0
fi

# Tokenize query: lowercase, replace non-alphanumeric with spaces, split.
QUERY_LOWER="$(printf '%s' "$QUERY" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' ' ')"
read -r -a TOKENS <<< "$QUERY_LOWER"

# Build a JSON array of tokens for jq.
if [[ ${#TOKENS[@]} -eq 0 ]]; then
    TOKENS_JSON='[]'
else
    TOKENS_JSON="$(printf '%s\n' "${TOKENS[@]}" | jq -R . | jq -s .)"
fi

jq \
    --argjson tokens "$TOKENS_JSON" \
    --arg category "$CATEGORY" \
    --argjson limit "$LIMIT" '
    def score(tokens):
        . as $e
        | (($e.keywords // []) | map(ascii_downcase)) as $kw
        | (($e.title // "") | ascii_downcase) as $t
        | (($e.description // "") | ascii_downcase) as $d
        | reduce tokens[] as $tok (0;
            . + (if ($kw | index($tok)) then 10 else 0 end)
              + (if ($t | contains($tok)) then 5 else 0 end)
              + (if ($d | contains($tok)) then 2 else 0 end)
        );

    ([.[]
      | select($category == "" or ((.category // "") | ascii_downcase) == ($category | ascii_downcase))
     ]) as $filtered
    | (if ($tokens | length) > 0 then
           [$filtered[] | {entry: ., score: score($tokens)} | select(.score > 0)]
           | sort_by(-.score, .entry.title)
       elif $category != "" then
           [$filtered[] | {entry: ., score: 0}]
           | sort_by(.entry.title | ascii_downcase)
       else
           []
       end)
    | .[0:$limit]
    | map({
        id: .entry.id,
        title: .entry.title,
        path: .entry.path,
        description: .entry.description,
        category: .entry.category,
        score: .score
    })
' "$CATALOG"

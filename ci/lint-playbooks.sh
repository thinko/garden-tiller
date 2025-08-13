#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Running yamllint..."
find . -type f -name "*.yaml" -o -name "*.yml" \
  | grep -E '(^./playbooks/|roles/)' | sort -u \
  > /tmp/ytargets.txt

if [[ -s /tmp/ytargets.txt ]]; then
  yamllint -c .yamllint -f parsable $(cat /tmp/ytargets.txt) || true
else
  echo "No YAML files found under playbooks/ or roles/"
fi

echo "Running ansible-lint..."
ansible-lint -p --parseable --exclude vendor $(git ls-files '*.yml' '*.yaml' \
  | grep -E '(^playbooks/|^roles/|^tasks/)' || true) \
  > /tmp/ansible-lint.out || true

if [[ -s /tmp/ansible-lint.out ]]; then
  echo "ansible-lint found issues; grouping by file:"
  awk -F: '{print $1}' /tmp/ansible-lint.out | sort | uniq -c | sort -nr
  echo
  echo "Full list of issues:"
  cat /tmp/ansible-lint.out
  # Provide guidance per file
  while read -r file; do
    echo "----"
    echo "File: $file"
    grep -n "^$file:" -n /tmp/ansible-lint.out || true
    echo "Suggested action: open branch fix/lint/$(basename "${file%.*}") and address these issues."
  done < <(awk -F: '{print $1}' /tmp/ansible-lint.out | sort | uniq)
else
  echo "No ansible-lint issues found."
fi

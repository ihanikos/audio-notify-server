#!/bin/bash
# Check for ruff/lint ignore comments in changed files and global ignores in pyproject.toml
#
# Allowed exceptions:
# - S101 (assert) in tests/ - pytest idiomatically uses assert statements
# - D203, D213 - mutually conflicting with D211, D212 (must choose one style)

# Read hook input from stdin (required)
input=$(cat)

cd "$CLAUDE_PROJECT_DIR"

# Get the file path from the hook input
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

errors=""

# Check for global ignores in pyproject.toml
if [[ "$file_path" == *"pyproject.toml" ]]; then
    # Check for ignore list in ruff config
    # Allow only D203 and D213 (mutually conflicting rules)
    global_ignores=$(grep -nE '^\s*ignore\s*=\s*\[' pyproject.toml 2>/dev/null || true)
    if [ -n "$global_ignores" ]; then
        # Extract the ignore block content
        ignore_content=$(sed -n '/\[tool\.ruff\.lint\]/,/^\[/p' pyproject.toml | grep -A 20 'ignore\s*=' | head -20)
        # Check if there are any codes other than D203, D213
        disallowed_global=$(echo "$ignore_content" | grep -oE '"[A-Z]+[0-9]+"' | grep -vE '"D203"|"D213"' || true)
        if [ -n "$disallowed_global" ]; then
            errors="Found disallowed global ruff ignores in pyproject.toml:
$ignore_content

Only D203 and D213 (mutually conflicting rules) are allowed as global ignores.
Fix the underlying lint issues instead."
        fi
    fi

    # Check for per-file-ignores (allow only S101 in tests)
    if grep -q 'per-file-ignores' pyproject.toml 2>/dev/null; then
        pfi_content=$(sed -n '/\[tool\.ruff\.lint\.per-file-ignores\]/,/^\[/p' pyproject.toml)
        # Check if there are any ignores other than S101 in tests
        disallowed=$(echo "$pfi_content" | grep -v '^\[' | grep -v '^$' | grep -v '"tests/\*".*S101' || true)
        if [ -n "$disallowed" ]; then
            errors="${errors}

Found disallowed per-file-ignores in pyproject.toml:
$disallowed

Only S101 in tests/ is allowed as a per-file ignore."
        fi
    fi
fi

# Only check Python files for inline ignores
if [[ "$file_path" == *.py ]]; then
    # Check for ignore patterns
    ignores=$(grep -nE '(# noqa|# type: ignore|# pragma: no cover|# skipqa|# ruff: noqa)' "$file_path" 2>/dev/null || true)

    if [ -n "$ignores" ]; then
        errors="${errors}

Found lint ignore comments in $file_path:
$ignores

Please remove ignore comments and fix the underlying issues."
    fi
fi

if [ -n "$errors" ]; then
    echo "$errors" >&2
    exit 2
fi

exit 0

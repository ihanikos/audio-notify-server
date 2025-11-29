#!/bin/bash
# Run ruff linting after file edits
# Treats warnings as errors

# Read hook input from stdin (required)
cat > /dev/null

cd "$CLAUDE_PROJECT_DIR"

# Only run if Python files exist
if ls src/**/*.py tests/*.py &>/dev/null; then
    output=$(hatch run lint 2>&1)
    status=$?

    # Check for warnings in output (treat as errors)
    if echo "$output" | grep -q "^warning:"; then
        echo "$output" >&2
        echo "Lint: Warnings found (treated as errors)" >&2
        exit 2
    fi

    if [ $status -eq 0 ]; then
        echo "Lint: All checks passed!"
    else
        echo "$output" >&2
        echo "Lint: Issues found" >&2
        exit 2
    fi
fi

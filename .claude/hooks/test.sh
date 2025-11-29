#!/bin/bash
# Run pytest after file edits

# Read hook input from stdin (required)
cat > /dev/null

cd "$CLAUDE_PROJECT_DIR"

# Only run if test files exist
if ls tests/*.py &>/dev/null; then
    output=$(hatch run test 2>&1)
    status=$?
    if [ $status -eq 0 ]; then
        echo "Tests: All passed!"
    else
        echo "$output" >&2
        echo "Tests: Some failures" >&2
        exit 2
    fi
fi

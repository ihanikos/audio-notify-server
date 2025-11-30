#!/bin/bash
# PreToolUse hook to explain why .claude directory access is forbidden
#
# This hook provides a helpful error message when Claude attempts to
# read, edit, or write files in the .claude directory.

input=$(cat)

cd "$CLAUDE_PROJECT_DIR" || exit 2

# Extract the file path, pattern, and command from hook input
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')
pattern=$(echo "$input" | jq -r '.tool_input.pattern // empty')
command=$(echo "$input" | jq -r '.tool_input.command // empty')

# Check if accessing .claude directory
is_claude_dir=false

if [[ "$file_path" == *".claude"* ]]; then
    is_claude_dir=true
fi

if [[ "$pattern" == *".claude"* ]]; then
    is_claude_dir=true
fi

if [[ "$command" == *".claude"* ]]; then
    is_claude_dir=true
fi

if [ "$is_claude_dir" = true ]; then
    cat >&2 << 'EOF'
ACCESS DENIED: The .claude directory is protected.

This directory contains project hooks and settings that enforce code quality
standards (linting, testing, no-ignores policy). To maintain the integrity
of these guardrails, Claude is not permitted to read, modify, or list files
in this directory.

If you need to modify hooks or settings, please do so manually or ask the
project maintainer.
EOF
    exit 2
fi

exit 0

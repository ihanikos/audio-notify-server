#!/bin/bash
# Prevent reckless use of pkill and killall

# Read hook input from stdin
input=$(cat)

# Get the command from the hook input
command=$(echo "$input" | jq -r '.tool_input.command // empty')

# Check for pkill or killall
if echo "$command" | grep -qE '\b(pkill|killall)\b'; then
    echo "STOP: Do not use pkill or killall - these are dangerous blanket commands." >&2
    echo "" >&2
    echo "Instead:" >&2
    echo "1. Use 'ps aux | grep <pattern>' to find the specific PIDs" >&2
    echo "2. Review the process list carefully" >&2
    echo "3. Use 'kill <specific-pid>' to kill only the intended processes" >&2
    echo "" >&2
    echo "This prevents accidentally killing unrelated processes like the audio-notify-server." >&2
    exit 2
fi

exit 0

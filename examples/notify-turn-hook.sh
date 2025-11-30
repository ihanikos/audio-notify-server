#!/bin/bash
# Sample Stop hook for Claude Code - notifies audio-notify-server when Claude finishes
#
# Installation:
#   1. Copy this file to ~/.claude/hooks/notify-turn.sh
#   2. chmod +x ~/.claude/hooks/notify-turn.sh
#   3. Add to ~/.claude/settings.json:
#      {
#        "hooks": {
#          "Stop": [
#            {
#              "type": "command",
#              "command": "~/.claude/hooks/notify-turn.sh",
#              "timeout": 120
#            }
#          ]
#        }
#      }
#   4. Set CLAUDE_NOTIFY_SERVER env var or edit the default below
#
# This hook summarizes what was done using claude --print and sends
# a spoken notification via audio-notify-server.

# Prevent recursive hook triggers from claude --print
LOCKFILE="/tmp/notify-hook.lock"
if [ -f "$LOCKFILE" ]; then
    exit 0
fi

# Read hook input from stdin
input=$(cat)

# Extract session info from hook input
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty')
cwd=$(echo "$input" | jq -r '.cwd // empty')

# Run the actual work in background so hook returns immediately
nohup bash -c '
NOTIFY_SERVER="${CLAUDE_NOTIFY_SERVER:-http://localhost:51515}"
transcript_path="$1"
cwd="$2"

project_name=$(basename "$cwd" 2>/dev/null || echo "unknown")
message="Your turn in $project_name"

if [ -n "$transcript_path" ] && [ -f "$transcript_path" ]; then
    last_user_msg=$(cat "$transcript_path" | jq -rs '\''
        map(select(.type == "user" and (.message.content | type == "string"))) |
        last |
        .message.content // empty
    '\'' 2>/dev/null | head -c 500)

    assistant_msgs=$(cat "$transcript_path" | jq -rs '\''
        (map(select(.type == "user" and (.message.content | type == "string"))) | last | .timestamp) as $last_user_ts |
        map(select(.type == "assistant" and .timestamp > $last_user_ts)) |
        map(.message.content | if type == "array" then map(select(.type == "text") | .text) | join("") else . end) |
        map(select(length > 0)) |
        join("\n\n")
    '\'' 2>/dev/null | head -c 2000)

    if [ -n "$assistant_msgs" ]; then
        prompt="Output ONLY a single short sentence (max 15 words) summarizing what was done. No questions, no explanations, no preamble. Just the summary sentence.

User asked: ${last_user_msg:0:200}

Assistant did: ${assistant_msgs:0:1500}"

        touch /tmp/notify-hook.lock
        summary=$(echo "$prompt" | claude --print --model haiku 2>/dev/null)
        rm -f /tmp/notify-hook.lock

        if [ -n "$summary" ]; then
            message="$summary"
        fi
    fi
fi

json_message=$(echo "$message" | jq -Rs ".")

curl -s -X POST "$NOTIFY_SERVER/notify" \
    -H "Content-Type: application/json" \
    -d "{\"message\": $json_message, \"speak\": true, \"sound\": true}" \
    --connect-timeout 5 \
    --max-time 60 \
    > /dev/null 2>&1
' _ "$transcript_path" "$cwd" > /dev/null 2>&1 &

exit 0

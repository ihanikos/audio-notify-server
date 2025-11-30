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
#
# Configuration (via environment variables):
#   CLAUDE_NOTIFY_SERVER - URL of the audio-notify-server (default: http://localhost:51515)
#   CLAUDE_NOTIFY_MIN_DURATION - Minimum task duration in seconds to trigger notification (default: 60)
#
# This hook summarizes what was done using claude --print and sends
# a spoken notification via audio-notify-server. Only triggers for
# tasks that take longer than MIN_DURATION seconds.

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
# Brief delay to ensure transcript is fully written
sleep 2

NOTIFY_SERVER="${CLAUDE_NOTIFY_SERVER:-http://localhost:51515}"
MIN_DURATION="${CLAUDE_NOTIFY_MIN_DURATION:-60}"
transcript_path="$1"
cwd="$2"

# Check task duration - only notify for long-running tasks
if [ -n "$transcript_path" ] && [ -f "$transcript_path" ]; then
    # Get timestamp of last user message and last assistant message
    duration_info=$(cat "$transcript_path" | jq -rs '\''
        (map(select(.type == "user" and (.message.content | type == "string"))) | last | .timestamp) as $user_ts |
        (map(select(.type == "assistant")) | last | .timestamp) as $asst_ts |
        if $user_ts and $asst_ts then
            {
                user_ts: $user_ts,
                asst_ts: $asst_ts,
                duration: (($asst_ts | fromdateiso8601) - ($user_ts | fromdateiso8601))
            }
        else
            {duration: 0}
        end
    '\'' 2>/dev/null)

    duration=$(echo "$duration_info" | jq -r '.duration // 0')

    if [ "$(echo "$duration < $MIN_DURATION" | bc -l)" = "1" ]; then
        exit 0
    fi
fi

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
        [.[] | select(.type == "assistant" and .timestamp > $last_user_ts) |
         .message.content | if type == "array" then .[] | select(.type == "text") | .text else . end] |
        map(select(. != null and length > 0)) |
        join("\n")
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

# audio-notify-server

A lightweight local audio notification server for remote task completion alerts. Designed to receive simple API calls (via curl) from remote servers and play sounds or speak messages locally.

## Quick Reference (for callers)

```bash
# Sound only
curl -X POST http://SERVER_IP:51515/notify

# Sound + spoken message
curl -X POST http://SERVER_IP:51515/notify \
     -H "Content-Type: application/json" \
     -d '{"message": "Build complete", "speak": true}'

# GET (simpler)
curl "http://SERVER_IP:51515/notify?message=Done&speak=true"
```

Interactive API docs available at `http://SERVER_IP:51515/docs`

## Features

- Simple HTTP API for triggering notifications
- Sound playback using system audio players
- Optional text-to-speech (TTS) for messages
- Binds to specific interfaces (ideal for VPN-only access)
- Auto-detect interfaces by prefix (for ZeroTier's dynamic interface names)
- Secure by default (binds to localhost)
- Systemd user service for running on boot
- No authentication required (relies on network isolation)

## Installation

```bash
# Clone or download, then run the installer
./install.sh

# Or install manually with pip
pip install --user -e .
```

The installer will:
1. Install the package
2. Create a systemd user service
3. Optionally enable and start the service

## Usage

### Starting the Server

```bash
# Default: localhost only (safest)
audio-notify-server

# Bind to ZeroTier (auto-detect zt* interface)
audio-notify-server --interface-prefix zt

# Bind to WireGuard
audio-notify-server --interface-prefix wg

# Bind to a specific interface
audio-notify-server --interface tun0

# Bind to a specific IP
audio-notify-server --host 10.8.0.2

# Custom port (default: 51515)
audio-notify-server --port 51516

# List available interfaces
audio-notify-server --list-interfaces

# Enable debug logging
audio-notify-server --debug

# Use custom notification sound
audio-notify-server --sound /path/to/sound.wav
```

### Systemd Service (ZeroTier)

The installer creates a systemd user service that:
- Waits for the ZeroTier interface to appear
- Auto-detects the `zt*` interface (handles dynamic names)
- Restarts on failure

```bash
# Enable and start
systemctl --user enable --now audio-notify-server

# Check status
systemctl --user status audio-notify-server

# View logs
journalctl --user -u audio-notify-server -f

# For service to run before login (on boot)
sudo loginctl enable-linger $USER
```

To use a different interface prefix (e.g., WireGuard):
```bash
./install.sh wg
```

### Sending Notifications

From a remote server (replace IP with your VPN IP):

```bash
# Simple notification (sound only)
curl -X POST http://10.8.0.2:51515/notify

# With message displayed in response
curl -X POST http://10.8.0.2:51515/notify \
     -H "Content-Type: application/json" \
     -d '{"message": "Build complete!"}'

# With TTS (speaks the message)
curl -X POST http://10.8.0.2:51515/notify \
     -H "Content-Type: application/json" \
     -d '{"message": "Deployment finished!", "speak": true}'

# Sound only, no TTS
curl -X POST http://10.8.0.2:51515/notify \
     -H "Content-Type: application/json" \
     -d '{"sound": true, "speak": false}'

# GET request (simpler for scripts)
curl "http://10.8.0.2:51515/notify?message=Task%20done&speak=true"

# Health check
curl http://10.8.0.2:51515/health
```

### Shell Function for Remote Servers

Add to your remote server's `.bashrc` or `.zshrc`:

```bash
notify() {
    local msg="${1:-Task complete}"
    curl -s -X POST "http://YOUR_VPN_IP:51515/notify" \
         -H "Content-Type: application/json" \
         -d "{\"message\": \"$msg\", \"speak\": true}" > /dev/null 2>&1
}

# Usage:
# long-running-command && notify "Build finished!"
# make build && notify
```

## API Reference

### POST /notify

Trigger a notification.

**Request Body (JSON):**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| message | string | "" | Message to speak via TTS |
| sound | bool | true | Play notification sound |
| speak | bool | false | Speak message via TTS |

**Response:**
```json
{
  "success": true,
  "actions": [
    {"type": "sound", "success": true},
    {"type": "tts", "success": true, "message": "Build complete!"}
  ]
}
```

### GET /notify

Same as POST, using query parameters.

### GET /health

Health check endpoint. Returns `{"status": "ok"}`.

## Configuration

### Server Configuration

Create `/etc/audio-notify-server/config.json` to customize server behavior:

```json
{
  "max_message_length": 500
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| max_message_length | 500 | Maximum characters allowed in TTS messages. Requests exceeding this limit receive a 400 error asking to summarize. |

### Logging

Logs are written to `~/.local/state/audio-notify-server/audio-notify-server.log` with automatic rotation (10 MB) and retention (7 days).

Use `--debug` for verbose logging:
```bash
audio-notify-server --debug
```

## Security Considerations

- **Default binding**: Localhost only (127.0.0.1)
- **No authentication**: Relies on network isolation (VPN)
- **Recommended setup**: Bind to VPN interface only (`--interface-prefix zt`)
- **Never bind to 0.0.0.0** on untrusted networks
- **Message length limit**: Configurable max length prevents abuse

## Requirements

- Python 3.9+
- For sound: `paplay` (PulseAudio), `pw-play` (PipeWire), `aplay` (ALSA), or `mpv`/`ffplay`
- For TTS: `pyttsx3` (included) or `espeak`/`espeak-ng`/`festival`

## Development

```bash
# Install dev dependencies
hatch env create

# Run tests
hatch run test

# Lint
hatch run lint

# Format
hatch run format
```

## License

MIT

"""Command-line interface for audio-notify-server."""

from __future__ import annotations

import argparse
import array
import fcntl
import socket
import struct
import sys
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from .config import get_elevenlabs_config
from .server import run_server

if TYPE_CHECKING:
    from collections.abc import Sequence

# Timeout for ElevenLabs API requests (seconds)
ELEVENLABS_API_TIMEOUT = 30.0


def get_interface_ip(interface_name: str) -> str | None:
    """Return the IP address of a network interface.

    Args:
        interface_name: Name of the interface (e.g., 'tun0', 'wg0', 'eth0').

    Returns:
        IP address string or None if not found.

    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ip_addr = socket.inet_ntoa(
            fcntl.ioctl(
                sock.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack("256s", interface_name.encode()[:15]),
            )[20:24],
        )
    except OSError:
        return None
    else:
        return ip_addr


def list_interfaces() -> list[tuple[str, str]]:
    """Return available network interfaces and their IPs.

    Returns:
        List of (interface_name, ip_address) tuples.

    """
    try:
        # Get list of interfaces
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        max_interfaces = 128
        bytes_needed = max_interfaces * 40
        names = array.array("B", b"\0" * bytes_needed)
        outbytes = struct.unpack(
            "iL",
            fcntl.ioctl(
                sock.fileno(),
                0x8912,  # SIOCGIFCONF
                struct.pack("iL", bytes_needed, names.buffer_info()[0]),
            ),
        )[0]

        namestr = names.tobytes()
        interfaces = []
        for i in range(0, outbytes, 40):
            name = namestr[i : i + 16].split(b"\0", 1)[0].decode()
            ip = socket.inet_ntoa(namestr[i + 20 : i + 24])
            interfaces.append((name, ip))
    except OSError:
        # Fallback: just return localhost
        interfaces = [("lo", "127.0.0.1")]

    return interfaces


def find_interface_by_prefix(prefix: str) -> tuple[str, str] | None:
    """Find the first interface matching a prefix.

    Args:
        prefix: Interface name prefix (e.g., 'zt', 'tun', 'wg').

    Returns:
        Tuple of (interface_name, ip_address) or None if not found.

    """
    for name, ip in list_interfaces():
        if name.startswith(prefix):
            return name, ip
    return None


def _handle_list_interfaces() -> None:
    """List available network interfaces and exit."""
    logger.info("Available interfaces:")
    for name, ip in list_interfaces():
        logger.info("  {}: {}", name, ip)
    sys.exit(0)


def _handle_list_voices() -> None:
    """List available ElevenLabs voices and exit."""
    config = get_elevenlabs_config()
    if not config.enabled:
        logger.error("ElevenLabs is disabled in configuration")
        sys.exit(1)
    if not config.api_key:
        logger.error("ElevenLabs API key not configured")
        logger.info(
            "Set ELEVENLABS_API_KEY or add to ~/.config/audio-notify-server/config.json",
        )
        sys.exit(1)

    try:
        with httpx.Client(timeout=ELEVENLABS_API_TIMEOUT) as client:
            response = client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": config.api_key},
            )
            response.raise_for_status()
            try:
                voices = response.json().get("voices", [])
            except ValueError:
                logger.error("Invalid response from ElevenLabs API")
                sys.exit(1)
            logger.info("Available ElevenLabs voices:")
            for voice in voices:
                labels = voice.get("labels", {})
                accent = labels.get("accent", "")
                gender = labels.get("gender", "")
                desc = labels.get("description", "")
                info = ", ".join(filter(None, [gender, accent, desc]))
                name = voice.get("name", "Unknown")
                voice_id = voice.get("voice_id", "N/A")
                logger.info("  {} ({}): {}", name, voice_id, info)
    except httpx.HTTPStatusError as e:
        logger.error("ElevenLabs API error: {}", e.response.text)
        sys.exit(1)
    except httpx.RequestError as e:
        logger.error("Request failed: {}", e)
        sys.exit(1)
    sys.exit(0)


def _resolve_host(args: argparse.Namespace) -> str:
    """Resolve the host address from interface arguments.

    Args:
        args: Parsed command line arguments.

    Returns:
        The IP address to bind to.

    """
    host = args.host

    # Interface prefix takes precedence (for ZeroTier with dynamic names)
    if args.interface_prefix:
        result = find_interface_by_prefix(args.interface_prefix)
        if result is None:
            logger.error("No interface found with prefix '{}'", args.interface_prefix)
            logger.info("Use --list-interfaces to see available interfaces")
            sys.exit(1)
        interface_name, interface_ip = result
        host = interface_ip
        logger.info("Binding to interface {} ({})", interface_name, host)
    elif args.interface:
        interface_ip = get_interface_ip(args.interface)
        if interface_ip is None:
            logger.error("Could not find interface '{}'", args.interface)
            logger.info("Use --list-interfaces to see available interfaces")
            sys.exit(1)
        host = interface_ip
        logger.info("Binding to interface {} ({})", args.interface, host)
    else:
        logger.debug("Using default host: {}", host)

    return host


def _create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser.

    Returns:
        Configured ArgumentParser instance.

    """
    parser = argparse.ArgumentParser(
        prog="audio-notify-server",
        description="Local audio notification server for remote task completion alerts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start on localhost (default, safest)
  audio-notify-server

  # Bind to ZeroTier (auto-detect zt* interface)
  audio-notify-server --interface-prefix zt

  # Bind to a specific VPN interface
  audio-notify-server --interface tun0
  audio-notify-server --interface wg0

  # Bind to a specific IP
  audio-notify-server --host 10.8.0.2

  # Use custom port
  audio-notify-server --port 51516

  # List available interfaces
  audio-notify-server --list-interfaces

Sending notifications (from remote server):
  # Simple notification (sound only)
  curl -X POST http://10.8.0.2:51515/notify

  # With message (spoken via TTS)
  curl -X POST http://10.8.0.2:51515/notify \\
       -H "Content-Type: application/json" \\
       -d '{"message": "Build complete!", "speak": true}'

  # GET request (for simpler scripting)
  curl "http://10.8.0.2:51515/notify?message=Done&speak=true"
        """,
    )

    parser.add_argument(
        "--host",
        "-H",
        default="127.0.0.1",
        help="IP address to bind to (default: 127.0.0.1). Use with caution!",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=51515,
        help="Port to listen on (default: 51515)",
    )
    parser.add_argument(
        "--interface",
        "-i",
        help="Network interface to bind to (e.g., tun0, wg0). Overrides --host.",
    )
    parser.add_argument(
        "--interface-prefix",
        "-P",
        help="Bind to first interface matching prefix (e.g., 'zt' for ZeroTier).",
    )
    parser.add_argument(
        "--sound",
        "-s",
        help="Path to custom notification sound file",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug mode",
    )
    parser.add_argument(
        "--list-interfaces",
        "-l",
        action="store_true",
        help="List available network interfaces and exit",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available ElevenLabs voices and exit",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the CLI application.

    Args:
        argv: Command line arguments (default: sys.argv[1:]).

    """
    parser = _create_parser()
    args = parser.parse_args(argv)

    if args.list_interfaces:
        _handle_list_interfaces()

    if args.list_voices:
        _handle_list_voices()

    host = _resolve_host(args)

    # Security warning for non-localhost binding
    if host not in {"127.0.0.1", "::1"}:
        logger.warning("Binding to {} - ensure this is a trusted network!", host)

    run_server(
        host=host,
        port=args.port,
        sound_file=args.sound,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()

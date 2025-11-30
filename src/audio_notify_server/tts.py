"""Text-to-speech functionality."""

import shutil
import subprocess


def speak(message: str) -> bool:
    """Speak a message using text-to-speech.

    Args:
        message: The message to speak.

    Returns:
        True if TTS was successful, False otherwise.

    """
    if not message:
        return False

    # Use system TTS commands directly (pyttsx3 has instability issues with espeak driver)
    tts_commands = [
        ["espeak", message],
        ["espeak-ng", message],
        ["spd-say", message],
        ["festival", "--tts"],  # needs stdin
    ]

    for cmd in tts_commands:
        if shutil.which(cmd[0]):
            try:
                if cmd[0] == "festival":
                    subprocess.run(
                        cmd,
                        input=message.encode(),
                        check=True,
                        capture_output=True,
                        timeout=30,
                    )
                else:
                    subprocess.run(
                        cmd,
                        check=True,
                        capture_output=True,
                        timeout=30,
                    )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                continue
            else:
                return True

    return False

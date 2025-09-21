#!/usr/bin/env python3
"""
Telegram Session String Generator
A user-friendly tool to generate Telegram session strings for bots and users.
"""

import asyncio
import os
import subprocess
import sys
from getpass import getpass
from typing import Any

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = {}

from pyrogram import Client, errors


class Colors:
    """Simple color codes for terminal output"""

    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_colored(text: str, color: str = Colors.END) -> None:
    """Print colored text to terminal"""
    print(f"{color}{text}{Colors.END}")


def print_header() -> None:
    """Print application header"""
    print_colored("\n" + "=" * 60, Colors.BLUE)
    print_colored("    🚀 TELEGRAM SESSION STRING GENERATOR 🚀", Colors.BOLD)
    print_colored("=" * 60 + "\n", Colors.BLUE)


def print_separator() -> None:
    """Print a simple separator line"""
    print_colored("-" * 50, Colors.BLUE)


def coalesce(*values, default=None) -> Any:
    """Return first non-empty value"""
    for v in values:
        if v not in (None, "", "None"):
            return v

    return default


def get_device_props(keys: list) -> dict[str, str]:
    """Get Android device properties"""
    props = {}
    for key in keys:
        try:
            value = subprocess.check_output(
                ["getprop", key], text=True, timeout=1
            ).strip()
        except Exception:
            value = ""

        props[key] = value

    return props


def detect_device() -> tuple[str, str]:
    """Auto-detect device information"""
    props = get_device_props(
        [
            "ro.product.manufacturer",
            "ro.product.brand",
            "ro.product.model",
            "ro.build.version.release",
            "ro.build.id",
        ]
    )

    manufacturer = (
        props.get("ro.product.manufacturer")
        or props.get("ro.product.brand")
        or "Android"
    )
    model = props.get("ro.product.model") or "Device"
    android_version = props.get("ro.build.version.release") or "10"
    build_id = props.get("ro.build.id")

    device_model = f"{manufacturer} {model}".strip()
    system_version = f"Android {android_version}"
    if build_id:
        system_version += f" ({build_id})"

    return device_model, system_version


def load_environment() -> dict[str, str]:
    """Load configuration from .env file and environment variables"""
    config = {}

    # Load from .env file
    config.update({k: v for k, v in dotenv_values().items() if v})

    # Load from environment variables (higher priority)
    config.update({k: v for k, v in os.environ.items() if v})

    return {k.lower(): v for k, v in config.items()}


def ask_input(
    prompt: str, default: str = None, secret: bool = False, validator=None
) -> str:
    """Get user input with validation"""
    display_prompt = f"💬 {prompt}"
    if default:
        display_prompt += f" [{default}]"

    display_prompt += ": "

    while True:
        try:
            if secret:
                value = getpass(display_prompt)
            else:
                value = input(display_prompt)
        except KeyboardInterrupt:
            raise
        except Exception:
            value = input(display_prompt)

        # Use default if empty input
        if not value and default:
            value = default

        # Validate input
        if validator and value:
            is_valid, error_msg = validator(value)
            if not is_valid:
                print_colored(f"❌ {error_msg}", Colors.RED)
                continue

        return value


def progress_step(current: int, total: int, message: str) -> None:
    """Display progress step"""
    width = len(str(total))
    print_colored(f"[{str(current).rjust(width)}/{total}] 🔄 {message}", Colors.YELLOW)


def choose_login_mode(default: str = "user") -> str:
    """Choose between user or bot login mode"""
    print_colored("📱 Choose login mode:", Colors.BOLD)
    print("   • user - Login with phone number (for personal use)")
    print("   • bot  - Login with bot token (for bot applications)")

    while True:
        mode = input(f"💬 Mode [user/bot] [{default}]: ").strip().lower()
        if not mode:
            return default

        if mode in ("user", "bot"):
            return mode

        print_colored("❌ Please choose 'user' or 'bot'", Colors.RED)


def validate_api_id(api_id: str) -> tuple[bool, str]:
    """Validate Telegram API ID"""
    try:
        value = int(api_id)
        if value <= 0:
            return False, "API ID must be a positive number"

        return True, ""
    except ValueError:
        return False, "API ID must be a valid number"


def validate_phone(phone: str) -> tuple[bool, str]:
    """Basic phone number validation"""
    if not phone.startswith("+"):
        return False, "Phone number must start with '+' (international format)"

    if len(phone.replace("+", "").replace(" ", "").replace("-", "")) < 10:
        return False, "Phone number seems too short"

    return True, ""


async def login_as_user(client: Client, phone: str) -> None:
    """Handle user login process"""
    print_colored("📱 Sending login code to your phone...", Colors.YELLOW)
    sent_code = await client.send_code(phone)

    code = ask_input("Enter the login code from Telegram").strip().replace(" ", "")

    try:
        await client.sign_in(
            phone_number=phone,
            phone_code=code,
            phone_code_hash=sent_code.phone_code_hash,
        )
    except errors.SessionPasswordNeeded:
        print_colored("🔐 Two-factor authentication is enabled", Colors.YELLOW)
        password = ask_input("Enter your 2FA password", secret=True)
        await client.check_password(password=password)


async def login_as_bot(client: Client) -> None:
    """Handle bot login process"""
    # For bots, we don't need to call start() after connect()
    # The connection is already established


def display_summary(config: dict[str, Any]) -> None:
    """Display configuration summary"""
    print_colored("📋 Configuration Summary:", Colors.BOLD)
    print_separator()

    summary_items = [
        ("Mode", config["mode"]),
        ("API ID", config["api_id"]),
        (
            "API Hash",
            f"{'*' * 6}{config['api_hash'][-4:]}" if config["api_hash"] else "",
        ),
    ]

    if config["mode"] == "user":
        summary_items.append(("Phone", config.get("phone", "")))
    else:
        token_display = (
            config.get("bot_token", "")[:10] + "..." if config.get("bot_token") else ""
        )
        summary_items.append(("Bot Token", token_display))

    summary_items.extend(
        [
            ("Device Model", config["device_model"]),
            ("System Version", config["system_version"]),
            ("App Version", config["app_version"]),
            ("Language", config["lang_code"]),
            ("System Language", config["system_lang_code"]),
            ("Proxy", config.get("proxy") or "None"),
        ]
    )

    for label, value in summary_items:
        print(f"  {label:<15}: {value}")

    print_separator()


async def generate_session() -> None:
    """Main session generation workflow"""
    print_header()

    # Load existing configuration
    env_config = load_environment()
    device_model, system_version = detect_device()

    print_colored(
        "⚙️  Loading configuration (press Enter to use detected/default values)",
        Colors.GREEN,
    )
    print_separator()

    # Get user inputs
    mode = choose_login_mode(coalesce(env_config.get("mode"), "user"))
    print()

    api_id = ask_input(
        "Telegram API ID", default=env_config.get("api_id"), validator=validate_api_id
    )

    api_hash = ask_input("Telegram API Hash", default=env_config.get("api_hash"))

    phone = bot_token = None
    if mode == "user":
        phone = ask_input(
            "Phone number (international format)",
            default=env_config.get("phone"),
            validator=validate_phone,
        )
    else:
        bot_token = ask_input(
            "Bot token (format: 1234567890:ABC...)", default=env_config.get("bot_token")
        )

    # Optional advanced settings
    print_colored("\n🔧 Advanced Settings (optional):", Colors.GREEN)
    device = ask_input(
        "Device model", default=coalesce(env_config.get("device_model"), device_model)
    )

    sys_ver = ask_input(
        "System version",
        default=coalesce(env_config.get("system_version"), system_version),
    )

    app_ver = ask_input(
        "App version", default=coalesce(env_config.get("app_version"), "Telegram 1.0")
    )

    lang_code = ask_input(
        "Language code", default=coalesce(env_config.get("lang_code"), "en")
    )

    sys_lang = ask_input(
        "System language code",
        default=coalesce(env_config.get("system_lang_code"), lang_code),
    )

    # Create configuration summary
    config = {
        "mode": mode,
        "api_id": api_id,
        "api_hash": api_hash,
        "phone": phone,
        "bot_token": bot_token,
        "device_model": device,
        "system_version": sys_ver,
        "app_version": app_ver,
        "lang_code": lang_code,
        "system_lang_code": sys_lang,
        "proxy": env_config.get("proxy"),
    }

    print()
    display_summary(config)

    input("\n✅ Press Enter to continue or Ctrl+C to cancel...")

    # Start session generation
    total_steps = 5 if mode == "user" else 4
    current_step = 1

    print_colored("\n🚀 Starting session generation...", Colors.GREEN)

    # Prepare client
    progress_step(current_step, total_steps, "Preparing Telegram client")
    current_step += 1

    client_config = {
        "name": "session_gen",
        "api_id": int(api_id),
        "api_hash": str(api_hash),
        "device_model": str(device),
        "system_version": str(sys_ver),
        "app_version": str(app_ver),
        "lang_code": str(lang_code),
        "system_lang_code": str(sys_lang),
        "in_memory": True,
    }

    if config.get("proxy"):
        client_config["proxy"] = config["proxy"]

    if mode == "bot":
        client_config["bot_token"] = str(bot_token)

    client = Client(**client_config)

    try:
        if mode == "user":
            # For users: connect first, then login
            progress_step(current_step, total_steps, "Connecting to Telegram")
            current_step += 1
            await client.connect()

            progress_step(current_step, total_steps, "Processing user login")
            current_step += 1
            await login_as_user(client, phone)

        else:
            # For bots: use start() which handles connection and authentication
            progress_step(
                current_step, total_steps, "Connecting and authenticating bot"
            )
            current_step += 1
            await client.start()

        # Generate session string
        progress_step(current_step, total_steps, "Generating session string")
        current_step += 1
        session_string = await client.export_session_string()

        # Cleanup
        progress_step(current_step, total_steps, "Cleaning up connection")
        if client.is_connected:
            await client.stop()

        # Display result
        print_colored("\n🎉 SUCCESS! Your session string:", Colors.GREEN)
        print("=" * 60)
        print_colored(session_string, Colors.BOLD)
        print("=" * 60)
        print_colored(
            "\n💡 Keep this string safe and never share it with anyone!", Colors.YELLOW
        )

    except Exception as e:
        if client.is_connected:
            await client.stop()

        raise e


def main():
    """Main entry point"""
    try:
        # Try to use uvloop for better performance
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

    try:
        asyncio.run(generate_session())
    except KeyboardInterrupt:
        print_colored("\n\n❌ Operation cancelled by user.", Colors.RED)
        sys.exit(130)
    except Exception as e:
        print_colored(f"\n💥 Error: {str(e)}", Colors.RED)
        sys.exit(1)


if __name__ == "__main__":
    main()

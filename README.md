# Telegram Selfbot

A modular Telegram selfbot built with PyroTgFork (a Pyrogram fork) and PostgreSQL for persistent storage. This repository provides an event-driven framework for automating a Telegram user account (selfbot). Use responsibly — selfbots violate Telegram Terms of Service and may result in account restrictions.

Version: 2025-10-27  
Python: 3.11+ | Database: PostgreSQL | Framework: PyroTgFork

## Key Features

- Modular architecture for easy extension and removal of features
- PostgreSQL storage for persistent sessions and state
- Event-driven design with a priority-based listener system
- Hot reload to update code without losing sessions
- Docker-ready for containerized deployments
- Async/await for efficient, non-blocking operations

## Built-in Modules

| Module  | Command                      | Description                         |
|--------:|------------------------------|-------------------------------------|
| AFK     | `afk` / `afk -r [reason]`    | Toggle AFK status; use `-r` to set a reason |
| Call    | `[action]call [options]`     | Join and manage voice chats         |
| Debug   | `code#` or `e code`          | Execute Python code                 |
| Delete  | `d` or `del`                 | Delete messages                     |
| GenAI   | `query !?`                   | Chat with Gemini AI (GenAI module)  |
| Graph   | `graph [text] -t [title]`    | Create Telegraph pages              |
| Help    | `help[/module]`              | Show available commands             |
| Ping    | `p` or `ping`                | Check latency                       |
| Purge   | `purge[me] [limit]`          | Bulk delete messages                |
| Restart | `r`                          | Restart and update the application  |

## Quick Start

### Prerequisites

- Python 3.11 or newer
- PostgreSQL database
- Telegram API credentials (get from https://my.telegram.org)
- Bot token from @BotFather (if using bot account features)
- Optional: Gemini API key for the GenAI module

### Local installation

1. Clone the repository
   ```bash
   git clone https://github.com/DeltaUniverse/selfbot.git
   cd selfbot
   ```

2. Install dependencies (Poetry recommended)
   ```bash
   pip install poetry
   poetry install
   ```

3. Configure environment
   ```bash
   cp .env.example .env
   # Edit .env and add API_ID, API_HASH, DATABASE_URL, etc.
   ```

4. Run the application
   ```bash
   poetry run python -m selfbot
   ```

### Docker

Build and run with docker-compose:
```bash
docker-compose up -d
docker-compose logs -f selfbot
docker-compose down
```

Production image:
```bash
docker build -t selfbot:latest .
docker run -d --env-file .env selfbot:latest
```

## Configuration (.env)

Create a `.env` file in the repository root and set the required variables:

```env
# Required
API_ID=your_api_id
API_HASH=your_api_hash
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Optional
GEMINI_API_KEY=your_gemini_api_key
STICKER_FILE_ID=file_id
REMOTE=https://github.com/YourRepo/selfbot
BRANCH=main
```

## Usage Examples

Basic commands:
```
# Check bot status
ping

# Show help
help
help/debug

# Delete a message (reply to the message)
<reply to message> d

# Purge messages (reply to a starting message)
<reply to start> purge 50

# Execute Python code
print("Hello")#
e await app.send_message("me", "Test")
```

AFK mode:
```
# Set AFK with a reason (use -r to provide a reason)
afk -r Working on something

# Remove AFK (call the command without -r)
afk
```

GenAI (Gemini) chat:
```
# Ask Gemini
What is Telegram MTProto? !?

# With context (reply to a message)
<reply to message> Explain this !?
```

Create Telegraph pages:
```
# Create page from inline text
graph Hello, World! -t "My Page"

# Create page from a replied message
<reply to message> graph -t "Article Title"
```

## Development

Project structure:
```
selfbot/
├── core/           # Core components (database, dispatcher, etc.)
├── modules/        # Feature modules
├── utils/          # Helper utilities
├── __init__.py
├── __main__.py
└── main.py         # Entry point
```

Creating a module (example):
```python
from pyrogram import filters
from pyrogram.types import Message
from selfbot import listener
from selfbot.module import Module

class MyModule(Module):
    name = "MyModule"
    cmds = "mycommand {arg}"
    desc = {"arg": "Description", "e.g.": "mycommand test"}

    @listener.handler(filters.regex(r"^mycommand (.+)$"), priority=1)
    async def on_message_out(self, event: Message) -> None:
        arg = event.matches[0].group(1)
        await event.edit_text(f"You said: {arg}")
```

## Deployment

systemd service example:
Create `/etc/systemd/system/selfbot.service`:
```ini
[Unit]
Description=Telegram Selfbot
After=network.target postgresql.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/selfbot
Environment="PATH=/path/to/selfbot/.venv/bin"
ExecStart=/path/to/selfbot/.venv/bin/python -m selfbot
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
Enable and start:
```bash
sudo systemctl enable selfbot
sudo systemctl start selfbot
```

Docker and docker-compose instructions are provided above for containerized deployments.

## Troubleshooting

Common issues and suggestions:

- Database connection failed
  - Verify DATABASE_URL format and credentials
  - Ensure PostgreSQL is running and reachable

- Invalid API_ID/API_HASH
  - Obtain fresh credentials at https://my.telegram.org
  - Double-check for typos in `.env`

- Module not loading
  - Check module syntax and imports
  - Inspect logs: `docker-compose logs -f` or application console

- Flood-wait errors
  - Telegram rate limits apply; the application will back off for small waits (<30s)
  - Use `purge` with safe limits for large operations

## Contributing

We welcome contributions. Suggested workflow:
1. Fork the repository.
2. Create a feature branch (for example, feature/my-feature or fix/issue-123).
3. Make changes and add tests where appropriate.
4. Run linting and tests.
5. Open a pull request with a clear description of the change.

Focus on functional improvements and tests. See BACKLOG.md for ideas.

## License

This project is released under the MIT License. See the LICENSE file for details.

## Disclaimer and Responsible Use

This repository implements a selfbot (automating a user account), which is against Telegram's Terms of Service. Use at your own risk.

- Your account may be banned.
- Keep your credentials secure.
- Do not spam or abuse the API.
- Use ethically and responsibly.

This project is provided for educational purposes only.

## Support

- Documentation: check module docstrings and the in-app `help` command
- Issues: use GitHub Issues for bug reports and feature requests
- Discussions: use the project's Telegram group or discussion channels if available
- 

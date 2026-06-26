# TTS Bot

Made by Dunhill.

Discord bot that converts text to speech and plays it in the voice channel. Built in Python, using the Google Translate voice (gTTS).

## How it works

Send a message in chat starting with `}` and the bot speaks it in the voice channel you're in. Each person has their own voice, speed and volume settings, saved automatically.

If two people use the bot at the same time, the messages go into a queue and play one after another, without cutting anyone off. When that happens, the bot announces the speaker's name before the message, so it's clear who's talking.

## Installation

1. Install the dependencies:
```
pip install -r requirements.txt
```

2. Create a `.env` file in the project folder with the bot token:
```
DISCORD_TOKEN=your_token_here
```

3. Run the bot:
```
iniciar_bot.bat
```

No need to install ffmpeg separately, it's bundled with one of the dependencies.

## Discord commands

By default the bot's commands are in English. You can switch to Portuguese with `}language pt` (or `}idioma pt`, both work). This is a global setting, it switches for everyone on the server at once, it's not per-user.

**In English (default):**
- `}<text>` — speaks the text in the voice channel
- `}voice <language> [tld]` — changes language and accent, ex: `}voice en com` for English
- `}speed <value>` — speech speed, from 0.5 to 2.0
- `}volume <value>` — speech volume, from 0.1 to 2.0
- `}name on` / `}name off` — turns your name announcement on/off when someone else is using the bot at the same time
- `}config` — shows your current configuration
- `}resetconfig` — resets everything to default
- `}language en` / `}language pt` — changes the bot's command language (global)
- `}help` — shows this list inside Discord

**In Portuguese** (after `}language pt`):
- `}<texto>`, `}voz <idioma> [tld]`, `}velocidade <valor>`, `}volume <valor>`, `}nome on/off`, `}config`, `}resetconfig`, `}idioma en/pt`, `}ajuda`

There's a 3.5 second cooldown per person between one message and the next, to prevent spam.

## Terminal commands

While the bot is running, you can type commands directly into the terminal where it's open. These stay in Portuguese on purpose, since they're an admin tool, separate from the Discord-facing commands above:

- `ajuda` — lists the commands
- `cls` — clears the screen
- `status` — shows uptime and how many voice channels are connected
- `fila` — shows how many audios are waiting in each server's queue
- `limpar` — deletes leftover temporary audio files
- `desconectar` — disconnects the bot from all voice channels
- `logs` — shows the last 10 lines of the log
- `sair` — shuts down the bot

## Auto-restart if it crashes

The `iniciar_bot.bat` file restarts the bot automatically if it crashes for any reason. Run that `.bat` instead of running `python bot.py` directly.

For it to come back up on its own after a power outage, you need to configure Windows to log in automatically and open the `.bat` on login (Task Scheduler). That part is outside the bot itself, it's system configuration.

## File structure

- `bot.py` — the bot
- `requirements.txt` — Python dependencies
- `.env` — bot token (don't share this file with anyone)
- `configs_usuarios.json` — each user's configuration (created automatically)
- `bot_language.json` — the bot's current command language, en or pt (created automatically)
- `audios/` — temporary generated audio files, deleted right after playing
- `logs/` — bot log, with automatic rotation (max 5MB per file, keeps up to 5 old ones)
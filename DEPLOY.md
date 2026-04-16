# Cloud Deploy Guide

This bot is prepared for Docker-based cloud hosting.

## Recommended path
Use a host that can run a long-lived worker/container.

## Environment variables
Set these in your host dashboard:
- MAIN_BOT_KEY
- GROQ_API_KEY
- BOT_OWNER_ID
- BOT_PREFIX
- DEFAULT_WARN_THRESHOLD
- DEFAULT_MUTE_MINUTES
- DEFAULT_MAX_WARNINGS
- AI_REPLY_COOLDOWN_SECONDS
- VOICE_RECONNECT_INTERVAL

## Docker entrypoint
The container starts with:
python main.py

## Notes
- SQLite works for a small bot, but the database file must live on persistent disk.
- If your host has ephemeral storage, switch to Postgres later.
- Voice on Linux is easier because this Dockerfile installs ffmpeg and libopus0.

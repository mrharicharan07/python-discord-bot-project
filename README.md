# Zoro Bot — Phase 1 Setup Guide

## File Structure
```
zorobot/
├── main.py              ← bot launcher (start here)
├── database.py          ← all data storage (multi-server)
├── ai.py                ← Groq AI abuse detection
└── cogs/
    ├── moderation.py    ← scoring engine, anti-raid, anti-nuke
    └── admin.py         ← all setup commands (!setlog, !whitelist, etc.)
```

---

## Step 1 — Install Python libraries

Open terminal / command prompt and run:
```
pip install discord.py groq
```

---

## Step 2 — Add your tokens

Open `main.py` and replace:
```python
TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"
```

Open `ai.py` and replace:
```python
GROQ_API_KEY = "PASTE_YOUR_GROQ_KEY"
```

Open `cogs/admin.py` and replace:
```python
BOT_OWNER_ID = 1477775862266069014   ← your Discord user ID
```

---

## Step 3 — Run locally to test

```
python main.py
```

You should see:
```
[DB] Tables ready.
[COG] Loaded: cogs.moderation
[COG] Loaded: cogs.admin
========================================
  Zoro Bot ONLINE
  Logged in as: YourBot#1234
  Servers: 1
========================================
```

---

## Step 4 — Host 24/7 FREE on Railway

Railway gives you free hosting. Bot stays online even when your laptop is off.

1. Go to https://railway.app and sign up with GitHub
2. Create new project → "Deploy from GitHub repo"
3. Upload your bot files to a GitHub repo first (or use Railway CLI)
4. Add environment variables in Railway dashboard:
   - `DISCORD_TOKEN` = your bot token
   - `GROQ_API_KEY`  = your Groq key
5. Change `main.py` to read from env:
   ```python
   import os
   TOKEN = os.getenv("DISCORD_TOKEN")
   ```
   And `ai.py`:
   ```python
   import os
   GROQ_API_KEY = os.getenv("GROQ_API_KEY")
   ```
6. Add a `requirements.txt` file with:
   ```
   discord.py
   groq
   ```
7. Deploy — Railway auto-runs `python main.py`

---

## Step 5 — Set up each server

After adding the bot to a server, type in any channel:
```
!setup
```
This shows the setup checklist. Then run:
```
!setlog #mod-logs
!whitelist add @YourName
!whitelist add @YourMod
!sensitivity 60
```

---

## Command Reference

| Command | Who | What |
|---|---|---|
| `!setup` | Anyone | Show setup guide |
| `!status` | Anyone | Show current config |
| `!ping` | Anyone | Check if bot is alive |
| `!setlog #channel` | Admin | Set log channel |
| `!whitelist add @user` | Admin | Add safe user |
| `!whitelist remove @user` | Admin | Remove safe user |
| `!whitelist list` | Admin | Show all safe users |
| `!addword <word>` | Admin | Add custom bad word |
| `!removeword <word>` | Admin | Remove custom bad word |
| `!wordlist` | Admin | Show custom bad words |
| `!warnings @user` | Admin | Check user warnings |
| `!clearwarn @user` | Admin | Reset user warnings |
| `!sensitivity <0-100>` | Admin | Change sensitivity |
| `!panic` | Owner | Lock all channels |
| `!unlock` | Owner | Unlock all channels |

---

## How the scoring system works

Every message gets a score. Action only happens if score >= threshold (default 60).

| Signal | Points |
|---|---|
| Bad word found (rule) | +40 |
| AI returns YES | +50 |
| Message under 4 words | -20 |

Example — "that movie was shit lol" → score 40 (threshold 60) → NO ACTION ✅
Example — "madarchod lanja puku" → score 120+ → WARN ✅

Adjust with `!sensitivity`:
- `!sensitivity 40` = relaxed (gaming/meme servers)
- `!sensitivity 60` = default (most servers)
- `!sensitivity 80` = strict (study/kids servers)

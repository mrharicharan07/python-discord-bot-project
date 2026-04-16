import random
import re
import time
import unicodedata
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from ai import ai_check, ai_reply
from config import AI_REPLY_COOLDOWN_SECONDS
from database import (
    add_warning,
    get_connection,
    get_custom_words,
    get_guild_config,
    get_warnings,
    is_whitelisted,
    reset_warnings,
)


LEET_MAP = str.maketrans(
    {
        '0': 'o',
        '1': 'i',
        '3': 'e',
        '4': 'a',
        '5': 's',
        '7': 't',
        '@': 'a',
        '$': 's',
        '!': 'i',
    }
)

CORE_PATTERNS = {
    'sexual_abuse': {
        'score': 45,
        'words': {
            'fuck', 'fuk', 'fucking', 'motherfucker', 'mf', 'bitch', 'asshole', 'bsdk',
            'madarchod', 'behenchod', 'mc', 'bc', 'randi', 'lanja', 'lanjakodaka',
            'puku', 'pooka', 'puka', 'erripuka', 'erripuku', 'kojjja', 'kojja', 'dengu',
            'dengey', 'chod', 'chutiya', 'lund', 'lauda', 'lawda', 'chut', 'choot',
        },
    },
    'hate_or_slur': {
        'score': 60,
        'words': {'nigger', 'niga', 'nigga', 'faggot', 'kike', 'retard', 'spastic'},
    },
    'threat': {
        'score': 55,
        'words': {'kill you', 'rape you', 'die bitch', 'go kill yourself', 'kys'},
    },
}

FALLBACK_REPLIES = [
    'I am here. Tell me what you need.',
    'Say it clearly and I will help.',
    'Need setup help, moderation help, or server tools?',
    'I can help with setup, rank, tickets, moderation, and voice.',
]

ACTION_REPLIES = [
    'That message crossed the line.',
    'Keep the chat clean.',
    'That was flagged by moderation.',
    'Tone it down.',
]


def setup_modcase_table():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS mod_cases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id    TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            action      TEXT NOT NULL,
            reason      TEXT,
            score       INTEGER,
            created_at  TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def log_case(guild_id: str, user_id: str, action: str, reason: str, score: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO mod_cases (guild_id, user_id, action, reason, score, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, user_id, action, reason, score, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_user_cases(guild_id: str, user_id: str, limit: int = 10) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT action, reason, score, created_at FROM mod_cases WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT ?",
        (guild_id, user_id, limit),
    )
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFKC', text.lower())
    text = ''.join(ch for ch in text if unicodedata.category(ch)[0] != 'C')
    text = text.translate(LEET_MAP)
    text = re.sub(r'(.){2,}', r'', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def squash_text(text: str) -> str:
    return re.sub(r'[^a-z]', '', text)


def evaluate_local_rules(text: str, custom_words: set[str]) -> tuple[int, list[str]]:
    normalized = normalize_text(text)
    squashed = squash_text(normalized)
    score = 0
    reasons = []
    for category, info in CORE_PATTERNS.items():
        category_hit = False
        for word in info['words']:
            word_normalized = squash_text(normalize_text(word))
            if word_normalized and word_normalized in squashed:
                category_hit = True
                break
        if category_hit:
            score += info['score']
            reasons.append(category)
    for custom_word in custom_words:
        custom_normalized = squash_text(normalize_text(custom_word))
        if custom_normalized and custom_normalized in squashed:
            score += 35
            reasons.append(f'custom:{custom_word}')
    if len(normalized.split()) <= 2:
        score -= 10
    return max(score, 0), reasons


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reply_cooldowns: dict[str, float] = {}
        setup_modcase_table()

    async def send_log(self, guild: discord.Guild, text: str):
        config = get_guild_config(str(guild.id))
        channel_id = config.get('log_channel_id')
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(text[:1900])
            except discord.Forbidden:
                pass

    def should_reply(self, guild_id: str) -> bool:
        now = time.time()
        last = self.reply_cooldowns.get(guild_id, 0)
        if now - last < AI_REPLY_COOLDOWN_SECONDS:
            return False
        self.reply_cooldowns[guild_id] = now
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        content = message.content.strip()
        if not content:
            return
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        config = get_guild_config(guild_id)

        if self.bot.user in message.mentions and config.get('ai_replies', True):
            await self.handle_mention(message, config)
            return
        if message.content.startswith(config.get('prefix', '!')):
            return
        if not config.get('automod_enabled', True):
            return
        if is_whitelisted(guild_id, user_id):
            return

        custom_words = get_custom_words(guild_id)
        score, reasons = evaluate_local_rules(content, custom_words)
        ai_used = False
        if 20 <= score < config.get('warn_threshold', 60):
            ai_used = True
            if await ai_check(content) == 'YES':
                score += 35
                reasons.append('ai_confirmed')

        if score >= config.get('warn_threshold', 60):
            await self.apply_action(message, score, reasons, ai_used)
            return

    async def handle_mention(self, message: discord.Message, config: dict):
        clean_msg = re.sub(rf'<@!?{self.bot.user.id}>', '', message.content).strip()
        if not clean_msg:
            await message.reply(f'{message.author.mention} yes?')
            return
        if await ai_check(clean_msg) == 'YES':
            score, reasons = evaluate_local_rules(clean_msg, get_custom_words(str(message.guild.id)))
            await self.apply_action(message, max(score, config.get('warn_threshold', 60)), reasons + ['mention_abuse'], True)
            return
        if not self.should_reply(str(message.guild.id)):
            await message.reply(f'{message.author.mention} {random.choice(FALLBACK_REPLIES)}')
            return
        reply = await ai_reply(message.author.display_name, message.guild.name, clean_msg)
        if not reply:
            reply = random.choice(FALLBACK_REPLIES)
        await message.reply(f'{message.author.mention} {reply}')

    async def apply_action(self, message: discord.Message, score: int, reasons: list[str], ai_used: bool):
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        config = get_guild_config(guild_id)
        total = add_warning(guild_id, user_id)
        max_warnings = max(2, int(config.get('max_warnings', 3)))
        mute_minutes = max(1, int(config.get('mute_minutes', 5)))
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        reason_text = ', '.join(reasons) if reasons else 'rule_match'
        await message.channel.send(
            f'{message.author.mention} Warning {total}/{max_warnings}\n{random.choice(ACTION_REPLIES)}'
        )
        action_taken = 'warn'
        if score >= config.get('warn_threshold', 60) + 25 or total >= max_warnings:
            try:
                await message.author.timeout(timedelta(minutes=mute_minutes), reason=f'Auto moderation: {reason_text}')
                await message.channel.send(f'{message.author.mention} timed out for {mute_minutes} minute(s).')
                action_taken = 'timeout'
            except (discord.Forbidden, AttributeError):
                action_taken = 'warn_only'
        if total > max_warnings:
            reset_warnings(guild_id, user_id)
        log_case(guild_id, user_id, action_taken, reason_text, score)
        await self.send_log(
            message.guild,
            f"[AUTOMOD] user={message.author} ({message.author.id}) score={score} action={action_taken} ai_used={ai_used} reasons={reason_text} content={message.content[:300]!r}",
        )

    @commands.command()
    async def whywarn(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        warnings = get_warnings(str(ctx.guild.id), str(member.id))
        await ctx.send(f'{member.mention} has {warnings} warning(s) in this server.')

    @commands.command()
    async def modhistory(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        rows = get_user_cases(str(ctx.guild.id), str(member.id))
        if not rows:
            await ctx.send(f'No moderation history found for {member.mention}.')
            return
        lines = []
        for row in rows:
            lines.append(f"**{row['action']}** | score={row['score']} | {row['reason']} | {row['created_at'][:16]}")
        embed = discord.Embed(title=f'Mod History - {member}', description='\n'.join(lines), color=discord.Color.red())
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Moderation(bot))

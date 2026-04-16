"""
main.py - Zoro bot launcher.
"""

import asyncio
import ctypes.util
import os

import discord
from discord.ext import commands

try:
    import nacl  # noqa: F401
    PYNACL_AVAILABLE = True
except Exception:
    PYNACL_AVAILABLE = False

from config import MAIN_BOT_KEY
from database import get_guild_config, setup_database


OPUS_SOURCE = 'not loaded'


def try_load_opus() -> str:
    global OPUS_SOURCE
    if discord.opus.is_loaded():
        OPUS_SOURCE = 'already loaded'
        return OPUS_SOURCE

    candidates = []
    found = ctypes.util.find_library('opus')
    if found:
        candidates.append(found)

    candidates.extend([
        'libopus-0.x64.dll',
        'libopus-0.dll',
        'opus.dll',
    ])

    local_dir = os.path.dirname(os.path.abspath(__file__))
    for name in ('libopus-0.x64.dll', 'libopus-0.dll', 'opus.dll'):
        candidates.append(os.path.join(local_dir, name))

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            discord.opus.load_opus(candidate)
            if discord.opus.is_loaded():
                OPUS_SOURCE = candidate
                return OPUS_SOURCE
        except Exception:
            continue

    OPUS_SOURCE = 'not found'
    return OPUS_SOURCE


def get_prefix(bot, message):
    if not message.guild:
        return '!'
    config = get_guild_config(str(message.guild.id))
    return config.get('prefix', '!')


intents = discord.Intents.all()
bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)


async def update_presence():
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f'{len(bot.guilds)} servers | !setup | !rank | !ticket',
        )
    )


@bot.event
async def on_ready():
    print('\n' + '=' * 48)
    print('  Zoro Bot ONLINE')
    print(f'  Logged in as: {bot.user}')
    print(f'  Servers: {len(bot.guilds)}')
    for guild in bot.guilds:
        print(f'    - {guild.name} ({guild.id})')
    print('=' * 48 + '\n')
    print(f'  Voice opus loaded: {discord.opus.is_loaded()}')
    print(f'  Voice opus source: {OPUS_SOURCE}')
    print(f'  PyNaCl available: {PYNACL_AVAILABLE}')
    await update_presence()


@bot.event
async def on_guild_join(guild):
    print(f'[+] Joined: {guild.name} ({guild.id})')
    await update_presence()

    target = guild.system_channel
    if target is None:
        me = guild.me
        for channel in guild.text_channels:
            if me and channel.permissions_for(me).send_messages:
                target = channel
                break

    if target:
        embed = discord.Embed(
            title='Zoro Bot is ready',
            description=(
                'Type `!setup` to configure this server.\n'
                'Every server keeps its own settings, moderation, XP, coins, tickets, and voice mode.'
            ),
            color=discord.Color.blurple(),
        )
        try:
            await target.send(embed=embed)
        except discord.Forbidden:
            pass


@bot.event
async def on_guild_remove(guild):
    print(f'[-] Removed from: {guild.name} ({guild.id})')
    await update_presence()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Missing argument. Try `!setup` for help.')
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send('Invalid argument. Mention a valid user, role, or channel.')
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('You do not have permission to use that command.')
        return
    print(f'[ERROR] {type(error).__name__}: {error}')


async def load_cogs():
    cogs = [
        'cogs.moderation',
        'cogs.admin',
        'cogs.security',
        'cogs.levels',
        'cogs.economy',
        'cogs.welcome',
        'cogs.tickets',
        'cogs.giveaway',
        'cogs.voice',
    ]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f'[COG] Loaded: {cog}')
        except Exception as exc:
            print(f'[COG ERROR] {cog}: {exc}')


async def main():
    if not MAIN_BOT_KEY:
        raise RuntimeError('Missing MAIN_BOT_KEY. Set it in config.py or environment variables.')

    try_load_opus()
    setup_database()
    async with bot:
        await load_cogs()
        await bot.start(MAIN_BOT_KEY)


if __name__ == '__main__':
    asyncio.run(main())

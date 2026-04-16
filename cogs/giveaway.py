import asyncio
import random
import re
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from database import get_connection


def setup_giveaway_table():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaways (
            message_id  TEXT PRIMARY KEY,
            guild_id    TEXT NOT NULL,
            channel_id  TEXT NOT NULL,
            host_id     TEXT NOT NULL,
            prize       TEXT NOT NULL,
            winners     INTEGER NOT NULL,
            ends_at     TEXT NOT NULL,
            ended       INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def parse_time(time_str: str) -> int:
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    match = re.fullmatch(r'(\d+)([smhd])', time_str.lower())
    if not match:
        return 0
    amount, unit = int(match.group(1)), match.group(2)
    return amount * units[unit]


def save_giveaway(message_id: int, guild_id: int, channel_id: int, host_id: int, prize: str, winners: int, ends_at: datetime):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO giveaways (message_id, guild_id, channel_id, host_id, prize, winners, ends_at, ended)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (str(message_id), str(guild_id), str(channel_id), str(host_id), prize, winners, ends_at.isoformat()),
    )
    conn.commit()
    conn.close()


def mark_giveaway_ended(message_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (str(message_id),))
    conn.commit()
    conn.close()


def get_active_giveaways() -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM giveaways WHERE ended = 0")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        setup_giveaway_table()
        self.active: dict[int, dict] = {}

    async def cog_load(self):
        self.bot.loop.create_task(self.restore_giveaways())

    async def restore_giveaways(self):
        await self.bot.wait_until_ready()
        for giveaway in get_active_giveaways():
            message_id = int(giveaway['message_id'])
            ends_at = datetime.fromisoformat(giveaway['ends_at'])
            self.active[message_id] = {
                'prize': giveaway['prize'],
                'winners': int(giveaway['winners']),
                'channel': int(giveaway['channel_id']),
                'host': int(giveaway['host_id']),
                'ends_at': ends_at,
            }
            self.bot.loop.create_task(self.wait_and_end(message_id, ends_at))

    async def wait_and_end(self, message_id: int, ends_at: datetime):
        delay = max(0, (ends_at - datetime.now()).total_seconds())
        await asyncio.sleep(delay)
        info = self.active.get(message_id)
        if not info:
            return
        channel = self.bot.get_channel(info['channel'])
        if channel:
            await self._end_giveaway(channel, message_id)

    @commands.command()
    async def giveaway(self, ctx, duration: str = None, winners: int = 1, *, prize: str = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not duration or not prize:
            await ctx.send('Usage: `!giveaway <time> <winners> <prize>`')
            return
        seconds = parse_time(duration)
        if seconds <= 0:
            await ctx.send('Invalid time. Use `30s`, `5m`, `2h`, `1d`.')
            return
        if winners < 1 or winners > 20:
            await ctx.send('Winner count must be between 1 and 20.')
            return

        ends_at = datetime.now() + timedelta(seconds=seconds)
        embed = discord.Embed(title='Giveaway', color=discord.Color.gold())
        embed.description = (
            f'**Prize:** {prize}\n'
            f'**Winners:** {winners}\n'
            f'**Ends:** <t:{int(ends_at.timestamp())}:R>\n\n'
            'React with ?? to enter!'
        )
        embed.set_footer(text=f'Hosted by {ctx.author.display_name}')

        msg = await ctx.send(embed=embed)
        await msg.add_reaction('??')

        info = {
            'prize': prize,
            'winners': winners,
            'channel': ctx.channel.id,
            'host': ctx.author.id,
            'ends_at': ends_at,
        }
        self.active[msg.id] = info
        save_giveaway(msg.id, ctx.guild.id, ctx.channel.id, ctx.author.id, prize, winners, ends_at)
        await ctx.send(f'Giveaway started with message ID `{msg.id}`.', delete_after=6)
        self.bot.loop.create_task(self.wait_and_end(msg.id, ends_at))

    async def _pick_winners(self, message: discord.Message, winners: int) -> list[discord.User]:
        reaction = discord.utils.get(message.reactions, emoji='??')
        if not reaction:
            return []
        users = [user async for user in reaction.users() if not user.bot]
        if not users:
            return []
        count = min(winners, len(users))
        return random.sample(users, count)

    async def _end_giveaway(self, channel: discord.abc.Messageable, message_id: int):
        info = self.active.pop(message_id, None)
        if not info:
            return
        mark_giveaway_ended(message_id)

        try:
            message = await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden):
            return

        winners = await self._pick_winners(message, info['winners'])
        if not winners:
            await channel.send(f'No valid entries for giveaway `{message_id}`.')
            return

        winner_mentions = ', '.join(winner.mention for winner in winners)
        embed = discord.Embed(title='Giveaway Ended', color=discord.Color.green())
        embed.description = f"**Prize:** {info['prize']}\n**Winner(s):** {winner_mentions}"
        await channel.send(embed=embed)
        await channel.send(f'Congratulations {winner_mentions}! You won **{info["prize"]}**!')

    @commands.command()
    async def endgiveaway(self, ctx, message_id: int = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not message_id or message_id not in self.active:
            await ctx.send('No active giveaway with that ID.')
            return
        await self._end_giveaway(ctx.channel, message_id)

    @commands.command()
    async def reroll(self, ctx, message_id: int = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not message_id:
            await ctx.send('Usage: `!reroll <message_id>`')
            return
        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send('Message not found.')
            return
        winners = await self._pick_winners(message, 1)
        if not winners:
            await ctx.send('No valid users to reroll.')
            return
        await ctx.send(f'New winner: {winners[0].mention}! Congratulations!')


async def setup(bot):
    await bot.add_cog(Giveaway(bot))

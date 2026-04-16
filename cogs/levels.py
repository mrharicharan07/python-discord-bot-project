import random
import time

import discord
from discord.ext import commands

from database import get_connection


XP_COOLDOWN_SECONDS = 45


def setup_levels_table():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS levels (
            guild_id  TEXT NOT NULL,
            user_id   TEXT NOT NULL,
            xp        INTEGER DEFAULT 0,
            level     INTEGER DEFAULT 0,
            messages  INTEGER DEFAULT 0,
            UNIQUE(guild_id, user_id)
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS level_rewards (
            guild_id  TEXT NOT NULL,
            level     INTEGER NOT NULL,
            role_id   TEXT NOT NULL,
            UNIQUE(guild_id, level)
        )
        """
    )
    c.execute("PRAGMA table_info(levels)")
    existing = {row['name'] for row in c.fetchall()}
    if 'messages' not in existing:
        c.execute("ALTER TABLE levels ADD COLUMN messages INTEGER DEFAULT 0")
    conn.commit()
    conn.close()


def xp_needed(level: int) -> int:
    return 100 + (level * 60)


def get_user_level(guild_id: str, user_id: str) -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT xp, level, messages FROM levels WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {'xp': row['xp'], 'level': row['level'], 'messages': row['messages']}
    return {'xp': 0, 'level': 0, 'messages': 0}


def add_xp(guild_id: str, user_id: str, amount: int) -> tuple[int, bool]:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO levels (guild_id, user_id, xp, level, messages) VALUES (?, ?, ?, 0, 1)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = xp + ?, messages = messages + 1
        """,
        (guild_id, user_id, amount, amount),
    )
    conn.commit()
    c.execute("SELECT xp, level FROM levels WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = c.fetchone()
    xp, level = row['xp'], row['level']
    leveled_up = False
    while xp >= xp_needed(level):
        xp -= xp_needed(level)
        level += 1
        leveled_up = True
    c.execute("UPDATE levels SET xp=?, level=? WHERE guild_id=? AND user_id=?", (xp, level, guild_id, user_id))
    conn.commit()
    conn.close()
    return level, leveled_up


def get_leaderboard(guild_id: str, limit: int = 10) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, xp, level, messages FROM levels
        WHERE guild_id=?
        ORDER BY level DESC, xp DESC, messages DESC
        LIMIT ?
        """,
        (guild_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def set_level_reward(guild_id: str, level: int, role_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO level_rewards (guild_id, level, role_id) VALUES (?, ?, ?)",
        (guild_id, level, role_id),
    )
    conn.commit()
    conn.close()


def remove_level_reward(guild_id: str, level: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM level_rewards WHERE guild_id=? AND level=?", (guild_id, level))
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_level_rewards(guild_id: str) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT level, role_id FROM level_rewards WHERE guild_id=? ORDER BY level ASC", (guild_id,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        setup_levels_table()
        self._xp_cooldown: dict[str, float] = {}

    async def apply_level_rewards(self, member: discord.Member, level: int):
        rewards = get_level_rewards(str(member.guild.id))
        for reward in rewards:
            if level >= int(reward['level']):
                role = member.guild.get_role(int(reward['role_id']))
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f'Level reward for level {level}')
                    except discord.Forbidden:
                        pass

    @commands.Cog.listener('on_message')
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if len(message.content.strip()) < 3:
            return
        gid = str(message.guild.id)
        uid = str(message.author.id)
        key = f'{gid}:{uid}'
        now = time.time()
        last = self._xp_cooldown.get(key, 0)
        if now - last < XP_COOLDOWN_SECONDS:
            return
        self._xp_cooldown[key] = now
        xp_gain = random.randint(8, 18)
        new_level, leveled_up = add_xp(gid, uid, xp_gain)
        if leveled_up:
            await self.apply_level_rewards(message.author, new_level)
            await message.channel.send(f'{message.author.mention} leveled up to **Level {new_level}**!')

    @commands.command()
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        data = get_user_level(str(ctx.guild.id), str(member.id))
        level = data['level']
        xp = data['xp']
        messages = data['messages']
        needed = xp_needed(level)
        filled = max(0, min(20, int((xp / needed) * 20))) if needed else 0
        bar = '#' * filled + '-' * (20 - filled)
        embed = discord.Embed(title=f"{member.display_name}'s Rank", color=discord.Color.blurple())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name='Level', value=str(level), inline=True)
        embed.add_field(name='XP', value=f'{xp}/{needed}', inline=True)
        embed.add_field(name='Messages', value=str(messages), inline=True)
        embed.add_field(name='Progress', value=f'`{bar}`', inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def leaderboard(self, ctx):
        rows = get_leaderboard(str(ctx.guild.id))
        if not rows:
            await ctx.send('No XP data yet. Start chatting!')
            return
        medals = ['[1]', '[2]', '[3]']
        lines = []
        for i, row in enumerate(rows):
            member = ctx.guild.get_member(int(row['user_id']))
            name = member.display_name if member else f"<@{row['user_id']}>"
            prefix = medals[i] if i < 3 else f'`{i+1}.`'
            lines.append(f"{prefix} **{name}** - Level {row['level']} | XP {row['xp']} | Msgs {row['messages']}")
        embed = discord.Embed(title=f'Leaderboard - {ctx.guild.name}', description='\n'.join(lines), color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setlevelrole(self, ctx, level: int = None, role: discord.Role = None):
        if level is None or level < 1 or role is None:
            await ctx.send('Usage: `!setlevelrole <level> @role`')
            return
        set_level_reward(str(ctx.guild.id), level, str(role.id))
        await ctx.send(f'Level reward saved: level **{level}** -> {role.mention}')

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def removelevelrole(self, ctx, level: int = None):
        if level is None or level < 1:
            await ctx.send('Usage: `!removelevelrole <level>`')
            return
        if remove_level_reward(str(ctx.guild.id), level):
            await ctx.send(f'Level reward removed for level **{level}**.')
        else:
            await ctx.send('No level reward was configured for that level.')

    @commands.command()
    async def levelrewards(self, ctx):
        rewards = get_level_rewards(str(ctx.guild.id))
        if not rewards:
            await ctx.send('No level rewards configured yet.')
            return
        lines = []
        for reward in rewards:
            role = ctx.guild.get_role(int(reward['role_id']))
            role_text = role.mention if role else f'<@&{reward["role_id"]}>'
            lines.append(f"Level **{reward['level']}** -> {role_text}")
        embed = discord.Embed(title=f'Level Rewards - {ctx.guild.name}', description='\n'.join(lines), color=discord.Color.blurple())
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Levels(bot))

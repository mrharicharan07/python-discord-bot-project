import random
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from database import get_connection


DEFAULT_SHOP_ITEMS = {
    'vip': {'price': 2000, 'description': 'Premium flex item for your inventory.'},
    'lootbox': {'price': 750, 'description': 'Mystery box for bragging rights.'},
    'shield': {'price': 1200, 'description': 'Defense item for future features.'},
    'booster': {'price': 1500, 'description': 'XP booster item for future upgrades.'},
}


def setup_economy_table():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS economy (
            guild_id     TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            coins        INTEGER DEFAULT 0,
            last_daily   TEXT DEFAULT NULL,
            last_work    TEXT DEFAULT NULL,
            last_beg     TEXT DEFAULT NULL,
            daily_streak INTEGER DEFAULT 0,
            UNIQUE(guild_id, user_id)
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS economy_inventory (
            guild_id    TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            item_name   TEXT NOT NULL,
            quantity    INTEGER DEFAULT 0,
            UNIQUE(guild_id, user_id, item_name)
        )
        """
    )
    c.execute("PRAGMA table_info(economy)")
    existing = {row['name'] for row in c.fetchall()}
    for name, definition in {
        'last_work': 'TEXT DEFAULT NULL',
        'last_beg': 'TEXT DEFAULT NULL',
        'daily_streak': 'INTEGER DEFAULT 0',
    }.items():
        if name not in existing:
            c.execute(f"ALTER TABLE economy ADD COLUMN {name} {definition}")
    conn.commit()
    conn.close()


def ensure_economy_user(guild_id: str, user_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO economy (guild_id, user_id, coins, daily_streak) VALUES (?, ?, 0, 0)", (guild_id, user_id))
    conn.commit()
    conn.close()


def get_balance(guild_id: str, user_id: str) -> int:
    ensure_economy_user(guild_id, user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT coins FROM economy WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = c.fetchone()
    conn.close()
    return row['coins'] if row else 0


def get_profile(guild_id: str, user_id: str) -> dict:
    ensure_economy_user(guild_id, user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT coins, last_daily, last_work, last_beg, daily_streak FROM economy WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else {'coins': 0, 'last_daily': None, 'last_work': None, 'last_beg': None, 'daily_streak': 0}


def add_coins(guild_id: str, user_id: str, amount: int):
    ensure_economy_user(guild_id, user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE economy SET coins = coins + ? WHERE guild_id=? AND user_id=?", (amount, guild_id, user_id))
    conn.commit()
    conn.close()


def remove_coins(guild_id: str, user_id: str, amount: int) -> bool:
    balance = get_balance(guild_id, user_id)
    if balance < amount:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE economy SET coins = coins - ? WHERE guild_id=? AND user_id=?", (amount, guild_id, user_id))
    conn.commit()
    conn.close()
    return True


def add_item(guild_id: str, user_id: str, item_name: str, quantity: int = 1):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO economy_inventory (guild_id, user_id, item_name, quantity) VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id, item_name) DO UPDATE SET quantity = quantity + ?
        """,
        (guild_id, user_id, item_name, quantity, quantity),
    )
    conn.commit()
    conn.close()


def get_inventory(guild_id: str, user_id: str) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT item_name, quantity FROM economy_inventory WHERE guild_id=? AND user_id=? ORDER BY item_name ASC", (guild_id, user_id))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def _cooldown_ready(last_value: str | None, hours: float) -> tuple[bool, int]:
    if not last_value:
        return True, 0
    last = datetime.fromisoformat(last_value)
    diff = datetime.now() - last
    cooldown = timedelta(hours=hours)
    if diff >= cooldown:
        return True, 0
    left = cooldown - diff
    return False, max(1, int(left.total_seconds() // 60))


def can_claim_daily(guild_id: str, user_id: str) -> tuple[bool, int]:
    profile = get_profile(guild_id, user_id)
    return _cooldown_ready(profile.get('last_daily'), 24)


def claim_daily(guild_id: str, user_id: str, amount: int):
    profile = get_profile(guild_id, user_id)
    now = datetime.now()
    streak = int(profile.get('daily_streak', 0) or 0)
    last_daily = profile.get('last_daily')
    if last_daily:
        previous = datetime.fromisoformat(last_daily)
        if now - previous <= timedelta(hours=48):
            streak += 1
        else:
            streak = 1
    else:
        streak = 1
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE economy SET coins = coins + ?, last_daily = ?, daily_streak = ? WHERE guild_id=? AND user_id=?", (amount, now.isoformat(), streak, guild_id, user_id))
    conn.commit()
    conn.close()
    return streak


def update_action_time(guild_id: str, user_id: str, field: str):
    ensure_economy_user(guild_id, user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE economy SET {field} = ? WHERE guild_id=? AND user_id=?", (datetime.now().isoformat(), guild_id, user_id))
    conn.commit()
    conn.close()


def get_rich_list(guild_id: str, limit: int = 10) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, coins, daily_streak FROM economy WHERE guild_id=? ORDER BY coins DESC LIMIT ?", (guild_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        setup_economy_table()

    @commands.command()
    async def balance(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        profile = get_profile(str(ctx.guild.id), str(member.id))
        embed = discord.Embed(title=f"{member.display_name}'s Balance", color=discord.Color.gold())
        embed.add_field(name='Coins', value=f"{profile['coins']:,}", inline=True)
        embed.add_field(name='Daily streak', value=str(profile.get('daily_streak', 0)), inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    async def daily(self, ctx):
        gid = str(ctx.guild.id)
        uid = str(ctx.author.id)
        can_claim, minutes_left = can_claim_daily(gid, uid)
        if not can_claim:
            await ctx.send(f'{ctx.author.mention} already claimed daily. Come back in **{minutes_left} min**.')
            return
        streak_bonus = min(100, get_profile(gid, uid).get('daily_streak', 0) * 10)
        amount = random.randint(150, 300) + streak_bonus
        streak = claim_daily(gid, uid, amount)
        balance = get_balance(gid, uid)
        await ctx.send(f'{ctx.author.mention} claimed **{amount} coins**. Streak: **{streak}**. Balance: **{balance:,}**')

    @commands.command()
    async def work(self, ctx):
        gid = str(ctx.guild.id)
        uid = str(ctx.author.id)
        profile = get_profile(gid, uid)
        ready, minutes_left = _cooldown_ready(profile.get('last_work'), 1)
        if not ready:
            await ctx.send(f'{ctx.author.mention} you are tired. Work again in **{minutes_left} min**.')
            return
        amount = random.randint(80, 220)
        add_coins(gid, uid, amount)
        update_action_time(gid, uid, 'last_work')
        await ctx.send(f'{ctx.author.mention} worked hard and earned **{amount} coins**.')

    @commands.command()
    async def beg(self, ctx):
        gid = str(ctx.guild.id)
        uid = str(ctx.author.id)
        profile = get_profile(gid, uid)
        ready, minutes_left = _cooldown_ready(profile.get('last_beg'), 0.5)
        if not ready:
            await ctx.send(f'{ctx.author.mention} nobody is listening yet. Try again in **{minutes_left} min**.')
            return
        amount = random.randint(20, 90)
        add_coins(gid, uid, amount)
        update_action_time(gid, uid, 'last_beg')
        await ctx.send(f'{ctx.author.mention} begged successfully and received **{amount} coins**.')

    @commands.command()
    async def give(self, ctx, member: discord.Member = None, amount: int = 0):
        if not member or amount <= 0:
            await ctx.send('Usage: `!give @user <amount>`')
            return
        if member.id == ctx.author.id:
            await ctx.send("You can't give coins to yourself.")
            return
        gid = str(ctx.guild.id)
        uid = str(ctx.author.id)
        tid = str(member.id)
        if not remove_coins(gid, uid, amount):
            await ctx.send(f'Not enough coins. You have **{get_balance(gid, uid):,}**.')
            return
        add_coins(gid, tid, amount)
        await ctx.send(f'{ctx.author.mention} gave **{amount:,} coins** to {member.mention}.')

    @commands.command()
    async def shop(self, ctx):
        lines = []
        for name, info in DEFAULT_SHOP_ITEMS.items():
            lines.append(f"**{name}** - {info['price']} coins | {info['description']}")
        embed = discord.Embed(title=f'Shop - {ctx.guild.name}', description='\n'.join(lines), color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.command()
    async def buy(self, ctx, item_name: str = None, quantity: int = 1):
        if not item_name:
            await ctx.send('Usage: `!buy <item_name> [quantity]`')
            return
        item_key = item_name.lower().strip()
        item = DEFAULT_SHOP_ITEMS.get(item_key)
        if not item:
            await ctx.send('That item does not exist. Use `!shop`.')
            return
        if quantity < 1 or quantity > 50:
            await ctx.send('Quantity must be between 1 and 50.')
            return
        total_cost = item['price'] * quantity
        gid = str(ctx.guild.id)
        uid = str(ctx.author.id)
        if not remove_coins(gid, uid, total_cost):
            await ctx.send(f'Not enough coins. You need **{total_cost:,}** coins.')
            return
        add_item(gid, uid, item_key, quantity)
        await ctx.send(f'{ctx.author.mention} bought **{quantity}x {item_key}** for **{total_cost:,} coins**.')

    @commands.command()
    async def inventory(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        rows = get_inventory(str(ctx.guild.id), str(member.id))
        if not rows:
            await ctx.send(f'{member.mention} has no items yet.')
            return
        lines = [f"**{row['item_name']}** x{row['quantity']}" for row in rows]
        embed = discord.Embed(title=f"{member.display_name}'s Inventory", description='\n'.join(lines), color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.command()
    async def rich(self, ctx):
        rows = get_rich_list(str(ctx.guild.id))
        if not rows:
            await ctx.send('No economy data yet. Use `!daily` to start!')
            return
        medals = ['[1]', '[2]', '[3]']
        lines = []
        for i, row in enumerate(rows):
            member = ctx.guild.get_member(int(row['user_id']))
            name = member.display_name if member else f"<@{row['user_id']}>"
            prefix = medals[i] if i < 3 else f'`{i+1}.`'
            lines.append(f"{prefix} **{name}** - {row['coins']:,} coins | streak {row['daily_streak']}")
        embed = discord.Embed(title=f'Richest Users - {ctx.guild.name}', description='\n'.join(lines), color=discord.Color.gold())
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Economy(bot))

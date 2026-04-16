import asyncio
from datetime import datetime

import discord
from discord.ext import commands

from database import get_connection


def setup_tickets_table():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            guild_id        TEXT NOT NULL,
            user_id         TEXT NOT NULL,
            channel_id      TEXT NOT NULL,
            support_role_id TEXT,
            UNIQUE(guild_id, user_id)
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_settings (
            guild_id         TEXT PRIMARY KEY,
            category_id      TEXT,
            log_channel_id   TEXT,
            support_role_id  TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def get_ticket(guild_id: str, user_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = c.fetchone()
    conn.close()
    return row['channel_id'] if row else None


def get_ticket_owner_by_channel(channel_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT guild_id, user_id FROM tickets WHERE channel_id=?", (channel_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def save_ticket(guild_id: str, user_id: str, channel_id: str, support_role_id: str | None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO tickets (guild_id, user_id, channel_id, support_role_id) VALUES (?, ?, ?, ?)", (guild_id, user_id, channel_id, support_role_id))
    conn.commit()
    conn.close()


def delete_ticket_by_channel(channel_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM tickets WHERE channel_id=?", (channel_id,))
    conn.commit()
    conn.close()


def get_ticket_settings(guild_id: str) -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM ticket_settings WHERE guild_id=?", (guild_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {'guild_id': guild_id, 'category_id': None, 'log_channel_id': None, 'support_role_id': None}


def set_ticket_setting(guild_id: str, field: str, value: str | None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO ticket_settings (guild_id) VALUES (?)", (guild_id,))
    c.execute(f"UPDATE ticket_settings SET {field} = ? WHERE guild_id = ?", (value, guild_id))
    conn.commit()
    conn.close()


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        setup_tickets_table()

    async def send_ticket_log(self, guild: discord.Guild, text: str):
        settings = get_ticket_settings(str(guild.id))
        channel_id = settings.get('log_channel_id')
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(text[:1900])
            except discord.Forbidden:
                pass

    async def build_transcript(self, channel: discord.TextChannel) -> str:
        lines = [f'Transcript for #{channel.name}', '-' * 40]
        async for message in channel.history(limit=None, oldest_first=True):
            timestamp = message.created_at.strftime('%Y-%m-%d %H:%M:%S')
            content = message.content or '[embed/attachment only]'
            lines.append(f'[{timestamp}] {message.author}: {content}')
        return '\n'.join(lines)

    @commands.command()
    async def setticketcategory(self, ctx, category: discord.CategoryChannel | None = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not category:
            await ctx.send('Usage: `!setticketcategory <category>`')
            return
        set_ticket_setting(str(ctx.guild.id), 'category_id', str(category.id))
        await ctx.send(f'Ticket category set to **{category.name}**.')

    @commands.command()
    async def setticketlog(self, ctx, channel: discord.TextChannel | None = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not channel:
            await ctx.send('Usage: `!setticketlog #channel`')
            return
        set_ticket_setting(str(ctx.guild.id), 'log_channel_id', str(channel.id))
        await ctx.send(f'Ticket log channel set to {channel.mention}.')

    @commands.command()
    async def setsupportrole(self, ctx, role: discord.Role | None = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not role:
            await ctx.send('Usage: `!setsupportrole @role`')
            return
        set_ticket_setting(str(ctx.guild.id), 'support_role_id', str(role.id))
        await ctx.send(f'Support role set to {role.mention}.')

    @commands.command()
    async def ticketsetup(self, ctx):
        settings = get_ticket_settings(str(ctx.guild.id))
        embed = discord.Embed(title=f'Ticket Setup - {ctx.guild.name}', color=discord.Color.blue())
        embed.add_field(name='Category', value=f"<#{settings['category_id']}>" if settings.get('category_id') else 'Not set', inline=False)
        embed.add_field(name='Log channel', value=f"<#{settings['log_channel_id']}>" if settings.get('log_channel_id') else 'Not set', inline=False)
        embed.add_field(name='Support role', value=f"<@&{settings['support_role_id']}>" if settings.get('support_role_id') else 'Not set', inline=False)
        embed.add_field(name='Commands', value='`!ticket` `!closeticket [reason]` `!setticketcategory` `!setticketlog` `!setsupportrole`', inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def ticket(self, ctx):
        gid = str(ctx.guild.id)
        uid = str(ctx.author.id)
        existing = get_ticket(gid, uid)
        if existing:
            channel = ctx.guild.get_channel(int(existing))
            if channel:
                await ctx.send(f'You already have a ticket open: {channel.mention}')
                return
            delete_ticket_by_channel(existing)

        settings = get_ticket_settings(gid)
        category = ctx.guild.get_channel(int(settings['category_id'])) if settings.get('category_id') else None
        support_role = ctx.guild.get_role(int(settings['support_role_id'])) if settings.get('support_role_id') else None
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            ctx.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        else:
            for role in ctx.guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel_name = f"ticket-{ctx.author.name[:18].lower().replace(' ', '-')}-{ctx.author.discriminator}"
        try:
            ticket_channel = await ctx.guild.create_text_channel(channel_name, category=category, overwrites=overwrites, reason=f'Ticket opened by {ctx.author}')
        except discord.Forbidden:
            await ctx.send('Bot needs Manage Channels permission.')
            return

        save_ticket(gid, uid, str(ticket_channel.id), settings.get('support_role_id'))
        embed = discord.Embed(title='Support Ticket', color=discord.Color.blue())
        embed.description = (
            f'Hey {ctx.author.mention}, support is here.\n\n'
            'Describe your issue and a staff member will help you.\n'
            'Use `!closeticket <reason>` when done.'
        )
        if support_role:
            await ticket_channel.send(content=support_role.mention, embed=embed)
        else:
            await ticket_channel.send(embed=embed)
        await ctx.send(f'Ticket created: {ticket_channel.mention}')
        await self.send_ticket_log(ctx.guild, f'[TICKET OPEN] user={ctx.author} channel={ticket_channel.mention}')

    @commands.command()
    async def closeticket(self, ctx, *, reason: str = 'No reason provided'):
        if not ctx.channel.name.startswith('ticket-'):
            existing = get_ticket(str(ctx.guild.id), str(ctx.author.id))
            if not existing:
                await ctx.send("You don't have an open ticket.")
                return
            channel = ctx.guild.get_channel(int(existing))
            if not channel:
                delete_ticket_by_channel(existing)
                await ctx.send('Stale ticket record removed.')
                return
            await ctx.send(f'Use `{channel.mention}` and run `!closeticket <reason>` there.')
            return

        transcript = await self.build_transcript(ctx.channel)
        owner = get_ticket_owner_by_channel(str(ctx.channel.id))
        delete_ticket_by_channel(str(ctx.channel.id))
        await self.send_ticket_log(
            ctx.guild,
            f'[TICKET CLOSE] channel=#{ctx.channel.name} closed_by={ctx.author} reason={reason}\n```\n{transcript[:1500]}\n```'
        )
        await ctx.send(f'Closing ticket in 3 seconds. Reason: {reason}')
        await asyncio.sleep(3)
        try:
            await ctx.channel.delete(reason=f'Ticket closed by {ctx.author} | {reason}')
        except discord.Forbidden:
            await ctx.send('Bot needs Manage Channels permission.')


async def setup(bot):
    await bot.add_cog(Tickets(bot))

import discord
from discord.ext import commands

from config import BOT_OWNER_ID
from database import (
    add_custom_word,
    add_whitelist,
    ensure_guild,
    get_connection,
    get_custom_words,
    get_guild_config,
    get_warnings,
    get_whitelist,
    remove_custom_word,
    remove_whitelist,
    reset_warnings,
    set_ai_replies_enabled,
    set_anti_link_enabled,
    set_anti_nuke_enabled,
    set_anti_raid_enabled,
    set_automod_enabled,
    set_channel_create_limit,
    set_role_create_limit,
    set_log_channel,
    set_max_warnings,
    set_mute_minutes,
    set_nuke_limit,
    set_prefix,
    set_raid_limit,
    set_raid_window_seconds,
    set_security_logs_enabled,
    set_warn_threshold,
)


def setup_lockdown_table():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS lockdown_overrides (
            guild_id    TEXT NOT NULL,
            channel_id  TEXT NOT NULL,
            target_id   TEXT NOT NULL,
            target_type TEXT NOT NULL,
            old_view    TEXT,
            old_send    TEXT,
            old_connect TEXT,
            PRIMARY KEY (guild_id, channel_id, target_id, target_type)
        )
        """
    )
    c.execute('PRAGMA table_info(lockdown_overrides)')
    existing = {row['name'] for row in c.fetchall()}
    needed = {'guild_id', 'channel_id', 'target_id', 'target_type', 'old_view', 'old_send', 'old_connect'}
    if existing and not needed.issubset(existing):
        c.execute('DROP TABLE lockdown_overrides')
        c.execute(
            """
            CREATE TABLE lockdown_overrides (
                guild_id    TEXT NOT NULL,
                channel_id  TEXT NOT NULL,
                target_id   TEXT NOT NULL,
                target_type TEXT NOT NULL,
                old_view    TEXT,
                old_send    TEXT,
                old_connect TEXT,
                PRIMARY KEY (guild_id, channel_id, target_id, target_type)
            )
            """
        )
    conn.commit()
    conn.close()


def encode_perm(value):
    if value is None:
        return 'none'
    return 'true' if value else 'false'


def decode_perm(value):
    if value == 'true':
        return True
    if value == 'false':
        return False
    return None


def save_lockdown_override(guild_id: str, channel_id: str, target_id: str, target_type: str, old_view, old_send, old_connect):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO lockdown_overrides (guild_id, channel_id, target_id, target_type, old_view, old_send, old_connect)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (guild_id, channel_id, target_id, target_type, encode_perm(old_view), encode_perm(old_send), encode_perm(old_connect)),
    )
    conn.commit()
    conn.close()


def get_lockdown_overrides(guild_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM lockdown_overrides WHERE guild_id = ?', (guild_id,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def clear_lockdown_overrides(guild_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM lockdown_overrides WHERE guild_id = ?', (guild_id,))
    conn.commit()
    conn.close()


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        setup_lockdown_table()

    def is_admin(self, member: discord.Member) -> bool:
        return member.guild_permissions.administrator or member.id == BOT_OWNER_ID

    def can_run_lockdown(self, member: discord.Member) -> bool:
        return (
            member.id == BOT_OWNER_ID
            or member.id == member.guild.owner_id
            or member.guild_permissions.administrator
        )

    async def emergency_lock_channel(self, guild: discord.Guild, channel: discord.abc.GuildChannel) -> int:
        changed = 0
        targets = [guild.default_role] + [role for role in guild.roles if role != guild.default_role and not role.permissions.administrator]
        for role in targets:
            try:
                overwrite = channel.overwrites_for(role)
                save_lockdown_override(str(guild.id), str(channel.id), str(role.id), 'role', overwrite.view_channel, overwrite.send_messages, overwrite.connect)
                await channel.set_permissions(role, view_channel=False, send_messages=False, connect=False)
                changed += 1
            except discord.Forbidden:
                pass
            except Exception:
                pass
        for target, overwrite in channel.overwrites.items():
            if not isinstance(target, discord.Member):
                continue
            if target.guild_permissions.administrator:
                continue
            try:
                save_lockdown_override(str(guild.id), str(channel.id), str(target.id), 'member', overwrite.view_channel, overwrite.send_messages, overwrite.connect)
                await channel.set_permissions(target, view_channel=False, send_messages=False, connect=False)
                changed += 1
            except discord.Forbidden:
                pass
            except Exception:
                pass
        return changed

    async def emergency_unlock_fallback(self, guild: discord.Guild) -> int:
        changed = 0
        targets = [guild.default_role] + [role for role in guild.roles if role != guild.default_role and not role.permissions.administrator]
        for channel in guild.channels:
            for role in targets:
                try:
                    await channel.set_permissions(role, view_channel=None, send_messages=None, connect=None)
                    changed += 1
                except discord.Forbidden:
                    pass
                except Exception:
                    pass
            for target, _overwrite in channel.overwrites.items():
                if not isinstance(target, discord.Member):
                    continue
                if target.guild_permissions.administrator:
                    continue
                try:
                    await channel.set_permissions(target, view_channel=None, send_messages=None, connect=None)
                    changed += 1
                except discord.Forbidden:
                    pass
                except Exception:
                    pass
        return changed

    @commands.command()
    async def ping(self, ctx):
        await ctx.send(f"Pong. Latency: `{round(self.bot.latency * 1000)}ms`")

    @commands.command()
    async def help(self, ctx):
        embed = discord.Embed(title='Zoro Command Center', description='Main controls for setup, security, moderation, and community systems.', color=discord.Color.blurple())
        embed.add_field(name='Setup', value='`!setup` `!status` `!setlog` `!setprefixcmd`', inline=False)
        embed.add_field(name='Moderation', value='`!automod` `!sensitivity` `!setmute` `!setmaxwarn` `!warnings` `!clearwarn`', inline=False)
        embed.add_field(name='Security', value='`!securitystatus` `!antiraid` `!antinuke` `!antilink` `!raidlimit` `!raidwindow` `!nukelimit` `!panic` `!unlock`', inline=False)
        embed.add_field(name='Utility', value='`!serverinfo` `!userinfo` `!avatar` `!botstats` `!purge` `!slowmode` `!announce`', inline=False)
        embed.add_field(name='Community', value='`!rank` `!leaderboard` `!balance` `!daily` `!work` `!beg` `!ticket` `!giveaway`', inline=False)
        embed.add_field(name='Setup panels', value='`!ticketsetup` `!welcomesetup` `!securitystatus`', inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def status(self, ctx):
        gid = str(ctx.guild.id)
        config = get_guild_config(gid)
        whitelist = get_whitelist(gid)
        words = get_custom_words(gid)

        log_channel = 'Not set'
        if config.get('log_channel_id'):
            channel = ctx.guild.get_channel(int(config['log_channel_id']))
            log_channel = channel.mention if channel else 'Deleted channel'

        whitelist_mentions = []
        for user_id in whitelist:
            member = ctx.guild.get_member(int(user_id))
            whitelist_mentions.append(member.mention if member else f'<@{user_id}>')

        embed = discord.Embed(title=f'Zoro Status - {ctx.guild.name}', description='Live server configuration overview.', color=discord.Color.blurple())
        embed.add_field(name='Prefix', value=config['prefix'], inline=True)
        embed.add_field(name='Log channel', value=log_channel, inline=True)
        embed.add_field(name='Automod', value='ON' if config['automod_enabled'] else 'OFF', inline=True)
        embed.add_field(name='AI replies', value='ON' if config['ai_replies'] else 'OFF', inline=True)
        embed.add_field(name='Sensitivity', value=f"{config['warn_threshold']}/100", inline=True)
        embed.add_field(name='Mute', value=f"{config['mute_minutes']} min", inline=True)
        embed.add_field(name='Max warnings', value=str(config['max_warnings']), inline=True)
        embed.add_field(name='Whitelist', value=', '.join(whitelist_mentions) if whitelist_mentions else 'None', inline=False)
        embed.add_field(name='Custom words', value=f"{len(words)} configured", inline=False)
        embed.set_footer(text='Per-server settings only. Nothing here affects your other servers.')
        await ctx.send(embed=embed)

    @commands.command()
    async def securitystatus(self, ctx):
        config = get_guild_config(str(ctx.guild.id))
        embed = discord.Embed(title=f'Security Status - {ctx.guild.name}', description='Protection switches and live thresholds for this server.', color=discord.Color.red())
        embed.add_field(name='Anti raid', value='ON' if config['anti_raid_enabled'] else 'OFF', inline=True)
        embed.add_field(name='Anti nuke', value='ON' if config['anti_nuke_enabled'] else 'OFF', inline=True)
        embed.add_field(name='Anti link', value='ON' if config['anti_link_enabled'] else 'OFF', inline=True)
        embed.add_field(name='Security logs', value='ON' if config['security_logs_enabled'] else 'OFF', inline=True)
        embed.add_field(name='Raid limit', value=f"{config['raid_limit']} joins", inline=True)
        embed.add_field(name='Raid window', value=f"{config['raid_window_seconds']} sec", inline=True)
        embed.add_field(name='Nuke limit', value=f"{config['nuke_limit']} destructive actions", inline=True)
        embed.add_field(name='Channel create limit', value=f"{config['channel_create_limit']} in window", inline=True)
        embed.add_field(name='Role create limit', value=f"{config.get('role_create_limit', 3)} in window", inline=True)
        embed.set_footer(text='Recommendation: keep anti-raid, anti-nuke, and security logs ON for main servers.')
        await ctx.send(embed=embed)

    @commands.command()
    async def setlog(self, ctx, channel: discord.TextChannel | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if not channel:
            await ctx.send('Usage: `!setlog #channel`')
            return
        set_log_channel(str(ctx.guild.id), str(channel.id))
        await ctx.send(f'Log channel set to {channel.mention}.')

    @commands.command()
    async def setprefixcmd(self, ctx, prefix: str | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if not prefix or len(prefix) > 5:
            await ctx.send('Usage: `!setprefixcmd <prefix>` and keep it under 5 characters.')
            return
        set_prefix(str(ctx.guild.id), prefix)
        await ctx.send(f'Prefix changed to `{prefix}` for this server.')

    @commands.command()
    async def sensitivity(self, ctx, level: int | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if level is None or not (20 <= level <= 100):
            await ctx.send('Usage: `!sensitivity <20-100>`')
            return
        set_warn_threshold(str(ctx.guild.id), level)
        await ctx.send(f'Moderation threshold set to {level}/100.')

    @commands.command()
    async def setmute(self, ctx, minutes: int | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if minutes is None or not (1 <= minutes <= 1440):
            await ctx.send('Usage: `!setmute <1-1440>`')
            return
        set_mute_minutes(str(ctx.guild.id), minutes)
        await ctx.send(f'Timeout duration set to {minutes} minute(s).')

    @commands.command()
    async def setmaxwarn(self, ctx, total: int | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if total is None or not (2 <= total <= 10):
            await ctx.send('Usage: `!setmaxwarn <2-10>`')
            return
        set_max_warnings(str(ctx.guild.id), total)
        await ctx.send(f'Max warnings set to {total}.')

    @commands.command()
    async def automod(self, ctx, state: str | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if state not in {'on', 'off'}:
            await ctx.send('Usage: `!automod on` or `!automod off`')
            return
        enabled = state == 'on'
        set_automod_enabled(str(ctx.guild.id), enabled)
        await ctx.send(f"Automod {'enabled' if enabled else 'disabled'} for this server.")

    @commands.command()
    async def aireplies(self, ctx, state: str | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if state not in {'on', 'off'}:
            await ctx.send('Usage: `!aireplies on` or `!aireplies off`')
            return
        enabled = state == 'on'
        set_ai_replies_enabled(str(ctx.guild.id), enabled)
        await ctx.send(f"AI replies {'enabled' if enabled else 'disabled'} for this server.")

    @commands.command()
    async def antiraid(self, ctx, state: str | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if state not in {'on', 'off'}:
            await ctx.send('Usage: `!antiraid on` or `!antiraid off`')
            return
        enabled = state == 'on'
        set_anti_raid_enabled(str(ctx.guild.id), enabled)
        await ctx.send(f"Anti-raid {'enabled' if enabled else 'disabled'} for this server.")

    @commands.command()
    async def antinuke(self, ctx, state: str | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if state not in {'on', 'off'}:
            await ctx.send('Usage: `!antinuke on` or `!antinuke off`')
            return
        enabled = state == 'on'
        set_anti_nuke_enabled(str(ctx.guild.id), enabled)
        await ctx.send(f"Anti-nuke {'enabled' if enabled else 'disabled'} for this server.")

    @commands.command()
    async def antilink(self, ctx, state: str | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if state not in {'on', 'off'}:
            await ctx.send('Usage: `!antilink on` or `!antilink off`')
            return
        enabled = state == 'on'
        set_anti_link_enabled(str(ctx.guild.id), enabled)
        await ctx.send(f"Anti-link {'enabled' if enabled else 'disabled'} for this server.")

    @commands.command()
    async def securitylogs(self, ctx, state: str | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if state not in {'on', 'off'}:
            await ctx.send('Usage: `!securitylogs on` or `!securitylogs off`')
            return
        enabled = state == 'on'
        set_security_logs_enabled(str(ctx.guild.id), enabled)
        await ctx.send(f"Security logs {'enabled' if enabled else 'disabled'} for this server.")

    @commands.command()
    async def raidlimit(self, ctx, total: int | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if total is None or not (2 <= total <= 50):
            await ctx.send('Usage: `!raidlimit <2-50>`')
            return
        set_raid_limit(str(ctx.guild.id), total)
        await ctx.send(f'Raid limit set to {total} joins in the configured window.')

    @commands.command()
    async def raidwindow(self, ctx, seconds: int | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if seconds is None or not (3 <= seconds <= 120):
            await ctx.send('Usage: `!raidwindow <3-120>`')
            return
        set_raid_window_seconds(str(ctx.guild.id), seconds)
        await ctx.send(f'Raid time window set to {seconds} second(s).')

    @commands.command()
    async def nukelimit(self, ctx, total: int | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if total is None or not (2 <= total <= 20):
            await ctx.send('Usage: `!nukelimit <2-20>`')
            return
        set_nuke_limit(str(ctx.guild.id), total)
        await ctx.send(f'Nuke limit set to {total} destructive actions in the window.')

    @commands.command()
    async def createlimit(self, ctx, total: int | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if total is None or not (2 <= total <= 30):
            await ctx.send('Usage: `!createlimit <2-30>`')
            return
        set_channel_create_limit(str(ctx.guild.id), total)
        await ctx.send(f'Channel create limit set to {total} in the security window.')

    @commands.command()
    async def rolecreatelimit(self, ctx, total: int | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if total is None or not (2 <= total <= 20):
            await ctx.send('Usage: `!rolecreatelimit <2-20>`')
            return
        set_role_create_limit(str(ctx.guild.id), total)
        await ctx.send(f'Role create limit set to {total} in the security window.')

    @commands.group(invoke_without_command=True)
    async def whitelist(self, ctx):
        await ctx.send('Usage: `!whitelist add @user`, `!whitelist remove @user`, `!whitelist list`')

    @whitelist.command(name='add')
    async def whitelist_add(self, ctx, member: discord.Member | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if not member:
            await ctx.send('Usage: `!whitelist add @user`')
            return
        if add_whitelist(str(ctx.guild.id), str(member.id)):
            await ctx.send(f'{member.mention} added to whitelist.')
        else:
            await ctx.send(f'{member.mention} is already whitelisted.')

    @whitelist.command(name='remove')
    async def whitelist_remove(self, ctx, member: discord.Member | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if not member:
            await ctx.send('Usage: `!whitelist remove @user`')
            return
        if remove_whitelist(str(ctx.guild.id), str(member.id)):
            await ctx.send(f'{member.mention} removed from whitelist.')
        else:
            await ctx.send(f'{member.mention} was not whitelisted.')

    @whitelist.command(name='list')
    async def whitelist_list(self, ctx):
        ids = get_whitelist(str(ctx.guild.id))
        if not ids:
            await ctx.send('No whitelisted users yet.')
            return
        mentions = []
        for user_id in ids:
            member = ctx.guild.get_member(int(user_id))
            mentions.append(member.mention if member else f'<@{user_id}>')
        await ctx.send('Whitelist: ' + ', '.join(mentions))

    @commands.command()
    async def addword(self, ctx, *, word: str | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if not word:
            await ctx.send('Usage: `!addword <word>`')
            return
        if add_custom_word(str(ctx.guild.id), word):
            await ctx.send(f"Added `{word.strip()}` to this server's custom words.")
        else:
            await ctx.send(f"`{word.strip()}` is already configured.")

    @commands.command()
    async def removeword(self, ctx, *, word: str | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if not word:
            await ctx.send('Usage: `!removeword <word>`')
            return
        if remove_custom_word(str(ctx.guild.id), word):
            await ctx.send(f"Removed `{word.strip()}`.")
        else:
            await ctx.send(f"`{word.strip()}` was not configured.")

    @commands.command()
    async def wordlist(self, ctx):
        words = sorted(get_custom_words(str(ctx.guild.id)))
        if not words:
            await ctx.send('No custom words configured.')
            return
        await ctx.send('Custom words: ' + ', '.join(f'`{word}`' for word in words))

    @commands.command()
    async def warnings(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        count = get_warnings(str(ctx.guild.id), str(member.id))
        await ctx.send(f'{member.mention} has {count} warning(s).')

    @commands.command()
    async def clearwarn(self, ctx, member: discord.Member | None = None):
        if not self.is_admin(ctx.author):
            await ctx.send('Administrator permission required.')
            return
        if not member:
            await ctx.send('Usage: `!clearwarn @user`')
            return
        reset_warnings(str(ctx.guild.id), str(member.id))
        await ctx.send(f'Warnings cleared for {member.mention}.')

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int | None = None):
        if amount is None or not (1 <= amount <= 100):
            await ctx.send('Usage: `!purge <1-100>`')
            return
        deleted = await ctx.channel.purge(limit=amount + 1)
        notice = await ctx.send(f'Deleted {len(deleted) - 1} message(s).')
        await notice.delete(delay=3)

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int | None = None):
        if seconds is None or not (0 <= seconds <= 21600):
            await ctx.send('Usage: `!slowmode <0-21600>`')
            return
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f'Slowmode set to {seconds} second(s) in {ctx.channel.mention}.')

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def announce(self, ctx, channel: discord.TextChannel | None = None, *, message: str | None = None):
        if not channel or not message:
            await ctx.send('Usage: `!announce #channel <message>`')
            return
        embed = discord.Embed(description=message, color=discord.Color.blurple())
        embed.set_author(name=f'Announcement from {ctx.guild.name}')
        await channel.send(embed=embed)
        await ctx.send(f'Announcement sent to {channel.mention}.')

    @commands.command()
    async def serverinfo(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
        embed.add_field(name='Owner', value=str(guild.owner), inline=True)
        embed.add_field(name='Members', value=str(guild.member_count), inline=True)
        embed.add_field(name='Roles', value=str(len(guild.roles)), inline=True)
        embed.add_field(name='Channels', value=str(len(guild.channels)), inline=True)
        embed.add_field(name='Created', value=guild.created_at.strftime('%d %b %Y'), inline=True)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=embed)

    @commands.command()
    async def userinfo(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        embed = discord.Embed(title=f'User Info - {member}', color=discord.Color.blurple())
        embed.add_field(name='ID', value=str(member.id), inline=False)
        embed.add_field(name='Joined server', value=member.joined_at.strftime('%d %b %Y') if member.joined_at else 'Unknown', inline=True)
        embed.add_field(name='Created account', value=member.created_at.strftime('%d %b %Y'), inline=True)
        embed.add_field(name='Top role', value=member.top_role.mention if member.top_role else 'None', inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command()
    async def avatar(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        embed = discord.Embed(title=f'Avatar - {member}', color=discord.Color.blurple())
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command()
    async def botstats(self, ctx):
        embed = discord.Embed(title='Zoro Bot Stats', color=discord.Color.blurple())
        embed.add_field(name='Servers', value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name='Latency', value=f'{round(self.bot.latency * 1000)}ms', inline=True)
        embed.add_field(name='Users cached', value=str(len(self.bot.users)), inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    async def panic(self, ctx):
        if not self.can_run_lockdown(ctx.author):
            await ctx.send('Only the bot owner, server owner, or an administrator can use this.')
            return
        clear_lockdown_overrides(str(ctx.guild.id))
        changed = 0
        for channel in ctx.guild.channels:
            changed += await self.emergency_lock_channel(ctx.guild, channel)
        await ctx.send(f'Emergency panic lockdown enabled. Applied {changed} permission changes across roles and member overrides. Use `!unlock` only after the threat is checked.')

    @commands.command()
    async def unlock(self, ctx):
        if not self.can_run_lockdown(ctx.author):
            await ctx.send('Only the bot owner, server owner, or an administrator can use this.')
            return
        rows = get_lockdown_overrides(str(ctx.guild.id))
        if not rows:
            changed = await self.emergency_unlock_fallback(ctx.guild)
            await ctx.send(f'No saved emergency state was found, so a fallback unlock was applied to {changed} permission entries. Review channel permissions after recovery.')
            return
        changed = 0
        for row in rows:
            channel = ctx.guild.get_channel(int(row['channel_id']))
            if not channel:
                continue
            if row.get('target_type') == 'member':
                target = ctx.guild.get_member(int(row['target_id']))
            else:
                target = ctx.guild.get_role(int(row['target_id']))
            if not target:
                continue
            try:
                await channel.set_permissions(
                    target,
                    view_channel=decode_perm(row['old_view']),
                    send_messages=decode_perm(row['old_send']),
                    connect=decode_perm(row['old_connect']),
                )
                changed += 1
            except discord.Forbidden:
                pass
            except Exception:
                pass
        clear_lockdown_overrides(str(ctx.guild.id))
        await ctx.send(f'Emergency lockdown removed. Restored {changed} saved permission entries.')

    @commands.command()
    async def setup(self, ctx):
        ensure_guild(str(ctx.guild.id))
        embed = discord.Embed(
            title=f'Zoro Setup - {ctx.guild.name}',
            description='Quick-start panel for logs, moderation, security, and staff safety.',
            color=discord.Color.blurple(),
        )
        embed.add_field(name='Logs', value='`!setlog #logs`', inline=False)
        embed.add_field(name='Moderation', value='`!automod on`, `!sensitivity 60`, `!setmute 5`, `!setmaxwarn 3`', inline=False)
        embed.add_field(name='Security', value='`!antiraid on`, `!antinuke on`, `!antilink on`, `!securitystatus` `!rolecreatelimit 3`', inline=False)
        embed.add_field(name='Safe staff', value='`!whitelist add @user`', inline=False)
        embed.add_field(name='AI chat', value='`!aireplies on` or `!aireplies off`', inline=False)
        embed.add_field(name='Utilities', value='`!help`, `!serverinfo`, `!userinfo`, `!botstats`', inline=False)
        embed.set_footer(text='All settings are saved per server. Safe to use across multiple servers.')
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Admin(bot))

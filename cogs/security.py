import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone

from database import get_connection, get_guild_config, is_whitelisted


TOKEN_GRAB_DOMAINS = {
    'discordnitro',
    'free-nitro',
    'discord-gift',
    'steamcommunity.ru',
    'steamcommunity.com.ru',
    'nitro-gift',
    'discordapp.gifts',
    'discord.gift.ru',
    'freegift',
    'claimnitro',
    'getnitro',
}


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
    conn.commit()
    conn.close()


def encode_perm(value):
    if value is None:
        return 'none'
    return 'true' if value else 'false'


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


def clear_lockdown_overrides(guild_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM lockdown_overrides WHERE guild_id = ?', (guild_id,))
    conn.commit()
    conn.close()


class Security(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        setup_lockdown_table()
        self._join_tracker: dict[str, list[datetime]] = {}
        self._ch_create: dict[str, list[datetime]] = {}
        self._ch_delete: dict[str, list[datetime]] = {}
        self._role_delete: dict[str, list[datetime]] = {}
        self._role_create: dict[str, list[datetime]] = {}
        self._lockdowns: set[int] = set()

    def get_config(self, guild_id: int | str) -> dict:
        return get_guild_config(str(guild_id))

    def tracker_key(self, guild_id: int | str, user_id: int | str) -> str:
        return f'{guild_id}:{user_id}'

    async def send_log(self, guild: discord.Guild, message: str, *, title: str = 'Security Alert', color: discord.Color | None = None):
        config = self.get_config(guild.id)
        if not config.get('security_logs_enabled', True):
            return
        channel_id = config.get('log_channel_id')
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if not channel:
            return
        embed = discord.Embed(
            title=title,
            description=message[:3800],
            color=color or discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f'{guild.name} | Security log')
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    async def punish_nuker(self, guild: discord.Guild, user: discord.abc.User, reason: str) -> str:
        try:
            await guild.ban(user, reason=reason)
            return 'banned'
        except discord.Forbidden:
            try:
                member = guild.get_member(user.id)
                if member:
                    await guild.kick(member, reason=reason)
                    return 'kicked'
            except discord.Forbidden:
                pass
        return 'not_removed'

    async def lock_server(self, guild: discord.Guild, reason: str):
        if guild.id in self._lockdowns:
            return
        self._lockdowns.add(guild.id)
        changed = 0
        try:
            clear_lockdown_overrides(str(guild.id))
            targets = [guild.default_role] + [role for role in guild.roles if role != guild.default_role and not role.permissions.administrator]
            for channel in guild.channels:
                for role in targets:
                    try:
                        overwrite = channel.overwrites_for(role)
                        save_lockdown_override(str(guild.id), str(channel.id), str(role.id), 'role', overwrite.view_channel, overwrite.send_messages, overwrite.connect)
                        await channel.set_permissions(role, view_channel=False, send_messages=False, connect=False, reason=f'Security lockdown: {reason}')
                        changed += 1
                    except Exception:
                        pass
                for target, overwrite in channel.overwrites.items():
                    if not isinstance(target, discord.Member):
                        continue
                    if target.guild_permissions.administrator:
                        continue
                    try:
                        save_lockdown_override(str(guild.id), str(channel.id), str(target.id), 'member', overwrite.view_channel, overwrite.send_messages, overwrite.connect)
                        await channel.set_permissions(target, view_channel=False, send_messages=False, connect=False, reason=f'Security lockdown: {reason}')
                        changed += 1
                    except Exception:
                        pass
            await self.send_log(
                guild,
                f'Lockdown triggered.\nReason: `{reason}`\nPermission entries changed: `{changed}`',
                title='Lockdown Activated',
                color=discord.Color.dark_red(),
            )
        finally:
            self._lockdowns.discard(guild.id)

    def _track_window(self, store: dict[str, list[datetime]], key: str, seconds: int) -> int:
        now = datetime.now(timezone.utc)
        store.setdefault(key, []).append(now)
        store[key] = [timestamp for timestamp in store[key] if now - timestamp < timedelta(seconds=seconds)]
        return len(store[key])

    async def get_recent_audit_actor(self, guild: discord.Guild, action: discord.AuditLogAction):
        try:
            async for entry in guild.audit_logs(limit=3, action=action):
                created = entry.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - created > timedelta(seconds=15):
                    continue
                user = entry.user
                if not user or user.bot or is_whitelisted(str(guild.id), str(user.id)):
                    return None
                return user
        except discord.Forbidden:
            return None
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = self.get_config(member.guild.id)
        if not config.get('anti_raid_enabled', True):
            return

        count = self._track_window(self._join_tracker, str(member.guild.id), int(config.get('raid_window_seconds', 10)))
        if count >= int(config.get('raid_limit', 5)):
            await self.lock_server(member.guild, f'Raid detected: {count} joins in {config.get("raid_window_seconds", 10)}s')
            await self.send_log(member.guild, f'Join spike crossed threshold.\nCount: `{count}`\nWindow: `{config.get("raid_window_seconds", 10)}s`', title='Anti-Raid Triggered', color=discord.Color.orange())
            self._join_tracker[str(member.guild.id)] = []

    async def handle_nuke_action(self, guild: discord.Guild, user: discord.abc.User, tracker: dict[str, list[datetime]], label: str):
        config = self.get_config(guild.id)
        key = self.tracker_key(guild.id, user.id)
        count = self._track_window(tracker, key, int(config.get('raid_window_seconds', 10)))
        if count < int(config.get('nuke_limit', 2)):
            return
        result = await self.punish_nuker(guild, user, f'Nuke attempt: {label}')
        await self.lock_server(guild, f'{label} by {user} ({result})')
        tracker[key] = []
        await self.send_log(guild, f'Actor: {user.mention if hasattr(user, "mention") else user}\nAction: `{label}`\nResult: `{result}`', title='Anti-Nuke Triggered', color=discord.Color.dark_red())

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        config = self.get_config(guild.id)
        if not config.get('anti_nuke_enabled', True):
            return
        user = await self.get_recent_audit_actor(guild, discord.AuditLogAction.channel_delete)
        if user:
            await self.handle_nuke_action(guild, user, self._ch_delete, 'mass channel delete')

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        config = self.get_config(guild.id)
        if not config.get('anti_nuke_enabled', True):
            return
        user = await self.get_recent_audit_actor(guild, discord.AuditLogAction.role_delete)
        if user:
            await self.handle_nuke_action(guild, user, self._role_delete, 'mass role delete')

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        config = self.get_config(guild.id)
        if not config.get('anti_nuke_enabled', True):
            return
        user = await self.get_recent_audit_actor(guild, discord.AuditLogAction.role_create)
        if not user:
            return
        key = self.tracker_key(guild.id, user.id)
        count = self._track_window(self._role_create, key, int(config.get('raid_window_seconds', 10)))
        if count >= int(config.get('role_create_limit', 3)):
            result = await self.punish_nuker(guild, user, 'Nuke attempt: role spam create')
            await self.lock_server(guild, f'role create spam by {user} ({result})')
            self._role_create[key] = []
            await self.send_log(guild, f'Actor: {user.mention if hasattr(user, "mention") else user}\nAction: `role create spam`\nResult: `{result}`', title='Anti-Nuke Triggered', color=discord.Color.dark_red())

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        config = self.get_config(guild.id)
        if not config.get('anti_nuke_enabled', True):
            return
        user = await self.get_recent_audit_actor(guild, discord.AuditLogAction.channel_create)
        if not user:
            return
        key = self.tracker_key(guild.id, user.id)
        count = self._track_window(self._ch_create, key, int(config.get('raid_window_seconds', 10)))
        if count >= int(config.get('channel_create_limit', 4)):
            result = await self.punish_nuker(guild, user, 'Nuke attempt: channel spam create')
            await self.lock_server(guild, f'channel create spam by {user} ({result})')
            self._ch_create[key] = []
            await self.send_log(guild, f'Actor: {user.mention if hasattr(user, "mention") else user}\nAction: `channel create spam`\nResult: `{result}`', title='Anti-Nuke Triggered', color=discord.Color.dark_red())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        config = self.get_config(message.guild.id)
        if not config.get('anti_link_enabled', True):
            return
        if is_whitelisted(str(message.guild.id), str(message.author.id)):
            return
        content = message.content.lower()
        found = any(domain in content for domain in TOKEN_GRAB_DOMAINS)
        if not found and 'discord' in content and any(word in content for word in ['gift', 'nitro', 'free', 'claim']):
            if 'discord.gg/' not in content and 'discord.com/invite/' not in content:
                found = True
        if not found:
            return
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        await message.channel.send(f'{message.author.mention} suspicious link removed. Do not click fake Nitro or token-grab links.')
        await self.send_log(message.guild, f'Author: {message.author.mention}\nChannel: {message.channel.mention}\nSnippet: `{message.content[:120]}`', title='Anti-Link Triggered', color=discord.Color.gold())

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def securityselftest(self, ctx, mode: str = 'status'):
        mode = mode.lower().strip()
        config = self.get_config(ctx.guild.id)
        if mode == 'status':
            await ctx.send('Security self-test modes: `status`, `raid`, `antilink`, `nuke-dry`, `lockdown`\nUse only in a test server. `lockdown` will actually hide/lock channels until `!unlock`.')
            return
        if mode == 'raid':
            await self.send_log(ctx.guild, f'Current threshold: `{config.get("raid_limit", 5)}` joins in `{config.get("raid_window_seconds", 10)}s`', title='Self-Test: Anti-Raid', color=discord.Color.orange())
            await ctx.send('Raid self-test complete. Check your log channel for the simulated alert.')
            return
        if mode == 'antilink':
            await self.send_log(ctx.guild, 'Suspicious link detection pipeline is enabled.', title='Self-Test: Anti-Link', color=discord.Color.gold())
            await ctx.send('Anti-link self-test complete. Check your log channel for the simulated alert.')
            return
        if mode == 'nuke-dry':
            await self.send_log(ctx.guild, f'Delete threshold: `{config.get("nuke_limit", 2)}` | Channel create threshold: `{config.get("channel_create_limit", 4)}` | Role create threshold: `{config.get("role_create_limit", 3)}`', title='Self-Test: Anti-Nuke', color=discord.Color.red())
            await ctx.send('Anti-nuke dry run complete. No channels were changed. Check your log channel.')
            return
        if mode == 'lockdown':
            await ctx.send('Real lockdown self-test is disabled for safety. Use `!securityselftest raid`, `!securityselftest antilink`, or `!securityselftest nuke-dry` in live servers. Use `!panic` only during a real attack.')
            return
        await ctx.send('Unknown mode. Use `!securityselftest status`.')

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await self.send_log(guild, f'{user} (`{user.id}`) was banned from the server.', title='Ban Logged')

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self.send_log(member.guild, f'{member} (`{member.id}`) left the server.', title='Member Left', color=discord.Color.blurple())


async def setup(bot):
    await bot.add_cog(Security(bot))

import discord
from discord.ext import commands

from database import get_connection


DEFAULT_WELCOME_TEMPLATE = 'Hey {mention}, welcome to **{server}**. You are member **#{member_count}**.'
DEFAULT_GOODBYE_TEMPLATE = '{name} left **{server}**. We now have **{member_count}** members.'
PREFERRED_CHANNEL_NAMES = {'welcome', 'welcomes', 'general', 'chat', 'lobby'}


def setup_welcome_table():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS welcome_config (
            guild_id          TEXT PRIMARY KEY,
            welcome_channel   TEXT,
            goodbye_channel   TEXT,
            autorole_id       TEXT,
            welcome_enabled   INTEGER DEFAULT 1,
            goodbye_enabled   INTEGER DEFAULT 1,
            welcome_template  TEXT,
            goodbye_template  TEXT
        )
        """
    )
    c.execute("PRAGMA table_info(welcome_config)")
    existing = {row['name'] for row in c.fetchall()}
    for name, definition in {
        'autorole_id': 'TEXT',
        'welcome_enabled': 'INTEGER DEFAULT 1',
        'goodbye_enabled': 'INTEGER DEFAULT 1',
        'welcome_template': 'TEXT',
        'goodbye_template': 'TEXT',
    }.items():
        if name not in existing:
            c.execute(f"ALTER TABLE welcome_config ADD COLUMN {name} {definition}")
    conn.commit()
    conn.close()


def get_welcome_config(guild_id: str) -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM welcome_config WHERE guild_id=?", (guild_id,))
    row = c.fetchone()
    conn.close()
    if row:
        data = dict(row)
        data['welcome_enabled'] = bool(data.get('welcome_enabled', 1))
        data['goodbye_enabled'] = bool(data.get('goodbye_enabled', 1))
        data['welcome_template'] = data.get('welcome_template') or DEFAULT_WELCOME_TEMPLATE
        data['goodbye_template'] = data.get('goodbye_template') or DEFAULT_GOODBYE_TEMPLATE
        return data
    return {
        'guild_id': guild_id,
        'welcome_channel': None,
        'goodbye_channel': None,
        'autorole_id': None,
        'welcome_enabled': True,
        'goodbye_enabled': True,
        'welcome_template': DEFAULT_WELCOME_TEMPLATE,
        'goodbye_template': DEFAULT_GOODBYE_TEMPLATE,
    }


def set_welcome_field(guild_id: str, field: str, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO welcome_config (guild_id) VALUES (?)", (guild_id,))
    c.execute(f"UPDATE welcome_config SET {field} = ? WHERE guild_id = ?", (value, guild_id))
    conn.commit()
    conn.close()


def render_template(template: str, member: discord.Member) -> str:
    return template.format(
        mention=member.mention,
        name=member.display_name,
        server=member.guild.name,
        member_count=member.guild.member_count,
        user_id=member.id,
    )


def channel_value(channel_id: str | None) -> str:
    return f"<#{channel_id}>" if channel_id else 'Auto / not found yet'


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        setup_welcome_table()

    def pick_default_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        candidates = []
        if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
            return guild.system_channel
        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.me)
            if perms.view_channel and perms.send_messages:
                candidates.append(channel)
        for channel in candidates:
            if channel.name.lower() in PREFERRED_CHANNEL_NAMES:
                return channel
        return candidates[0] if candidates else None

    def ensure_defaults(self, guild: discord.Guild) -> dict:
        cfg = get_welcome_config(str(guild.id))
        changed = False
        default_channel = self.pick_default_channel(guild)
        if not cfg.get('welcome_template'):
            set_welcome_field(str(guild.id), 'welcome_template', DEFAULT_WELCOME_TEMPLATE)
            cfg['welcome_template'] = DEFAULT_WELCOME_TEMPLATE
            changed = True
        if not cfg.get('goodbye_template'):
            set_welcome_field(str(guild.id), 'goodbye_template', DEFAULT_GOODBYE_TEMPLATE)
            cfg['goodbye_template'] = DEFAULT_GOODBYE_TEMPLATE
            changed = True
        if default_channel and not cfg.get('welcome_channel'):
            set_welcome_field(str(guild.id), 'welcome_channel', str(default_channel.id))
            cfg['welcome_channel'] = str(default_channel.id)
            changed = True
        if default_channel and not cfg.get('goodbye_channel'):
            set_welcome_field(str(guild.id), 'goodbye_channel', str(default_channel.id))
            cfg['goodbye_channel'] = str(default_channel.id)
            changed = True
        if changed:
            cfg = get_welcome_config(str(guild.id))
        return cfg

    def make_welcome_embed(self, member: discord.Member) -> discord.Embed:
        cfg = self.ensure_defaults(member.guild)
        embed = discord.Embed(title=f'Welcome to {member.guild.name}!', color=discord.Color.green())
        embed.description = render_template(cfg.get('welcome_template', DEFAULT_WELCOME_TEMPLATE), member)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Joined: {member.joined_at.strftime('%d %b %Y') if member.joined_at else 'Today'}")
        return embed

    def make_goodbye_embed(self, member: discord.Member) -> discord.Embed:
        cfg = self.ensure_defaults(member.guild)
        embed = discord.Embed(title=f'{member.display_name} left the server', color=discord.Color.red())
        embed.description = render_template(cfg.get('goodbye_template', DEFAULT_GOODBYE_TEMPLATE), member)
        embed.set_thumbnail(url=member.display_avatar.url)
        return embed

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self.ensure_defaults(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self.ensure_defaults(member.guild)
        autorole_id = cfg.get('autorole_id')
        if autorole_id:
            role = member.guild.get_role(int(autorole_id))
            if role:
                try:
                    await member.add_roles(role, reason='Autorole on join')
                except discord.Forbidden:
                    pass
        if not cfg.get('welcome_enabled', True):
            return
        channel_id = cfg.get('welcome_channel')
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(embed=self.make_welcome_embed(member))
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = self.ensure_defaults(member.guild)
        if not cfg.get('goodbye_enabled', True):
            return
        channel_id = cfg.get('goodbye_channel')
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(embed=self.make_goodbye_embed(member))
            except discord.Forbidden:
                pass

    @commands.command()
    async def setwelcome(self, ctx, channel: discord.TextChannel = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not channel:
            await ctx.send('Usage: `!setwelcome #channel`')
            return
        set_welcome_field(str(ctx.guild.id), 'welcome_channel', str(channel.id))
        await ctx.send(f'Welcome messages will be sent to {channel.mention}. The default template is already active until you change it with `!setwelcometext`.')

    @commands.command()
    async def setgoodbye(self, ctx, channel: discord.TextChannel = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not channel:
            await ctx.send('Usage: `!setgoodbye #channel`')
            return
        set_welcome_field(str(ctx.guild.id), 'goodbye_channel', str(channel.id))
        await ctx.send(f'Goodbye messages will be sent to {channel.mention}. The default template is already active until you change it with `!setgoodbyetext`.')

    @commands.command()
    async def setautorole(self, ctx, role: discord.Role = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not role:
            await ctx.send('Usage: `!setautorole @role`')
            return
        set_welcome_field(str(ctx.guild.id), 'autorole_id', str(role.id))
        await ctx.send(f'Autorole set to {role.mention}.')

    @commands.command()
    async def setwelcometext(self, ctx, *, template: str = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not template:
            await ctx.send('Usage: `!setwelcometext <template>`')
            return
        set_welcome_field(str(ctx.guild.id), 'welcome_template', template)
        await ctx.send('Welcome template updated.')

    @commands.command()
    async def setgoodbyetext(self, ctx, *, template: str = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if not template:
            await ctx.send('Usage: `!setgoodbyetext <template>`')
            return
        set_welcome_field(str(ctx.guild.id), 'goodbye_template', template)
        await ctx.send('Goodbye template updated.')

    @commands.command()
    async def welcomevars(self, ctx):
        await ctx.send('Template variables: `{mention}` `{name}` `{server}` `{member_count}` `{user_id}`')

    @commands.command()
    async def welcome(self, ctx, state: str = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if state not in {'on', 'off'}:
            await ctx.send('Usage: `!welcome on` or `!welcome off`')
            return
        set_welcome_field(str(ctx.guild.id), 'welcome_enabled', 1 if state == 'on' else 0)
        await ctx.send(f'Welcome messages {"enabled" if state == "on" else "disabled"}.')

    @commands.command()
    async def goodbye(self, ctx, state: str = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('Administrator permission required.')
            return
        if state not in {'on', 'off'}:
            await ctx.send('Usage: `!goodbye on` or `!goodbye off`')
            return
        set_welcome_field(str(ctx.guild.id), 'goodbye_enabled', 1 if state == 'on' else 0)
        await ctx.send(f'Goodbye messages {"enabled" if state == "on" else "disabled"}.')

    @commands.command()
    async def welcomesetup(self, ctx):
        cfg = self.ensure_defaults(ctx.guild)
        embed = discord.Embed(title=f'Welcome Setup - {ctx.guild.name}', color=discord.Color.green())
        embed.description = 'Default welcome and goodbye templates are already active. Change them only if you want custom text.'
        embed.add_field(name='Welcome channel', value=channel_value(cfg.get('welcome_channel')), inline=False)
        embed.add_field(name='Goodbye channel', value=channel_value(cfg.get('goodbye_channel')), inline=False)
        embed.add_field(name='Autorole', value=f"<@&{cfg['autorole_id']}>" if cfg.get('autorole_id') else 'Not set', inline=False)
        embed.add_field(name='Welcome enabled', value='ON' if cfg.get('welcome_enabled', True) else 'OFF', inline=True)
        embed.add_field(name='Goodbye enabled', value='ON' if cfg.get('goodbye_enabled', True) else 'OFF', inline=True)
        embed.add_field(name='Welcome template', value=cfg.get('welcome_template', DEFAULT_WELCOME_TEMPLATE)[:200], inline=False)
        embed.add_field(name='Goodbye template', value=cfg.get('goodbye_template', DEFAULT_GOODBYE_TEMPLATE)[:200], inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def testwelcome(self, ctx):
        self.ensure_defaults(ctx.guild)
        await ctx.send(embed=self.make_welcome_embed(ctx.author))


async def setup(bot):
    await bot.add_cog(Welcome(bot))

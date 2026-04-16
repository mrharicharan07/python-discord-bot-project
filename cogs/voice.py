import asyncio

import discord
from discord.ext import commands, tasks

from config import VOICE_RECONNECT_INTERVAL
from database import get_connection


def setup_voice_table():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS voice_247 (
            guild_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            text_channel_id TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def ensure_voice_columns():
    conn = get_connection()
    c = conn.cursor()
    c.execute('PRAGMA table_info(voice_247)')
    existing = {row['name'] for row in c.fetchall()}
    if 'text_channel_id' not in existing:
        c.execute('ALTER TABLE voice_247 ADD COLUMN text_channel_id TEXT')
    conn.commit()
    conn.close()


def get_247_record(guild_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        'SELECT channel_id, text_channel_id FROM voice_247 WHERE guild_id = ?',
        (guild_id,),
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_247_records():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT guild_id, channel_id, text_channel_id FROM voice_247')
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def set_247_channel(guild_id: str, channel_id: str, text_channel_id: str | None):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO voice_247 (guild_id, channel_id, text_channel_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            channel_id = excluded.channel_id,
            text_channel_id = excluded.text_channel_id
        """,
        (guild_id, channel_id, text_channel_id),
    )
    conn.commit()
    conn.close()


def clear_247_channel(guild_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM voice_247 WHERE guild_id = ?', (guild_id,))
    conn.commit()
    conn.close()


class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        setup_voice_table()
        ensure_voice_columns()
        self._reconnect_locks: set[int] = set()
        self._connect_locks: set[int] = set()
        self._last_notice_at: dict[int, float] = {}
        self._last_errors: dict[int, str] = {}
        self.voice_watchdog.start()

    def cog_unload(self):
        self.voice_watchdog.cancel()

    def set_last_error(self, guild_id: int, text: str):
        self._last_errors[guild_id] = text[:300]

    def get_last_error(self, guild_id: int) -> str:
        return self._last_errors.get(guild_id, 'No voice error recorded yet.')

    async def send_notice(self, guild: discord.Guild, record: dict | None, text: str):
        if not guild or not record or not record.get('text_channel_id'):
            return
        now = asyncio.get_running_loop().time()
        last = self._last_notice_at.get(guild.id, 0)
        if now - last < 15:
            return
        self._last_notice_at[guild.id] = now
        channel = guild.get_channel(int(record['text_channel_id']))
        if channel:
            try:
                await channel.send(text)
            except discord.Forbidden:
                pass

    def describe_voice_readiness(self, guild: discord.Guild, channel: discord.VoiceChannel) -> str | None:
        me = guild.me
        if me is None:
            return 'Bot member cache is not ready yet. Try again in a few seconds.'
        perms = channel.permissions_for(me)
        missing = []
        if not perms.view_channel:
            missing.append('View Channel')
        if not perms.connect:
            missing.append('Connect')
        if not perms.speak:
            missing.append('Speak')
        if missing:
            return 'Missing voice permissions: ' + ', '.join(missing)
        if not discord.opus.is_loaded():
            return 'Opus library is not loaded on this PC. Discord voice cannot connect until Opus is available.'
        return None

    async def ensure_connected(self, guild: discord.Guild, channel: discord.VoiceChannel):
        readiness_error = self.describe_voice_readiness(guild, channel)
        if readiness_error:
            self.set_last_error(guild.id, readiness_error)
            return False

        if guild.id in self._connect_locks:
            for _ in range(16):
                await asyncio.sleep(0.5)
                voice_client = guild.voice_client
                if voice_client and voice_client.is_connected() and voice_client.channel:
                    self.set_last_error(guild.id, '')
                    return voice_client.channel.id == channel.id
            self.set_last_error(guild.id, 'Another voice connection attempt is still in progress.')
            return False

        self._connect_locks.add(guild.id)
        try:
            voice_client = guild.voice_client
            if voice_client and voice_client.is_connected():
                if voice_client.channel and voice_client.channel.id != channel.id:
                    await voice_client.move_to(channel)
                    for _ in range(10):
                        await asyncio.sleep(0.3)
                        if voice_client.channel and voice_client.channel.id == channel.id:
                            self.set_last_error(guild.id, '')
                            return True
                self.set_last_error(guild.id, '')
                return True

            if voice_client and not voice_client.is_connected():
                try:
                    await voice_client.disconnect(force=True)
                except Exception:
                    pass
                await asyncio.sleep(1)

            await channel.connect(reconnect=True)
            for _ in range(16):
                await asyncio.sleep(0.5)
                voice_client = guild.voice_client
                if voice_client and voice_client.is_connected() and voice_client.channel:
                    self.set_last_error(guild.id, '')
                    return voice_client.channel.id == channel.id
            self.set_last_error(guild.id, 'Discord voice connection timed out before confirming the channel.')
            return False
        except Exception as exc:
            error_text = f'{type(exc).__name__}: {exc}'
            self.set_last_error(guild.id, error_text)
            print(f'[VOICE ERROR] connect failed for {guild.id}: {error_text}')
            return False
        finally:
            self._connect_locks.discard(guild.id)

    async def connect_to_saved_channel(self, guild: discord.Guild, record: dict, announce: bool = False):
        if guild.id in self._reconnect_locks:
            return False
        channel = guild.get_channel(int(record['channel_id'])) if record else None
        if not isinstance(channel, discord.VoiceChannel):
            self.set_last_error(guild.id, 'Saved 24/7 channel no longer exists or is not a voice channel.')
            return False

        self._reconnect_locks.add(guild.id)
        try:
            voice_client = guild.voice_client
            before_channel_id = voice_client.channel.id if voice_client and voice_client.is_connected() and voice_client.channel else None
            success = await self.ensure_connected(guild, channel)
            if not success:
                return False
            if announce and before_channel_id != channel.id:
                await self.send_notice(guild, record, f"24/7 voice restored in `{channel.name}`.")
            return True
        finally:
            self._reconnect_locks.discard(guild.id)

    @tasks.loop(seconds=VOICE_RECONNECT_INTERVAL)
    async def voice_watchdog(self):
        await self.bot.wait_until_ready()
        for record in get_all_247_records():
            guild = self.bot.get_guild(int(record['guild_id']))
            if guild is None:
                continue
            voice_client = guild.voice_client
            if voice_client is None or not voice_client.is_connected():
                await self.connect_to_saved_channel(guild, record)

    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.sleep(3)
        for record in get_all_247_records():
            guild = self.bot.get_guild(int(record['guild_id']))
            if guild:
                await self.connect_to_saved_channel(guild, record, announce=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not self.bot.user or member.id != self.bot.user.id:
            return
        if after.channel is None:
            record = get_247_record(str(member.guild.id))
            if record:
                await asyncio.sleep(5)
                await self.connect_to_saved_channel(member.guild, record, announce=True)

    @commands.command()
    async def join(self, ctx):
        if not ctx.author.voice:
            await ctx.send('Join a voice channel first.')
            return

        channel = ctx.author.voice.channel
        if await self.ensure_connected(ctx.guild, channel):
            await ctx.send(f"Joined `{channel.name}`.")
        else:
            await ctx.send(f"Voice join failed: {self.get_last_error(ctx.guild.id)}")

    @commands.command()
    async def leave(self, ctx):
        clear_247_channel(str(ctx.guild.id))
        voice_client = ctx.guild.voice_client
        if not voice_client:
            await ctx.send('Not connected to a voice channel.')
            return
        await voice_client.disconnect(force=True)
        await ctx.send('Left the voice channel and disabled 24/7 mode.')

    @commands.command(name='247')
    async def stay_247(self, ctx):
        if not ctx.author.voice:
            await ctx.send('Join a voice channel first.')
            return

        channel = ctx.author.voice.channel
        success = await self.ensure_connected(ctx.guild, channel)
        if not success:
            await ctx.send(f"Could not enable 24/7 mode: {self.get_last_error(ctx.guild.id)}")
            return

        set_247_channel(str(ctx.guild.id), str(channel.id), str(ctx.channel.id))
        await ctx.send(f"24/7 voice enabled in `{channel.name}`.")

    @commands.command()
    async def stop(self, ctx):
        clear_247_channel(str(ctx.guild.id))
        voice_client = ctx.guild.voice_client
        if voice_client:
            await voice_client.disconnect(force=True)
        await ctx.send('24/7 voice disabled.')

    @commands.command()
    async def vcstatus(self, ctx):
        record = get_247_record(str(ctx.guild.id))
        voice_client = ctx.guild.voice_client
        if not record:
            await ctx.send('24/7 voice is OFF for this server.')
            return
        channel = ctx.guild.get_channel(int(record['channel_id']))
        channel_name = channel.name if channel else 'deleted-channel'
        state = 'connected' if voice_client and voice_client.is_connected() else 'waiting to reconnect'
        await ctx.send(f"24/7 voice is ON for `{channel_name}` and currently `{state}`.")

    @commands.command()
    async def vcdebug(self, ctx):
        if not ctx.author.voice:
            await ctx.send('Join a voice channel first.')
            return
        channel = ctx.author.voice.channel
        me = ctx.guild.me
        perms = channel.permissions_for(me) if me else None
        lines = [
            f"Opus loaded: {discord.opus.is_loaded()}",
            f"PyNaCl available: {'yes' if __import__('importlib').util.find_spec('nacl') else 'no'}",
            f"Last voice error: {self.get_last_error(ctx.guild.id)}",
        ]
        if perms:
            lines.append(f"View Channel: {'yes' if perms.view_channel else 'no'}")
            lines.append(f"Connect: {'yes' if perms.connect else 'no'}")
            lines.append(f"Speak: {'yes' if perms.speak else 'no'}")
        await ctx.send('\n'.join(lines))


async def setup(bot):
    await bot.add_cog(Voice(bot))

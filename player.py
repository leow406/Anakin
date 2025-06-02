# player.py
import discord
from discord.ext import commands
import wavelink
import config

class PlayerControls(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.red, custom_id="player_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        player = wavelink.Pool.get_node().get_player(self.guild_id)
        if player:
            if player.playing:
                await player.stop()
            if player.connected:
                await player.disconnect()

        embed = discord.Embed(
            title="▶️ Anakin Player",
            description="**No music is currently playing**\n\n__Next:__\nNothing for now",
            color=0xFFA500
        )
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="⏮️ Prev", style=discord.ButtonStyle.gray, custom_id="player_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        music_cog: Music = self.bot.get_cog("Music")
        if not music_cog:
            return

        guild_id = self.guild_id
        hist = music_cog.get_history(guild_id)
        if not hist:
            return

        prev_track = hist.pop()
        node = wavelink.Pool.get_node()
        player = node.get_player(guild_id)
        if player is None:
            member = interaction.user
            if member.voice and member.voice.channel:
                player = await member.voice.channel.connect(cls=wavelink.Player)
            else:
                return

        current = player.current if player and player.current else None
        if current:
            queue = music_cog.get_queue(guild_id)
            queue.insert(0, current)

        music_cog.set_skip_flag(guild_id, True)
        if player.playing or player.paused:
            await player.stop()

        await player.play(prev_track)

        minutes = prev_track.length // 60000
        seconds = (prev_track.length // 1000) % 60
        queue_after = music_cog.get_queue(guild_id)
        next_title = queue_after[0].title if queue_after else "None"
        embed = discord.Embed(
            title="▶️ Anakin Player",
            description=f"**{prev_track.title}** - ({minutes}:{seconds:02d})\n\n__Next:__\n{next_title}",
            color=0xFFA500
        )
        thumb = getattr(prev_track, "thumbnail", None) or getattr(prev_track, "thumbnail_url", None)
        if thumb:
            embed.set_thumbnail(url=thumb)

        await interaction.message.edit(embed=embed, view=self)

        parent_cog: PlayerEmbed = self.bot.get_cog("PlayerEmbed")
        if parent_cog and parent_cog.queue_message:
            await parent_cog.queue_message.edit(embed=parent_cog._build_queue_embed(guild_id))

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.blurple, custom_id="player_pause")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild_id = self.guild_id
        player = wavelink.Pool.get_node().get_player(guild_id)
        if not player or not player.playing or player.paused:
            return

        await player.pause(True)
        embed = interaction.message.embeds[0]
        desc = embed.description
        if desc.startswith("**"):
            embed.description = desc.replace("**", "⏸️ **", 1)
        else:
            embed.description = "⏸️ Music paused.\n\n" + desc

        await interaction.message.edit(embed=embed, view=self)
        parent_cog: PlayerEmbed = self.bot.get_cog("PlayerEmbed")
        if parent_cog and parent_cog.queue_message:
            await parent_cog.queue_message.edit(embed=parent_cog._build_queue_embed(guild_id))

    @discord.ui.button(label="▶️ Play", style=discord.ButtonStyle.green, custom_id="player_play")
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild_id = self.guild_id
        player = wavelink.Pool.get_node().get_player(guild_id)
        if not player or not player.paused:
            return

        await player.pause(False)
        embed = interaction.message.embeds[0]
        desc = embed.description
        if desc.startswith("⏸️ "):
            embed.description = desc.replace("⏸️ ", "", 1)

        await interaction.message.edit(embed=embed, view=self)
        parent_cog: PlayerEmbed = self.bot.get_cog("PlayerEmbed")
        if parent_cog and parent_cog.queue_message:
            await parent_cog.queue_message.edit(embed=parent_cog._build_queue_embed(guild_id))

    @discord.ui.button(label="⏭️ Next", style=discord.ButtonStyle.gray, custom_id="player_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        music_cog: Music = self.bot.get_cog("Music")
        if not music_cog:
            return

        guild_id = self.guild_id
        played = await music_cog.skip_track(guild_id)
        if not played:
            embed = discord.Embed(
                title="▶️ Anakin Player",
                description="**No music is currently playing**\n\n__Next:__\nNothing for now",
                color=0xFFA500
            )
            await interaction.message.edit(embed=embed, view=self)

        parent_cog: PlayerEmbed = self.bot.get_cog("PlayerEmbed")
        if parent_cog and parent_cog.queue_message:
            await parent_cog.queue_message.edit(embed=parent_cog._build_queue_embed(guild_id))

    @discord.ui.button(label="🕑 Queue", style=discord.ButtonStyle.secondary, custom_id="player_queue")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        parent_cog: PlayerEmbed = self.bot.get_cog("PlayerEmbed")
        if not parent_cog:
            return

        if parent_cog.queue_message is None:
            q_embed = parent_cog._build_queue_embed(self.guild_id)
            q_msg = await interaction.channel.send(embed=q_embed)
            parent_cog.queue_message = q_msg
            await q_msg.add_reaction("❌")
        else:
            await parent_cog.queue_message.edit(embed=parent_cog._build_queue_embed(self.guild_id))


class PlayerEmbed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.player_message: discord.Message | None = None
        self.queue_message: discord.Message | None = None

    def _build_queue_embed(self, guild_id: int) -> discord.Embed:
        music_cog: Music = self.bot.get_cog("Music")
        queue_list = music_cog.get_queue(guild_id) if music_cog else []
        embed = discord.Embed(title="🕑 Queue", color=0x00BFFF)
        if queue_list:
            lines = [f"**{i+1}.** {t.title}" for i, t in enumerate(queue_list[:10])]
            if len(queue_list) > 10:
                lines.append(f"…and {len(queue_list) - 10} more track(s).")
            embed.description = "\n".join(lines)
        else:
            embed.description = "No tracks in the queue."
        return embed

    @commands.Cog.listener()
    async def on_ready(self):
        """
        When the bot is ready:
        1) Purge the channel completely (100 messages at a time)
        2) Send the initial “Player” embed
        """
        channel_id = getattr(config, "PLAYER_CHANNEL_ID", None)
        if channel_id is None:
            print("❌ config.PLAYER_CHANNEL_ID is not defined.")
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            print(f"❌ Could not fetch channel with ID {channel_id}.")
            return

        # ─── 1) Complete channel purge ──────────────────────────────
        deleted = await channel.purge(limit=100)
        while len(deleted) == 100:
            deleted = await channel.purge(limit=100)

        # ─── 2) Send the initial “Player” embed ───────────────────
        embed = discord.Embed(
            title="▶️ Anakin Player",
            description="**No music is currently playing**\n\n__Next:__\nNothing for now",
            color=0xFFA500
        )
        msg = await channel.send(embed=embed)
        controls = PlayerControls(self.bot, guild_id=channel.guild.id)
        await msg.edit(view=controls)
        self.player_message = msg

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot:
            return
        if self.queue_message and reaction.message.id == self.queue_message.id:
            if reaction.emoji == "❌":
                try:
                    await self.queue_message.delete()
                except:
                    pass
                self.queue_message = None

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, event):
        current = event.track
        guild_id = event.player.guild.id
        music_cog: Music = self.bot.get_cog("Music")
        if not music_cog:
            return

        queue_list = music_cog.get_queue(guild_id)
        next_title = queue_list[0].title if queue_list else "None"

        minutes = current.length // 60000
        seconds = (current.length // 1000) % 60
        embed = discord.Embed(
            title="▶️ Anakin Player",
            description=f"**{current.title}** - ({minutes}:{seconds:02d})\n\n__Next:__\n{next_title}",
            color=0xFFA500
        )
        thumb = getattr(current, "thumbnail", None) or getattr(current, "thumbnail_url", None)
        if thumb:
            embed.set_thumbnail(url=thumb)

        if self.player_message:
            await self.player_message.edit(embed=embed)

        if self.queue_message:
            await self.queue_message.edit(embed=self._build_queue_embed(guild_id))

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, event):
        guild_id = event.player.guild.id
        music_cog: Music = self.bot.get_cog("Music")
        if not music_cog:
            return

        if music_cog.get_skip_flag(guild_id):
            return

        queue_list = music_cog.get_queue(guild_id)
        if not queue_list:
            embed = discord.Embed(
                title="▶️ Anakin Player",
                description="**No music is currently playing**\n\n__Next:__\nNothing for now",
                color=0xFFA500
            )
            if self.player_message:
                await self.player_message.edit(embed=embed)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, event):
        logger.error(f"❌ Exception on {event.track.title}: {event.exception}")

async def setup(bot: commands.Bot):
    await bot.add_cog(PlayerEmbed(bot))

#!/usr/bin/env python3
import logging
import random
import re
import discord
from discord.ext import commands
import wavelink

import config      # contains TOKEN (str), PREFIX (str or tuple), FFMPEG_PATH (not used here), Spotify credentials
import playlist    # separate module `playlist.py` in the same folder

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Load player extension
initial_extensions = ["player"]

# ─── Logging ────────────────────────────────────────────────────────
logger = logging.getLogger("Anakin")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
logger.addHandler(handler)

# ─── Lavalink Node Settings ────────────────────────────────────────
LAVA_HOST     = "127.0.0.1"
LAVA_PORT     = 2333
LAVA_PASSWORD = "youshallnotpass"

# ─── Bot & Intents ──────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=config.PREFIX,
            intents=intents,
            help_command=None  # disable Discord's default help command
        )

    async def setup_hook(self):
        # ─── Connect to the Lavalink node ───────────────────────────────
        node = wavelink.Node(
            uri=f"http://{LAVA_HOST}:{LAVA_PORT}",
            password=LAVA_PASSWORD
        )
        await wavelink.Pool.connect(nodes=[node], client=self)
        logger.info("🔗 Lavalink node connected.")

        # ─── Load the main Music cog ───────────────────────────────────
        await self.add_cog(Music(self))

        # ─── Load any additional extensions (e.g., player.py) ───────────
        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"✅ Loaded extension: {ext}")
            except Exception as e:
                logger.error(f"❌ Error while loading extension '{ext}': {e}")

bot = MusicBot()

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Dictionaries per guild:
        # - queues[guild_id] = list of Tracks in the queue
        # - history[guild_id] = list of previously played Tracks (max length 3) for "previous"
        # - skip_flags[guild_id] = bool, indicates a manual skip occurred
        # - loading[guild_id] = bool, indicates a playlist is currently loading
        # - pending_shuffle[guild_id] = bool, indicates a shuffle was requested during playlist loading
        # - loops[guild_id] = None (no loop), -1 (infinite loop), or int ≥ 0 (remaining loops)
        self.queues = {}
        self.history = {}
        self.skip_flags = {}
        self.loading = {}
        self.pending_shuffle = {}
        self.loops = {}

        # Shared Spotify client (if needed elsewhere)
        self.spotify_client = SpotifyClientCredentials(
            client_id=config.SPOTIPY_CLIENT_ID,
            client_secret=config.SPOTIPY_CLIENT_SECRET
        )
        self.sp = spotipy.Spotify(auth_manager=self.spotify_client)

    def get_queue(self, guild_id: int):
        return self.queues.setdefault(guild_id, [])

    def get_history(self, guild_id: int):
        return self.history.setdefault(guild_id, [])

    def set_skip_flag(self, guild_id: int, value: bool):
        self.skip_flags[guild_id] = value

    def get_skip_flag(self, guild_id: int):
        return self.skip_flags.get(guild_id, False)

    def set_loading(self, guild_id: int, value: bool):
        self.loading[guild_id] = value

    def get_loading(self, guild_id: int):
        return self.loading.get(guild_id, False)

    def set_pending_shuffle(self, guild_id: int, value: bool):
        self.pending_shuffle[guild_id] = value

    def get_pending_shuffle(self, guild_id: int):
        return self.pending_shuffle.get(guild_id, False)

    def set_loop(self, guild_id: int, count):
        """
        count = -1 => infinite loop
        count = int ≥ 0 => number of loops remaining
        count = None => no loop
        """
        if count is None:
            # Remove any existing loop state
            if guild_id in self.loops:
                del self.loops[guild_id]
        else:
            self.loops[guild_id] = count

    def get_loop(self, guild_id: int):
        return self.loops.get(guild_id, None)

    async def skip_track(self, guild_id: int):
        """
        Utility method to advance to the next track in the queue, same behavior as the "next" command.
        Returns True if a new track has started; False if the queue is empty and playback stops.
        Also clears any active loop for this guild.
        """
        # Clear the loop on manual skip
        self.set_loop(guild_id, None)

        node = wavelink.Pool.get_node()
        player = node.get_player(guild_id)
        queue = self.get_queue(guild_id)
        current = player.current if player and player.current else None

        # Case A: queue is empty and nothing is playing => stop the player
        if not queue and current is None:
            return False

        # Case B: queue is empty but a track is playing => stop it
        if not queue and current:
            hist = self.get_history(guild_id)
            hist.append(current)
            if len(hist) > 3:
                hist.pop(0)

            self.set_skip_flag(guild_id, True)
            await player.stop()
            return False

        # Case C: queue contains at least one track
        if queue:
            if current:
                hist = self.get_history(guild_id)
                hist.append(current)
                if len(hist) > 3:
                    hist.pop(0)

            next_track = queue.pop(0)
            self.set_skip_flag(guild_id, True)
            if player and player.playing:
                await player.stop()
            await player.play(next_track)
            return True

    @commands.command(name="play")
    async def play(self, ctx: commands.Context, *, query: str):
        """
        If nothing is playing, connect and play the requested song.
        Otherwise, add the result to the queue.
        Supports the -loop [number] option:
        -loop X  -> replay the track X times after the first play
        -loop    -> infinite loop
        Also recognizes YouTube and Spotify links.
        """
        guild_id = ctx.guild.id

        # Parse the -loop option
        loop_match = re.search(r"-loop(?:\s+(\d+))?", query)
        loop_count = None
        if loop_match:
            num = loop_match.group(1)
            if num is not None:
                loop_count = int(num)
            else:
                loop_count = -1  # infinite loop
            # Remove the -loop option from the search query
            query = re.sub(r"-loop(?:\s+\d+)?", "", query).strip()

        node = wavelink.Pool.get_node()
        player = node.get_player(guild_id)

        if player is None:
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.reply("❌ You must be in a voice channel.")
            player = await ctx.author.voice.channel.connect(cls=wavelink.Player)

        track: wavelink.Track = None

        # 1) Check for a YouTube link
        yt_match = re.search(
            r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})",
            query
        )
        if yt_match:
            url = yt_match.group(0)
            tracks = await wavelink.Playable.search(url)
            if not tracks:
                return await ctx.reply("❌ Could not load the YouTube track.")
            track = tracks[0]
        else:
            # 2) Check for a Spotify track link
            sp_match = re.search(
                r"(?:https?://)?open\.spotify\.com/track/([A-Za-z0-9]+)",
                query
            )
            if sp_match:
                spotify_id = sp_match.group(1)
                try:
                    sp_data = self.sp.track(spotify_id)
                except Exception:
                    return await ctx.reply("❌ Could not retrieve Spotify track info.")
                name = sp_data.get("name", "")
                artists = ", ".join(artist["name"] for artist in sp_data.get("artists", []))
                search_query = f"{name} {artists}"
                yt_results = await wavelink.Playable.search(search_query)
                if not yt_results:
                    return await ctx.reply(f"❌ Could not find a YouTube video for: **{name}**.")
                track = yt_results[0]
            else:
                # 3) Standard search by title on YouTube
                tracks = await wavelink.Playable.search(query)
                if not tracks:
                    return await ctx.reply("❌ No results found.")
                track = tracks[0]

        if player.playing:
            # Add to the queue without loop
            queue = self.get_queue(guild_id)
            queue.append(track)
            return await ctx.reply(f"➕ **{track.title}** added to the queue")

        # Play immediately
        await player.play(track)

        # Set up looping if requested
        if loop_match:
            self.set_loop(guild_id, loop_count)
            if loop_count == -1:
                await ctx.reply(f"🔁 Playing **{track.title}** on infinite loop")
            else:
                await ctx.reply(f"🔁 Playing **{track.title}** {loop_count+1} times total")
        else:
            # No loop
            self.set_loop(guild_id, None)
            await ctx.reply(f"▶️ Now playing: **{track.title}**")

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        """
        Stop playback and disconnect the bot, without clearing the queue.
        """
        guild_id = ctx.guild.id
        # Clear any active loop
        self.set_loop(guild_id, None)

        player = wavelink.Pool.get_node().get_player(guild_id)
        if not player:
            return await ctx.reply("❌ No active player.")
        if player.playing:
            await player.stop()
        if player.connected:
            await player.disconnect()
        await ctx.reply("🛑 Bot disconnected. Queue remains in memory.")

    @commands.command(name="music")
    async def music(self, ctx: commands.Context):
        """
        Resume playback if the bot was stopped, or unpause if music is paused.
        If the bot is disconnected but there are tracks in the queue,
        reconnect and play the next track.
        """
        guild_id = ctx.guild.id
        node = wavelink.Pool.get_node()
        player = node.get_player(guild_id)

        # If the player exists and is paused, unpause
        if player and player.paused:
            await player.pause(False)
            return await ctx.reply("▶️ Music resumed.")

        # Otherwise, attempt to reconnect and play from the queue
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.reply("❌ You must be in a voice channel to resume music.")
        voice_channel = ctx.author.voice.channel

        if player is None or not player.connected:
            player = await voice_channel.connect(cls=wavelink.Player)
            queue = self.get_queue(guild_id)
            if queue:
                next_track = queue.pop(0)
                await player.play(next_track)
                return await ctx.reply(f"▶️ Bot connected and playing next track: **{next_track.title}**")
            else:
                return await ctx.reply("📜 The queue is empty. Use `!play <title>` to add music.")

        return await ctx.reply("ℹ️ Music is already playing or nothing to resume.")

    @commands.command(name="pause", aliases=["=", "!="])
    async def pause(self, ctx: commands.Context):
        """Pause the current track."""
        player = wavelink.Pool.get_node().get_player(ctx.guild.id)
        if not player or not player.playing:
            return await ctx.reply("❌ No track is currently playing.")
        if player.paused:
            return await ctx.reply("⏸️ Music is already paused.")
        await player.pause(True)
        await ctx.reply("⏸️ Music paused.")

    @commands.command(name="resume", aliases=[">"])
    async def resume(self, ctx: commands.Context):
        """Resume playback if paused."""
        return await self.music.callback(self, ctx)

    @commands.command(name="queue", aliases=["qu"])
    async def queue(self, ctx: commands.Context):
        """
        Display the current queue, showing:
        - History (previously played titles) in italics
        - Current track in bold (and 🔁 if looping)
        - Upcoming tracks normally
        """
        guild_id = ctx.guild.id
        node = wavelink.Pool.get_node()
        player = node.get_player(guild_id)

        history = self.get_history(guild_id)
        queue = self.get_queue(guild_id)
        loop_flag = self.get_loop(guild_id)

        if player and (player.current or player.playing or player.paused):
            current = player.current
        else:
            current = None

        if not history and not current and not queue:
            return await ctx.reply("📜 No music playing, queue and history are empty.")

        embed = discord.Embed(
            title="📜 Queue Status",
            color=discord.Color.blurple()
        )

        # History: previously played titles in italics
        if history:
            passed_lines = "\n".join(f"*{track.title}*" for track in history)
            embed.add_field(name="🕘 Played (History)", value=passed_lines, inline=False)

        # Current track in bold, with loop icon if applicable
        if current:
            title_display = f"**{current.title}**"
            if loop_flag is not None:
                title_display += " 🔁"
            embed.add_field(name="▶️ Now Playing", value=title_display, inline=False)
        else:
            embed.add_field(name="▶️ Now Playing", value="No track is currently playing.", inline=False)

        # Upcoming tracks
        if queue:
            upcoming_lines = "\n".join(
                f"{idx}. {track.title}" for idx, track in enumerate(queue[:10], start=1)
            )
            if len(queue) > 10:
                upcoming_lines += f"\n…and {len(queue) - 10} more track(s)."
            embed.add_field(name="⏭️ Upcoming", value=upcoming_lines, inline=False)
        else:
            embed.add_field(name="⏭️ Upcoming", value="No tracks in the queue.", inline=False)

        await ctx.reply(embed=embed)

    @commands.command(name="add", aliases=["ad"])
    async def add(self, ctx: commands.Context, *, query: str):
        """
        Search for a track and add it to the queue.
        If nothing is playing, play immediately.
        """
        guild_id = ctx.guild.id
        node = wavelink.Pool.get_node()
        player = node.get_player(guild_id)

        if player is None:
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.reply("❌ You must be in a voice channel.")
            player = await ctx.author.voice.channel.connect(cls=wavelink.Player)

        tracks = await wavelink.Playable.search(query)
        if not tracks:
            return await ctx.reply("❌ No results found.")
        track = tracks[0]

        if not player.playing and not player.paused:
            await player.play(track)
            return await ctx.reply(f"▶️ Now playing: **{track.title}**")

        queue = self.get_queue(guild_id)
        queue.append(track)
        await ctx.reply(f"➕ **{track.title}** added to the queue")

    @commands.command(name="remove", aliases=["re", "rm"])
    async def remove(self, ctx: commands.Context, *, identifier: str):
        """
        Remove a track from the queue by matching part of its title or URL.
        """
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            return await ctx.reply("📜 The queue is empty.")
        lowered = identifier.lower()
        for i, track in enumerate(queue):
            if lowered in track.title.lower() or (track.uri and lowered in track.uri.lower()):
                removed = queue.pop(i)
                return await ctx.reply(f"❌ **{removed.title}** removed from the queue")
        await ctx.reply("❌ No matching track found in the queue.")

    @commands.command(name="shuffle", aliases=["sh"])
    async def shuffle(self, ctx: commands.Context):
        """
        Shuffle the queue. If a playlist is loading, schedule shuffle after loading finishes.
        """
        guild_id = ctx.guild.id
        if self.get_loading(guild_id):
            self.set_pending_shuffle(guild_id, True)
            return await ctx.reply("⏳ Loading in progress; will shuffle the queue once done.")
        queue = self.get_queue(guild_id)
        if len(queue) < 2:
            return await ctx.reply("📜 Not enough tracks in the queue to shuffle.")
        random.shuffle(queue)
        await ctx.reply("🔀 Queue shuffled.")

    @commands.command(name="empty")
    async def empty(self, ctx: commands.Context):
        """
        Empty the entire queue (without touching history or currently playing track).
        """
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            return await ctx.reply("📜 The queue is already empty.")
        self.queues[ctx.guild.id] = []
        await ctx.reply("🗑️ Queue emptied.")

    @commands.command(name="previous", aliases=["<<"])
    async def previous(self, ctx: commands.Context):
        """
        Play the previous track (from history). History is limited to 3 tracks.
        Clears any active loop.
        """
        guild_id = ctx.guild.id
        hist = self.get_history(guild_id)
        if not hist:
            return await ctx.reply("❌ No tracks in history yet.")
        prev_track = hist.pop()

        node = wavelink.Pool.get_node()
        player = node.get_player(guild_id)
        if player is None:
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.reply("❌ You must be in a voice channel.")
            player = await ctx.author.voice.channel.connect(cls=wavelink.Player)

        # Clear the loop
        self.set_loop(guild_id, None)

        current = player.current if player and player.current else None
        if current:
            queue = self.get_queue(guild_id)
            queue.insert(0, current)

        self.set_skip_flag(guild_id, True)
        if player.playing or player.paused:
            await player.stop()

        await player.play(prev_track)
        await ctx.reply(f"↩️ Now playing previous track: **{prev_track.title}**")

    @commands.command(name="next", aliases=[">>"])
    async def next(self, ctx: commands.Context):
        """
        Skip to the next track in the queue.
        Clears any active loop.
        """
        guild_id = ctx.guild.id
        played = await self.skip_track(guild_id)
        if played:
            await ctx.reply("⏭️ Skipping to next track…")
        else:
            await ctx.reply("⏭️ No next track; playback stopped or queue is empty.")

    @commands.command(name="playlist", aliases=["pl"])
    async def playlist(self, ctx: commands.Context, *, url: str):
        """
        Add all tracks from a YouTube or Spotify playlist to the queue.
        For Spotify, play the first track immediately and load the rest in the background.
        """
        guild_id = ctx.guild.id
        node = wavelink.Pool.get_node()
        player = node.get_player(guild_id)

        if player is None:
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.reply("❌ You must be in a voice channel to load a playlist.")
            player = await ctx.author.voice.channel.connect(cls=wavelink.Player)

        self.set_loading(guild_id, True)
        self.set_pending_shuffle(guild_id, False)
        await ctx.reply("🔄 Loading playlist… This may take a while if it’s large.")

        added_count = 0

        # ─── YouTube playlist case ─────────────────────────────────────────
        if "youtube.com/playlist" in url or ("youtu.be" in url and "list=" in url):
            tracks = await playlist.load_youtube_playlist(node, url)
            if not tracks:
                self.set_loading(guild_id, False)
                return await ctx.reply("❌ Could not load YouTube playlist.")
            queue = self.get_queue(guild_id)

            for idx, t in enumerate(tracks):
                if idx == 0:
                    await player.play(t)
                    added_count += 1
                else:
                    queue.append(t)
                    added_count += 1

            self.set_loading(guild_id, False)
            if self.get_pending_shuffle(guild_id):
                random.shuffle(self.get_queue(guild_id))
                await ctx.reply("🔀 Queue shuffled after loading (shuffle requested).")

            return await ctx.reply(f"✅ **{added_count}** YouTube playlist track(s) added.")

        # ─── Spotify playlist case ─────────────────────────────────────────
        if "spotify.com" in url and "playlist" in url:
            if not playlist.SPOTIPY_AVAILABLE:
                self.set_loading(guild_id, False)
                return await ctx.reply("❌ Spotipy is not available; cannot load Spotify playlists.")

            match = re.search(r"playlist/([A-Za-z0-9]+)", url)
            if not match:
                self.set_loading(guild_id, False)
                return await ctx.reply("❌ Invalid Spotify playlist URL.")
            playlist_id = match.group(1)

            # ─── Spotify client credentials ───────────────────────────────
            credentials = SpotifyClientCredentials(
                client_id=config.SPOTIPY_CLIENT_ID,
                client_secret=config.SPOTIPY_CLIENT_SECRET
            )
            sp = spotipy.Spotify(auth_manager=credentials)

            response = sp.playlist_items(playlist_id, additional_types=["track"])
            if not response or not response.get("items"):
                self.set_loading(guild_id, False)
                return await ctx.reply("❌ Spotify playlist is empty or not found.")

            first_item = response["items"][0].get("track")
            if not first_item:
                self.set_loading(guild_id, False)
                return await ctx.reply("❌ Could not play the first Spotify track.")
            name = first_item.get("name", "")
            artists = ", ".join(artist["name"] for artist in first_item.get("artists", []))
            search_query = f"{name} {artists}"

            youtube_results = await wavelink.Playable.search(search_query)
            if not youtube_results:
                self.set_loading(guild_id, False)
                return await ctx.reply(f"❌ Could not find on YouTube: **{name}**.")
            first_track = youtube_results[0]

            await player.play(first_track)
            added_count = 1

            queue = self.get_queue(guild_id)

            async def load_rest_of_spotify():
                nonlocal added_count, queue
                items = response["items"][1:]
                for item in items:
                    track_info = item.get("track")
                    if not track_info:
                        continue
                    name2 = track_info.get("name", "")
                    artists2 = ", ".join(artist["name"] for artist in track_info.get("artists", []))
                    query2 = f"{name2} {artists2}"
                    results2 = await wavelink.Playable.search(query2)
                    if results2:
                        queue.append(results2[0])
                        added_count += 1

                next_page = response.get("next")
                current_response = response
                while next_page:
                    response2 = sp.next(current_response)
                    items2 = response2.get("items", [])
                    for item in items2:
                        track_info = item.get("track")
                        if not track_info:
                            continue
                        name3 = track_info.get("name", "")
                        artists3 = ", ".join(artist["name"] for artist in track_info.get("artists", []))
                        query3 = f"{name3} {artists3}"
                        results3 = await wavelink.Playable.search(query3)
                        if results3:
                            queue.append(results3[0])
                            added_count += 1
                    next_page = response2.get("next")
                    current_response = response2

                self.set_loading(guild_id, False)

                if self.get_pending_shuffle(guild_id):
                    random.shuffle(queue)
                    await ctx.reply("🔀 Queue shuffled after loading (shuffle requested).")

                await ctx.reply(f"✅ **{added_count}** Spotify playlist track(s) added.")

            # Launch background task to load the rest of the Spotify tracks
            self.bot.loop.create_task(load_rest_of_spotify())
            return

        # If the URL is neither YouTube nor Spotify playlist
        self.set_loading(guild_id, False)
        return await ctx.reply("❌ Unrecognized URL. Only YouTube (with 'list=') or Spotify playlists are supported.")

    @commands.command(name="help")
    async def help(self, ctx: commands.Context):
        prefix = config.PREFIX
        if isinstance(prefix, (list, tuple)):
            prefix = prefix[0]

        embed = discord.Embed(
            title="🆘 Command Help",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="▶️ play `<query or URL>` `[-loop [count]]`",
            value=(
                "Search and play a YouTube or Spotify track.\n"
                "- If a YouTube link is provided (`youtube.com/watch?v=...` or `youtu.be/...`), play that link.\n"
                "- If a Spotify track link is provided (`open.spotify.com/track/...`), the bot searches YouTube for the equivalent and plays it.\n"
                "- Otherwise, search by title on YouTube.\n"
                "- If a track is already playing, add to the queue.\n"
                "- `-loop 2`: play the track a total of 3 times (initial + 2 loops).\n"
                "- `-loop`: infinite loop.\n"
                "Example: `!play get lucky daft punk -loop 2`\n"
                "Example: `!play https://www.youtube.com/watch?v=dQw4w9WgXcQ -loop`\n"
                "Example: `!play https://open.spotify.com/track/7GhIk7Il098yCjg4BQjzvb`"
            ),
            inline=False
        )
        embed.add_field(
            name="🔄 music (alias resume)",
            value="If the bot was stopped with `!stop`, reconnect and resume the queue; if music is paused, unpause.",
            inline=False
        )
        embed.add_field(
            name="➕ add `<query or URL>` (alias `ad`)",
            value="Search for a track and add it to the queue. If nothing is playing, play immediately.",
            inline=False
        )
        embed.add_field(
            name="📜 queue (alias `qu`)",
            value="Display queue status: history (played), now playing (with 🔁 if looping), and upcoming tracks.",
            inline=False
        )
        embed.add_field(
            name="❌ remove `<title or URL>` (alias `re`/`rm`)",
            value="Remove a track from the queue by matching title or URL.",
            inline=False
        )
        embed.add_field(
            name="🔀 shuffle (alias `sh`)",
            value="Shuffle the queue. If a playlist is loading, shuffle after loading finishes.",
            inline=False
        )
        embed.add_field(
            name="🗑️ empty",
            value="Clear the entire queue (does not affect history or the current track).",
            inline=False
        )
        embed.add_field(
            name="⏸️ pause (alias `=`/`!=`)",
            value="Pause the current track.",
            inline=False
        )
        embed.add_field(
            name="▶️ resume (alias `>`)",
            value="Resume playback if paused (same as `!music`).",
            inline=False
        )
        embed.add_field(
            name="⏭️ next (alias `>>`)",
            value="Skip to the next track in the queue (clears any loop).",
            inline=False
        )
        embed.add_field(
            name="⏹️ stop",
            value="Stop playback and disconnect. Queue remains in memory (loop cleared).",
            inline=False
        )
        embed.add_field(
            name="↩️ previous (alias `<<`)",
            value="Play the previous track from history (up to 3 saved), clears loop.",
            inline=False
        )
        embed.add_field(
            name="🎵 playlist `<YouTube or Spotify URL>` (alias `pl`)",
            value="Add all tracks from a YouTube or Spotify playlist to the queue.",
            inline=False
        )
        embed.set_footer(text=f"Prefix: {prefix}")
        await ctx.reply(embed=embed)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, event):
        logger.info(f"✅ Node ready: {event.node.identifier}")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, event):
        # Log the start of playback; the Player embed is updated elsewhere if used
        logger.info(f"▶️ Track start: {event.track.title}")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, event):
        """
        Handle the end of a track:
        - If skip_flag is True (manual skip), reset it and return.
        - If a loop is active, replay or decrement loop count.
        - Otherwise, add the finished track to history and play the next track in queue.
        """
        guild_id = event.player.guild.id

        if self.get_skip_flag(guild_id):
            self.set_skip_flag(guild_id, False)
            return

        loop_flag = self.get_loop(guild_id)

        # If loop_flag == -1 => infinite loop
        if loop_flag == -1:
            await event.player.play(event.track)
            logger.info(f"🔁 Infinite loop: replaying {event.track.title}")
            return

        # If loop_flag > 0 => finite loop, decrement then replay
        if isinstance(loop_flag, int) and loop_flag > 0:
            self.set_loop(guild_id, loop_flag - 1)
            await event.player.play(event.track)
            logger.info(f"🔁 Loop x{loop_flag} remaining: replaying {event.track.title}")
            return

        # If loop_flag == 0, clear the loop
        if loop_flag == 0:
            self.set_loop(guild_id, None)

        # Add the finished track to history
        finished_track = event.track
        hist = self.get_history(guild_id)
        hist.append(finished_track)
        if len(hist) > 3:
            hist.pop(0)

        # Play the next track if the queue is not empty
        queue = self.get_queue(guild_id)
        if queue:
            next_track = queue.pop(0)
            self.set_skip_flag(guild_id, True)
            await event.player.play(next_track)
            logger.info(f"➔ Playing next track from queue: {next_track.title}")
        else:
            logger.info("📭 Queue is empty, playback ended.")

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, event):
        logger.error(f"❌ Exception on {event.track.title}: {event.exception}")

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")

if __name__ == "__main__":
    bot.run(config.TOKEN)

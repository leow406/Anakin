import re
import wavelink

# Optional for Spotify:
# If you want to support Spotify playlists, install spotipy and set
# SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in config.py or as environment variables.
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False

# If you store your Spotify credentials in config.py, import them here:
import config 

async def load_youtube_playlist(node, playlist_url):
    """
    Load all tracks from a YouTube playlist using Lavalink/Wavelink.
    Returns a list of wavelink.Track if the playlist is loaded, otherwise None.
    Example usage in main.py:
        tracks = await playlist.load_youtube_playlist(node, url)
    """
    # Lavalink will interpret the playlist URL and return a LoadResult
    result = await node.get_tracks(playlist_url)
    if not result or not getattr(result, "tracks", None):
        # No tracks found or the URL wasn't recognized as a playlist
        return None

    return result.tracks


async def load_spotify_playlist(node, playlist_url):
    """
    Load all tracks from a Spotify playlist by searching each track on YouTube.
    Requires spotipy to be installed and config.SPOTIPY_CLIENT_ID / config.SPOTIPY_CLIENT_SECRET to be set.
    Returns a list of corresponding wavelink.Track objects, or None on error / if spotipy is unavailable.
    Example usage in main.py:
        tracks = await playlist.load_spotify_playlist(node, url)
    """
    if not SPOTIPY_AVAILABLE:
        # Spotipy not installed → cannot load Spotify playlists
        return None

    # Extract the Spotify playlist ID from the URL
    match = re.search(r"playlist/([A-Za-z0-9]+)", playlist_url)
    if not match:
        return None
    playlist_id = match.group(1)

    # Instantiate SpotifyClientCredentials with credentials from config.py
    credentials = SpotifyClientCredentials(
        client_id=config.SPOTIPY_CLIENT_ID,
        client_secret=config.SPOTIPY_CLIENT_SECRET
    )
    sp = spotipy.Spotify(auth_manager=credentials)

    tracks_loaded = []

    # Fetch playlist items page by page (100 per page)
    response = sp.playlist_items(playlist_id, additional_types=["track"])
    while response:
        for item in response["items"]:
            track_info = item.get("track")
            if not track_info:
                continue

            # Build the YouTube search query: "Title Artist1, Artist2"
            name = track_info.get("name", "")
            artists = ", ".join(artist["name"] for artist in track_info.get("artists", []))
            search_query = f"{name} {artists}"

            # Search on YouTube (via Wavelink)
            results = await wavelink.Playable.search(search_query)
            if results:
                # Take the first result
                tracks_loaded.append(results[0])

        # Move to the next page if it exists
        if response.get("next"):
            response = sp.next(response)
        else:
            response = None

    return tracks_loaded

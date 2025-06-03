# Anakin

A full-featured Discord bot for playing music directly from YouTube and Spotify playlists, with queue management, looping, simple commands a an interactive player.

------------


## Overview

**Features : **
*Please note that all commands here have the "!" prefix but this can be changed in __config.py__*

------------

### Basic commands usage
#### !play
> Search and play a YouTube track (This does not fully support link yet)
If a track is already playing, add it to the queue

>##### Syntax : 
> `!play <title> -loop [int]`


>#####Arguments : 
> `title` : will search this title on youtube in order to play it
`-loop [int]` : play the track a total of `[int]` times (initial + `[int]` loops)
`-loop` : play the track endlessly

>##### Examples : 

> `!play get lucky daft punk -loop` will play Get Lucky - Daft Punk in loop infintely
`!play home resonance` will play Resonance - home once or add it to the queue
`!play Around the world -loop 3` will play Around the world - Daft Punk 3 times


------------

#### !add
>Search for a track and add it to the queue. If nothing is playing, play immediately.

>##### Syntax : 

>`!add <title>`

>#####Arguments : 
>`title` : will search this title on youtube abd add it to the queue

>##### Example : 
>`!add Rasputin` : will add Rasputin to the queue

------------

#### !queue
>Display queue status: history (played), now playing and upcoming tracks.

>##### Syntax : 
>`!queue`


------------

>#### !remove 
>Remove a track from the queue by matching title

>##### Syntax : 
>`!remove <title>`

>#####Arguments : 
>`title` : will remove this track from the list of upcoming songs

>##### Example : 
>`!remove Every breath you take` will remove Every Breath you take from the list of upcoming songs

------------

#### !shuffle
>Shuffle the queue. If a playlist is loading, shuffle after loading finishes.

>##### Syntax : 
>`!shuffle`

------------

#### !empty
>Clear the entire queue (does not affect history or the current track).
##### Syntax : 
>`!empty`


------------

#### !playlist
>Add all tracks from a YouTube or Spotify playlist to the queue.
>##### Syntax : 
>`!playlist <URL>`

>##### Arguments : 
>`URL` : will list every songs present in the playlist and add them to the queue

>##### Example : 
>`!playlist https://open.spotify.com/playlist/06tCWiOWTnuTfoKwHB8Byl?si=0f2e3c97a6bb472f` will add every track present in this spotify playlist to the queue

------------


### Controls 

>#### !pause 
>Pause the current track until resumed

------------
#### !resume 
>Resume playback if paused (same as !music).

------------
#### !next
>Skip to the next track in the queue (clears any loop).

------------
#### previous
>Play the previous track from history (up to 3 saved), clears loop.

------------
### Bot control

#### !stop
>Stop playback and disconnect. Queue remains in memory (loop cleared).

#### !music/resume
>If the bot was stopped with `!stop`, reconnect and resume the queue; if music is paused, unpause.

---

# Instalation 



You will need a Lavalink server to allow the bot to fetch result from Youtube. You can download the main .jar file here : 
**https://github.com/lavalink-devs/Lavalink/releases/tag/4.0.8**

Once downloaded place the file in the same directory as `application.yml`. You can edit this file to change the port or add plugins but make sure the password mach the one in the `main.py` file


------------



###  Lavalink configuration : 

You can edit multiple lines in `application.yml`
```yaml
server:
  port: 2333 "default 2333"
  address: 0.0.0.0 " to listen on all interfaces"
```

Here you can change the default password and enable/disable the youtube plugin : 
```yaml
lavalink:
  server:
    password: "youshallnotpass"    "need to match LAVA_PASSWORD in the bot code"
    sources:
      youtube: false "disable the default youtube integration"
      youtube-source: true "enable the ytb plugin"
```

Here you can configure the Youtube plugin that allow the bot to fetch results : 
```yaml
plugins:
  youtube:
    enabled: true
    allowSearch: true
    allowDirectVideoIds: true
    allowDirectPlaylistIds: true
```

You also need to enter your OAuth token for the bot to be able de search on youtube. It will be prompted when booting up Lavalink for the first time. You will need to access the said website and enter the code for it to link, justl like with a TV

```yaml

    oauth:
      enabled: true
      refreshToken: "YOUTUBE TOKEN"
      skipInitialization: true
```

When the configuration is ready, you can start Lavalink with a command like this : 

`java -Xms512m -Xmx2048m -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar Lavalink.jar`

I highly recommend running the bot with at least 1Gb of ram but 2Gb is will run smoother


------------

### Bot configuration : 

The `config.py` file is already well explained but to sum up this is where you can add your bot token and the spotify configuration :

```python
TOKEN       = "YOUR BOT TOKEN"
```

To setup the spotify credentials, you will need to create and app on the [Spotify developper page](https://developer.spotify.com/dashboard "Spotify developper page") and enter the given creds here : 

```python
SPOTIPY_CLIENT_ID     = "CLIENT ID"
SPOTIPY_CLIENT_SECRET = "CLIENT SECRET"
```
You will also need to specify in which channel the player will be sent : 
```python
PLAYER_CHANNEL_ID = 123456789123456789

```

------------











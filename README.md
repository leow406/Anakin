# Anakin

A full-featured Discord bot for playing music directly from YouTube and Spotify playlists, with queue management, looping, simple commands a an interactive player.

------------


### Overview

**Features : **
*Please note that all commands here have the "!" prefix but this can be changed in __config.py__*

------------

### Basic commands usage
#### !play
Search and play a YouTube track (This does not fully support link yet)
If a track is already playing, add it to the queue

###### Syntax : 
`!play <title> -loop [int]`


######Arguments : 
`title` : will search this title on youtube in order to play it
`-loop [int]` : play the track a total of `[int]` times (initial + `[int]` loops)
`-loop` : play the track endlessly

###### Examples : 

`!play get lucky daft punk -loop` will play Get Lucky - Daft Punk in loop infintely
`!play home resonance` will play Resonance - home once or add it to the queue
`!play Around the world -loop 3` will play Around the world - Daft Punk 3 times


------------

#### !add
Search for a track and add it to the queue. If nothing is playing, play immediately.

###### Syntax : 

`!add <title>`

######Arguments : 
`title` : will search this title on youtube abd add it to the queue

###### Example : 
`!add Rasputin` : will add Rasputin to the queue

------------

#### !queue
Display queue status: history (played), now playing and upcoming tracks.

###### Syntax : 
`!queue`


------------

#### !remove 
Remove a track from the queue by matching title

###### Syntax : 
`!remove <title>`

######Arguments : 
`title` : will remove this track from the list of upcoming songs

###### Example : 
`!remove Every breath you take` will remove Every Breath you take from the list of upcoming songs

------------

#### !shuffle
Shuffle the queue. If a playlist is loading, shuffle after loading finishes.
###### Syntax : 
`!shuffle`

------------

#### !empty
Clear the entire queue (does not affect history or the current track).
###### Syntax : 
`!empty`


------------

#### !playlist
Add all tracks from a YouTube or Spotify playlist to the queue.
###### Syntax : 
`!playlist <URL>`

###### Arguments : 
`URL` : will list every songs present in the playlist and add them to the queue

###### Example : 
`!playlist https://open.spotify.com/playlist/06tCWiOWTnuTfoKwHB8Byl?si=0f2e3c97a6bb472f` will add every track present in this spotify playlist to the queue

------------


### Controls 

#### !pause 
Pause the current track until resumed

------------
#### !resume 
Resume playback if paused (same as !music).

------------
#### !next
Skip to the next track in the queue (clears any loop).

------------
#### previous
Play the previous track from history (up to 3 saved), clears loop.

------------
### Bot control

#### !stop
Stop playback and disconnect. Queue remains in memory (loop cleared).

#### !music/resume
If the bot was stopped with `!stop`, reconnect and resume the queue; if music is paused, unpause.

---






















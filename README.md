<p align="center">
  <img src="custom_components/noopy_tv/logo@2x.png" alt="OneTV" width="128" height="128">
</p>

<h1 align="center">OneTV for Home Assistant</h1>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
  <img src="https://img.shields.io/github/v/release/Seidel76/noopy-tv-homeassistant" alt="Release">
  <img src="https://img.shields.io/github/license/Seidel76/noopy-tv-homeassistant" alt="License">
</p>

<p align="center">
  Control the OneTV Connect app on your Apple TV from Home Assistant — with automatic discovery.
</p>

---

## What you get

- **Zero configuration** — the app is found over Bonjour/mDNS; you only confirm it
- **A real media player** — transport controls, artwork, progress, channel list, media browser
- **Instant updates** — the app pushes an event stream, so a channel change shows up in well
  under a second; polling stays as a safety net
- **Live EPG** — what is on now, with a progress sensor (percent, title, start, end, minutes
  left, description)
- **Movie and episode progress** — the same sensor reports playback position during VOD
- **App launching** — pair your Apple TV entity and `media_player.turn_on` starts OneTV when
  the app is closed
- **Track selection** — audio and subtitle pickers for whatever is playing
- **Diagnostics** — downloadable from the integration page, with the API key redacted

### Media player

| Control | Notes |
| --- | --- |
| Play / Pause / Stop | |
| Next / Previous track | Moves to the next or previous channel |
| Seek | Bounded content only — a live stream reports no duration |
| Source | The full channel list, in playlist order |
| Browse media | Resume, favorites, channels by category, movies, TV shows |
| Turn on | Launches the app through the paired Apple TV |
| Turn off | Stops playback (tvOS offers no way to quit an app remotely) |

> **No volume controls.** The app's command handler implements neither `setVolume` nor
> `adjustVolume` nor `toggleMute`, so the integration does not advertise them rather than
> showing a slider that does nothing. Use your TV or AV receiver.

Browser thumbnails are served by the integration itself, padded to a square, because Home
Assistant crops them to a circle — a channel logo would otherwise lose its edges.

### Entities

| Entity | What it is |
| --- | --- |
| `media_player.onetv` | The player: state, artwork, transport, source list, browser |
| `sensor.onetv_lecture_en_cours` | Channel, movie or episode currently playing |
| `sensor.onetv_progression_du_programme` | Percent elapsed — the live programme, or the movie |
| `sensor.onetv_statistiques` | Channel and category counts |
| `select.onetv_toutes_les_chaines` | Every channel, plus one selector per category |
| `select.onetv_piste_audio` / `..._sous_titres` | Audio and subtitle tracks |
| `binary_sensor.onetv_application_accessible` | Whether the app answers right now |
| `button.onetv_retour_au_direct` | Back to live — shown only when you are behind |
| `button.onetv_rafraichir` | Force a data refresh |

Prefer `binary_sensor.*_application_accessible` over checking whether other entities are
`unavailable`. Note that the Apple TV's own `app_name` attribute keeps reporting OneTV long
after the app has been suspended.

## Requirements

- The OneTV Connect app running on an Apple TV (tvOS)
- The Home Assistant integration enabled in the app's settings
- Both devices on the same local network

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/Seidel76/noopy-tv-homeassistant` as **Integration**
3. Search for **OneTV**, install, restart Home Assistant
4. The Apple TV is usually discovered on its own; otherwise **Settings → Devices & Services
   → Add Integration**

### Manual

Copy `custom_components/noopy_tv` into your Home Assistant `config/custom_components/`
directory and restart.

## Launching the app

With OneTV closed its HTTP server is down, and the app cannot start itself. Pair an Apple TV
so Home Assistant can launch it:

**Settings → Devices & Services → OneTV → Configure → Paired Apple TV**

The app name must match the entry in the Apple TV's source list exactly (default:
`OneTV Connect`). Once paired, `media_player.turn_on` — and any `play_media` or
`select_source` issued while the app is closed — launches it first, then plays.

## Services

```yaml
# Change channel — by name or by id
action: noopy_tv.play_channel
data:
  channel_id: "TF1"

# Play a movie, optionally resuming
action: noopy_tv.play_movie
data:
  movie_id: "1339713"
  resume_position: 1830

# Play an episode
action: noopy_tv.play_episode
data:
  series_id: "13940"
  season: 1
  episode: 8

# Send a raw player command
action: noopy_tv.send_command
data:
  command: pause

# Force a refresh
action: noopy_tv.refresh
```

> With several Apple TVs configured, these services act on the most recently loaded one.
> To target a specific device, use the `media_player` services on its entity instead —
> `media_player.play_media`, `media_player.select_source`, `media_player.media_pause`.

## Examples

### Now playing card

```yaml
type: vertical-stack
cards:
  - type: media-control
    entity: media_player.onetv
  - type: entities
    entities:
      - entity: sensor.onetv_progression_du_programme
        name: Progress
      - entity: select.onetv_toutes_les_chaines
        name: Channel
```

### Put the TV on when you get home

```yaml
automation:
  - alias: "TV on arrival"
    triggers:
      - trigger: zone
        entity_id: person.me
        zone: zone.home
        event: enter
    actions:
      - action: media_player.turn_on
        target:
          entity_id: media_player.onetv
      - delay: "00:00:10"
      - action: media_player.select_source
        target:
          entity_id: media_player.onetv
        data:
          source: "TF1"
```

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Not discovered | The app is open and its Home Assistant integration is enabled |
| Entities unavailable | The app is closed, or the Apple TV is asleep |
| Connection refused | Both devices are on the same network and subnet |
| Turn on does nothing | No Apple TV paired — see **Launching the app** above |

Debug logging:

```yaml
logger:
  logs:
    custom_components.noopy_tv: debug
```

## License

MIT — see [LICENSE](LICENSE).

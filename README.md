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
  Control your OneTV app directly from Home Assistant with automatic discovery.
</p>

---

## Features

- **Zero Configuration** — Automatic Bonjour/mDNS discovery
- **Media Player Entity** — Full transport controls, artwork, progress bar, source list,
  and media browser for channels, movies and TV shows
- **Instant Updates** — Subscribes to the app's SSE event stream, so a channel change shows
  up in Home Assistant in well under a second (polling stays as a safety net)
- **App Launching** — Pair your Apple TV entity and `media_player.turn_on` starts OneTV when
  the app is closed
- **Live EPG** — Current program, progress, and next program info
- **Channel Logos** — Displayed via local proxy
- **Category Selectors** — One selector per category for quick access
- **Services** — `play_channel`, `play_movie`, `play_episode`, `send_command`, `refresh`

### Media player controls

| Control | Notes |
| --- | --- |
| Play / Pause / Stop | |
| Next / Previous track | Switches to the next/previous channel |
| Seek | Only for bounded content — live streams report no duration |
| Source | The full channel list |
| Browse media | Channels by category, movies, TV shows |
| Turn on | Launches the app through the paired Apple TV |
| Turn off | Stops playback (tvOS gives no way to quit an app remotely) |

> **No volume controls.** The app's command handler does not implement `setVolume`,
> `adjustVolume` or `toggleMute`, so the integration deliberately does not advertise them
> rather than showing a slider that does nothing. Control volume on your TV or AV receiver.

### Launching the app

When OneTV is closed, its HTTP server is down and the integration cannot reach it — the app
has no way to start itself. Pair an Apple TV so Home Assistant can launch it:

**Settings → Devices & Services → OneTV → Configure → Paired Apple TV**

The app name must match the entry in the Apple TV's source list exactly (default:
`OneTV Connect`). Once paired, `media_player.turn_on` — and any `play_media` /
`select_source` call made while the app is closed — launches it first, then plays.

The `binary_sensor.*_application_accessible` entity reports whether the app is currently
reachable. Prefer it over checking whether other entities are `unavailable`, and note that
the Apple TV's own `app_name` attribute keeps reporting OneTV even after the app has been
suspended.

## Requirements

- OneTV app running on Apple TV (tvOS)
- Home Assistant integration enabled in OneTV settings
- Both devices on the same local network

## Installation

### HACS (Recommended)

1. Open HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/Seidel76/noopy-tv-homeassistant` as **Integration**
3. Search for **OneTV** and install
4. Restart Home Assistant
5. Add via **Settings → Devices & Services → Add Integration**

### Manual

Copy `custom_components/noopy_tv` to your Home Assistant `config/custom_components/` directory.

## Entities

| Entity | Description |
|--------|-------------|
| `select.noopy_tv_toutes_les_chaines` | All channels selector with current playback |
| `select.noopy_tv_[category]` | Per-category channel selector |
| `sensor.noopy_tv_statistiques` | Total channels and categories count |
| `sensor.noopy_tv_[channel]` | Per-channel sensor with EPG data |

## Services

```yaml
# Change channel
service: noopy_tv.play_channel
data:
  channel_id: "TF1"

# Force refresh
service: noopy_tv.refresh
```

## Lovelace Examples

### Now Playing Card

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: |
      {% set s = 'select.noopy_tv_toutes_les_chaines' %}
      {% set ch = state_attr(s, 'current_channel') %}
      {% set prog = state_attr(s, 'current_program') %}
      {% set pct = state_attr(s, 'progress_percent') | float(0) | round %}
      {% if ch %}
      ## 📺 {{ ch }}
      **{{ prog }}** — {{ pct }}%
      {% else %}
      *No playback*
      {% endif %}
  - type: entities
    entities:
      - select.noopy_tv_toutes_les_chaines
```

### Automation Example

```yaml
automation:
  - alias: "TV Program Notification"
    trigger:
      - platform: state
        entity_id: sensor.noopy_tv_tf1
    action:
      - service: notify.mobile_app
        data:
          title: "Now on TF1"
          message: "{{ states('sensor.noopy_tv_tf1') }}"
```

## API Reference

OneTV exposes a local REST API at `http://[apple-tv-ip]:8765`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/info` | GET | Server information |
| `/api/v1/channels` | GET | All channels with EPG |
| `/api/v1/categories` | GET | Category list |
| `/api/v1/player` | GET | Current playback status |
| `/api/v1/player/play` | POST | Change channel |
| `/api/v1/proxy/image` | GET | Image proxy for logos |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Not discovered | Ensure OneTV is open and HA integration is enabled |
| Entity unavailable | App closed or Apple TV is sleeping |
| Connection refused | Check both devices are on the same network |

Enable debug logging:

```yaml
logger:
  logs:
    custom_components.noopy_tv: debug
```

## License

MIT License

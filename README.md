<p align="center">
  <img src="custom_components/noopy_tv/logo@2x.png" alt="Noopy TV" width="128" height="128">
</p>

<h1 align="center">Noopy TV for Home Assistant</h1>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
  <img src="https://img.shields.io/github/v/release/Seidel76/noopy-tv-homeassistant" alt="Release">
  <img src="https://img.shields.io/github/license/Seidel76/noopy-tv-homeassistant" alt="License">
</p>

<p align="center">
  Control your Noopy TV app directly from Home Assistant with automatic discovery.
</p>

---

## Features

- **Zero Configuration** — Automatic Bonjour/mDNS discovery
- **Channel Control** — Switch channels directly from Home Assistant
- **Live EPG** — Current program, progress, and next program info
- **Channel Logos** — Displayed via local proxy
- **Category Selectors** — One selector per category for quick access
- **Services** — `noopy_tv.play_channel` and `noopy_tv.refresh`

## Requirements

- Noopy TV app running on Apple TV (tvOS)
- Home Assistant integration enabled in Noopy TV settings
- Both devices on the same local network

## Installation

### HACS (Recommended)

1. Open HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/Seidel76/noopy-tv-homeassistant` as **Integration**
3. Search for **Noopy TV** and install
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

Noopy TV exposes a local REST API at `http://[apple-tv-ip]:8765`:

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
| Not discovered | Ensure Noopy TV is open and HA integration is enabled |
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

# Noopy TV - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

This integration connects Home Assistant to your Noopy TV app. **No manual configuration needed** - Home Assistant automatically discovers Noopy TV on your local network!

🇫🇷 [Version française ci-dessous](#-noopy-tv---intégration-home-assistant)

## ✨ How it works

```
┌─────────────────┐         Auto Discovery         ┌─────────────────┐
│                 │           Bonjour              │                 │
│   Noopy TV      │ ◄──────   (mDNS)   ─────────► │  Home Assistant │
│  (Apple TV)     │                                │                 │
│                 │                                │                 │
│  Local API      │ ──── HTTP localhost:8765 ────► │  Fetches data   │
│  Server         │          /api/v1/*             │                 │
└─────────────────┘                                └─────────────────┘
```

1. **Noopy TV** exposes a local HTTP server on port 8765
2. **Bonjour/mDNS** publishes the `_noopytv._tcp` service for discovery
3. **Home Assistant** automatically detects Noopy TV and fetches data

## 🚀 Features

- ✅ **Auto Discovery** - Home Assistant finds Noopy TV automatically
- ✅ **No credentials needed** - No need to enter your Xtream info
- ✅ **Channel list** - All your channels as sensors
- ✅ **Current program** - Shows the currently playing program
- ✅ **Progress** - Program progress percentage
- ✅ **Channel selector** - Change channels directly from Home Assistant
- ✅ **Now playing** - See what's currently being watched
- ✅ **Channel logos** - Images available
- ✅ **Categories** - Organized by category
- ✅ **Catch-up TV** - Shows which channels have replay

## 📦 Installation

### Noopy TV Side (automatic)

1. Open **Settings** in Noopy TV
2. Enable **Home Assistant** in the Integrations section
3. The server starts automatically

**Important**: Noopy TV must be **open** on your Apple TV for Home Assistant to connect.

### Home Assistant Side

1. Copy the `custom_components/noopy_tv` folder to your `config/custom_components/` directory

```bash
config/
├── custom_components/
│   └── noopy_tv/
│       ├── __init__.py
│       ├── api.py
│       ├── config_flow.py
│       ├── const.py
│       ├── manifest.json
│       ├── select.py
│       ├── sensor.py
│       ├── strings.json
│       └── translations/
```

2. Restart Home Assistant

3. **That's it!** Home Assistant should automatically discover Noopy TV

## 🔍 Auto Discovery

When Noopy TV is open on your Apple TV:

1. Go to **Settings** → **Devices & Services**
2. You should see a "Noopy TV discovered" notification
3. Click **Configure**
4. Confirm the addition

If auto discovery doesn't work, you can add manually:
1. **+ Add Integration**
2. Search for **Noopy TV**
3. Enter your Apple TV's IP address

## 📊 Created Entities

### Channel Selector

`select.noopy_tv_channel_selector`

A dropdown to change channels directly from Home Assistant! Shows:
- All available channels
- Currently watching channel (auto-selected)
- Player status (active/inactive)

### Statistics Sensor

`sensor.noopy_tv_statistics`

| Attribute | Description |
|-----------|-------------|
| `total_channels` | Total number of channels |
| `total_categories` | Number of categories |
| `categories` | List of category names |

### Per-channel Sensors

`sensor.noopy_tv_[channel_name]`

| Attribute | Description |
|-----------|-------------|
| `channel_id` | Channel ID |
| `channel_name` | Channel name |
| `logo_url` | Logo URL |
| `stream_url` | Video stream URL |
| `category` | Category |
| `current_program` | Current program |
| `current_program_start` | Start time |
| `current_program_end` | End time |
| `current_program_description` | Description |
| `progress_percent` | Progress (%) |
| `has_catchup` | Catch-up available |

## 🔧 API exposed by Noopy TV

Noopy TV exposes these endpoints at `http://[apple-tv-ip]:8765`:

| Endpoint | Description |
|----------|-------------|
| `/` | HTML welcome page |
| `/api/v1/info` | Server information |
| `/api/v1/channels` | Channel list with EPG |
| `/api/v1/categories` | Category list |
| `/api/v1/epg` | Full program guide |
| `/api/v1/now` | All current programs |
| `/api/v1/channel/{id}` | Channel details |
| `/api/v1/player` | Player status & current channel |
| `POST /api/v1/player/play` | Change channel |
| `/api/v1/proxy/image?url=` | Image proxy (for logos) |

## 📱 Usage Examples

### Lovelace Card - Now Playing with Logo

The complete card showing the current channel with logo, program, and progress:

```yaml
type: vertical-stack
cards:
  - type: markdown
    title: 📺 Now Playing
    content: |
      {% set channel = state_attr('select.noopy_tv_chaine_tv', 'current_channel') %}
      {% set program = state_attr('select.noopy_tv_chaine_tv', 'current_program') %}
      {% set logo = state_attr('select.noopy_tv_chaine_tv', 'logo_proxy_url') %}
      {% set progress = state_attr('select.noopy_tv_chaine_tv', 'progress_percent') %}
      {% set active = state_attr('select.noopy_tv_chaine_tv', 'player_active') %}
      {% if active and channel %}
      <img src="{{ logo }}" style="max-height: 48px; max-width: 120px; object-fit: contain;" />
      
      ## {{ channel }}
      
      **{{ program | default('Loading...') }}**
      
      ⏱️ Progress: {{ (progress | float(0)) | round(0) }}%
      {% else %}
      *No playback in progress*
      {% endif %}
  - type: entities
    entities:
      - entity: select.noopy_tv_chaine_tv
        name: Change channel
```

### Lovelace Card - Simple Channel Selector

```yaml
type: entities
title: 📺 Noopy TV
entities:
  - entity: select.noopy_tv_chaine_tv
    name: Channel
```

### Lovelace Card - Compact with Progress Bar

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: |
      {% set c = 'select.noopy_tv_chaine_tv' %}
      {% set active = state_attr(c, 'player_active') %}
      {% set channel = state_attr(c, 'current_channel') %}
      {% set program = state_attr(c, 'current_program') %}
      {% set progress = state_attr(c, 'progress_percent') | float(0) | round(0) %}
      
      {% if active and channel %}
      ## 📺 {{ channel }}
      🎬 **{{ program }}**
      
      <progress value="{{ progress }}" max="100" style="width:100%; height:8px; border-radius:4px;"></progress>
      <small>{{ progress }}% complete</small>
      {% else %}
      ## 📵 Player inactive
      *Start a channel on Noopy TV*
      {% endif %}
  - type: entities
    entities:
      - entity: select.noopy_tv_chaine_tv
        name: 📡 Change channel
```

### Lovelace Card - Current Program (per channel)

```yaml
type: entities
title: 📺 Live TV
entities:
  - entity: sensor.noopy_tv_tf1
    secondary_info: attribute
    attribute: current_program
  - entity: sensor.noopy_tv_france_2
    secondary_info: attribute  
    attribute: current_program
```

### Automation - Notification

```yaml
automation:
  - alias: "New program notification"
    trigger:
      - platform: state
        entity_id: sensor.noopy_tv_tf1
    action:
      - service: notify.mobile_app
        data:
          title: "📺 New on TF1"
          message: "{{ states('sensor.noopy_tv_tf1') }}"
```

### Service - Change Channel

```yaml
service: noopy_tv.play_channel
data:
  channel_id: "TF1"  # Channel name or UUID
```

## ⚠️ Limitations

- **App must be open**: Noopy TV must be running on Apple TV for the server to be accessible
- **Local network**: Apple TV and Home Assistant must be on the same network
- **tvOS only**: The server is currently only integrated in the tvOS version

## 🐛 Troubleshooting

### Home Assistant doesn't discover Noopy TV

1. Check that Noopy TV is **open** on Apple TV
2. Check that Home Assistant is enabled in Noopy TV **Settings** → **Integrations**
3. Check that both devices are on the **same network**
4. Try accessing `http://[apple-tv-ip]:8765` in a browser

### Integration shows "unavailable"

This means Noopy TV is no longer accessible:
- App was closed
- Apple TV went to sleep
- Network issue

### Enable debug logs

```yaml
logger:
  default: info
  logs:
    custom_components.noopy_tv: debug
```

## 🤝 Contributing

Contributions are welcome!

## 📄 License

MIT License

---

# 🇫🇷 Noopy TV - Intégration Home Assistant

Cette intégration permet de connecter automatiquement Home Assistant à votre application Noopy TV. **Aucune configuration manuelle n'est nécessaire** - Home Assistant découvre automatiquement Noopy TV sur votre réseau local !

## ✨ Comment ça marche

```
┌─────────────────┐          Découverte          ┌─────────────────┐
│                 │        automatique           │                 │
│   Noopy TV      │ ◄──────  Bonjour  ─────────► │  Home Assistant │
│  (Apple TV)     │         (mDNS)               │                 │
│                 │                              │                 │
│  Expose API     │ ──── HTTP localhost:8765 ──► │  Récupère       │
│  locale         │          /api/v1/*           │  les données    │
└─────────────────┘                              └─────────────────┘
```

1. **Noopy TV** expose un serveur HTTP local sur le port 8765
2. **Bonjour/mDNS** publie le service `_noopytv._tcp` pour la découverte
3. **Home Assistant** détecte automatiquement Noopy TV et récupère les données

## 🚀 Fonctionnalités

- ✅ **Découverte automatique** - Home Assistant détecte Noopy TV tout seul
- ✅ **Aucun identifiant requis** - Pas besoin d'entrer vos infos Xtream
- ✅ **Liste des chaînes TV** - Toutes vos chaînes comme sensors
- ✅ **Programme en cours** - Affiche le programme actuellement diffusé
- ✅ **Progression** - Pourcentage de progression du programme
- ✅ **Sélecteur de chaînes** - Changez de chaîne directement depuis Home Assistant
- ✅ **En cours de lecture** - Voyez ce qui est actuellement regardé
- ✅ **Logos des chaînes** - Images disponibles
- ✅ **Catégories** - Organisation par catégorie
- ✅ **Catch-up TV** - Indication des chaînes avec replay

## 📦 Installation

### Côté Noopy TV (automatique)

1. Ouvrez les **Réglages** dans Noopy TV
2. Activez **Home Assistant** dans la section Intégrations
3. Le serveur démarre automatiquement

**Important** : L'app Noopy TV doit être **ouverte** sur votre Apple TV pour que Home Assistant puisse s'y connecter.

### Côté Home Assistant

1. Copiez le dossier `custom_components/noopy_tv` dans votre dossier `config/custom_components/`

```bash
config/
├── custom_components/
│   └── noopy_tv/
│       ├── __init__.py
│       ├── api.py
│       ├── config_flow.py
│       ├── const.py
│       ├── manifest.json
│       ├── select.py
│       ├── sensor.py
│       ├── strings.json
│       └── translations/
```

2. Redémarrez Home Assistant

3. **C'est tout !** Home Assistant devrait découvrir automatiquement Noopy TV

## 🔍 Découverte automatique

Quand Noopy TV est ouvert sur votre Apple TV :

1. Allez dans **Paramètres** → **Appareils et services**
2. Vous devriez voir une notification "Noopy TV découvert"
3. Cliquez sur **Configurer**
4. Confirmez l'ajout

Si la découverte automatique ne fonctionne pas, vous pouvez ajouter manuellement :
1. **+ Ajouter une intégration**
2. Recherchez **Noopy TV**
3. Entrez l'adresse IP de votre Apple TV

## 📊 Entités créées

### Sélecteur de chaînes

`select.noopy_tv_channel_selector`

Une liste déroulante pour changer de chaîne directement depuis Home Assistant ! Affiche :
- Toutes les chaînes disponibles
- La chaîne en cours de lecture (auto-sélectionnée)
- Le statut du player (actif/inactif)

### Sensor de statistiques

`sensor.noopy_tv_statistiques`

| Attribut | Description |
|----------|-------------|
| `total_channels` | Nombre total de chaînes |
| `total_categories` | Nombre de catégories |
| `categories` | Liste des noms de catégories |

### Sensors par chaîne

`sensor.noopy_tv_[nom_chaine]`

| Attribut | Description |
|----------|-------------|
| `channel_id` | ID de la chaîne |
| `channel_name` | Nom de la chaîne |
| `logo_url` | URL du logo |
| `stream_url` | URL du flux vidéo |
| `category` | Catégorie |
| `current_program` | Programme en cours |
| `current_program_start` | Heure de début |
| `current_program_end` | Heure de fin |
| `current_program_description` | Description |
| `progress_percent` | Progression (%) |
| `has_catchup` | Catch-up disponible |

## 🔧 API exposée par Noopy TV

Noopy TV expose les endpoints suivants sur `http://[ip-apple-tv]:8765` :

| Endpoint | Description |
|----------|-------------|
| `/` | Page d'accueil HTML |
| `/api/v1/info` | Informations sur le serveur |
| `/api/v1/channels` | Liste des chaînes avec EPG |
| `/api/v1/categories` | Liste des catégories |
| `/api/v1/epg` | Guide des programmes complet |
| `/api/v1/now` | Tous les programmes en cours |
| `/api/v1/channel/{id}` | Détails d'une chaîne |
| `/api/v1/player` | Statut du player & chaîne en cours |
| `POST /api/v1/player/play` | Changer de chaîne |
| `/api/v1/proxy/image?url=` | Proxy d'images (pour les logos) |

## 📱 Exemples d'utilisation

### Carte Lovelace - En cours de lecture avec Logo

La carte complète affichant la chaîne en cours avec logo, programme et progression :

```yaml
type: vertical-stack
cards:
  - type: markdown
    title: 📺 En cours de lecture
    content: |
      {% set channel = state_attr('select.noopy_tv_chaine_tv', 'current_channel') %}
      {% set program = state_attr('select.noopy_tv_chaine_tv', 'current_program') %}
      {% set logo = state_attr('select.noopy_tv_chaine_tv', 'logo_proxy_url') %}
      {% set progress = state_attr('select.noopy_tv_chaine_tv', 'progress_percent') %}
      {% set active = state_attr('select.noopy_tv_chaine_tv', 'player_active') %}
      {% if active and channel %}
      <img src="{{ logo }}" style="max-height: 48px; max-width: 120px; object-fit: contain;" />
      
      ## {{ channel }}
      
      **{{ program | default('Chargement...') }}**
      
      ⏱️ Progression : {{ (progress | float(0)) | round(0) }}%
      {% else %}
      *Aucune lecture en cours*
      {% endif %}
  - type: entities
    entities:
      - entity: select.noopy_tv_chaine_tv
        name: Changer de chaîne
```

### Carte Lovelace - Sélecteur simple

```yaml
type: entities
title: 📺 Noopy TV
entities:
  - entity: select.noopy_tv_chaine_tv
    name: Chaîne
```

### Carte Lovelace - Compacte avec barre de progression

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: |
      {% set c = 'select.noopy_tv_chaine_tv' %}
      {% set active = state_attr(c, 'player_active') %}
      {% set channel = state_attr(c, 'current_channel') %}
      {% set program = state_attr(c, 'current_program') %}
      {% set progress = state_attr(c, 'progress_percent') | float(0) | round(0) %}
      
      {% if active and channel %}
      ## 📺 {{ channel }}
      🎬 **{{ program }}**
      
      <progress value="{{ progress }}" max="100" style="width:100%; height:8px; border-radius:4px;"></progress>
      <small>{{ progress }}% terminé</small>
      {% else %}
      ## 📵 Player inactif
      *Lancez une chaîne sur Noopy TV*
      {% endif %}
  - type: entities
    entities:
      - entity: select.noopy_tv_chaine_tv
        name: 📡 Changer de chaîne
```

### Carte Lovelace - Programme en cours (par chaîne)

```yaml
type: entities
title: 📺 TV en direct
entities:
  - entity: sensor.noopy_tv_tf1
    secondary_info: attribute
    attribute: current_program
  - entity: sensor.noopy_tv_france_2
    secondary_info: attribute  
    attribute: current_program
```

### Automatisation - Notification

```yaml
automation:
  - alias: "Notification nouveau programme"
    trigger:
      - platform: state
        entity_id: sensor.noopy_tv_tf1
    action:
      - service: notify.mobile_app
        data:
          title: "📺 Nouveau sur TF1"
          message: "{{ states('sensor.noopy_tv_tf1') }}"
```

### Service - Changer de chaîne

```yaml
service: noopy_tv.play_channel
data:
  channel_id: "TF1"  # Nom ou UUID de la chaîne
```

## ⚠️ Limitations

- **L'app doit être ouverte** : Noopy TV doit être en cours d'exécution sur l'Apple TV pour que le serveur soit accessible
- **Réseau local** : L'Apple TV et Home Assistant doivent être sur le même réseau
- **tvOS uniquement** : Le serveur est pour l'instant uniquement intégré à la version tvOS

## 🐛 Dépannage

### Home Assistant ne découvre pas Noopy TV

1. Vérifiez que Noopy TV est **ouvert** sur l'Apple TV
2. Vérifiez que Home Assistant est activé dans les **Réglages** → **Intégrations** de Noopy TV
3. Vérifiez que les deux appareils sont sur le **même réseau**
4. Essayez d'accéder à `http://[ip-apple-tv]:8765` dans un navigateur

### L'intégration affiche "indisponible"

Cela signifie que Noopy TV n'est plus accessible :
- L'app a été fermée
- L'Apple TV s'est mise en veille
- Problème réseau

### Activer les logs de débogage

```yaml
logger:
  default: info
  logs:
    custom_components.noopy_tv: debug
```

## 🤝 Contribution

Les contributions sont les bienvenues !

## 📄 Licence

MIT License

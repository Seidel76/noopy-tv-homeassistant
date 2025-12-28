# Noopy TV - Intégration Home Assistant

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
- ✅ **Logos des chaînes** - Images disponibles
- ✅ **Catégories** - Organisation par catégorie
- ✅ **Catch-up TV** - Indication des chaînes avec replay

## 📦 Installation

### Côté Noopy TV (automatique)

Le serveur Home Assistant est intégré directement dans Noopy TV. Il démarre automatiquement quand l'app est ouverte.

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

## 📱 Exemples d'utilisation

### Carte Lovelace - Programme en cours

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

### Vérifier si Noopy TV est accessible

```yaml
type: conditional
conditions:
  - entity: sensor.noopy_tv_statistiques
    state_not: "unavailable"
card:
  type: entities
  entities:
    - sensor.noopy_tv_statistiques
```

## ⚠️ Limitations

- **L'app doit être ouverte** : Noopy TV doit être en cours d'exécution sur l'Apple TV pour que le serveur soit accessible
- **Réseau local** : L'Apple TV et Home Assistant doivent être sur le même réseau
- **tvOS uniquement** : Le serveur est pour l'instant uniquement intégré à la version tvOS

## 🐛 Dépannage

### Home Assistant ne découvre pas Noopy TV

1. Vérifiez que Noopy TV est **ouvert** sur l'Apple TV
2. Vérifiez que les deux appareils sont sur le **même réseau**
3. Essayez d'accéder à `http://[ip-apple-tv]:8765` dans un navigateur

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

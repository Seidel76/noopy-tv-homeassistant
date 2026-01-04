from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


@dataclass
class NoopyChannel:
    id: str
    name: str
    stream_url: str | None = None
    logo_url: str | None = None
    category: str | None = None
    tvg_id: str | None = None
    stream_id: int | None = None
    has_catchup: bool = False
    catchup_days: int = 0
    current_program: dict | None = None


@dataclass
class NoopyCategory:
    name: str
    channels_count: int = 0


@dataclass
class NoopyProgram:
    id: str
    title: str
    start: datetime
    end: datetime
    description: str | None = None
    icon_url: str | None = None
    progress_percent: float = 0.0
    
    @property
    def is_current(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.start <= now < self.end


class NoopyTVAPIError(Exception):
    pass


class NoopyTVConnectionError(NoopyTVAPIError):
    pass


class NoopyTVAPI:
    
    def __init__(self, host: str, port: int = 8765, session: aiohttp.ClientSession | None = None) -> None:
        self._host = host
        self._port = port
        self._session = session
        self._own_session = session is None
        self._base_url = f"http://{host}:{port}"
        self._channels: dict[str, NoopyChannel] = {}
        self._categories: list[NoopyCategory] = []
        self._info: dict[str, Any] = {}
    
    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._own_session = True
        return self._session
    
    async def close(self) -> None:
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()
    
    async def _request(self, endpoint: str) -> Any:
        session = await self._ensure_session()
        url = f"{self._base_url}{endpoint}"
        
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    raise NoopyTVAPIError(f"Erreur HTTP {response.status}")
                return await response.json()
        except aiohttp.ClientConnectorError as err:
            raise NoopyTVConnectionError(f"Impossible de se connecter à Noopy TV: {err}") from err
        except aiohttp.ClientError as err:
            raise NoopyTVAPIError(f"Erreur de connexion: {err}") from err
    
    async def get_info(self) -> dict[str, Any]:
        data = await self._request("/api/v1/info")
        self._info = data
        return data
    
    async def test_connection(self) -> bool:
        try:
            info = await self.get_info()
            return info.get("name") == "Noopy TV"
        except NoopyTVAPIError:
            return False
    
    async def get_channels(self) -> list[NoopyChannel]:
        data = await self._request("/api/v1/channels")
        channels_data = data.get("channels", [])
        channels = []
        
        for item in channels_data:
            current_prog = None
            if "current_program" in item:
                prog = item["current_program"]
                current_prog = {
                    "title": prog.get("title"),
                    "start": prog.get("start"),
                    "end": prog.get("end"),
                    "description": prog.get("description"),
                    "icon_url": prog.get("icon_url"),
                    "progress_percent": prog.get("progress_percent", 0),
                }
            
            channel = NoopyChannel(
                id=item.get("id", ""),
                name=item.get("name", ""),
                stream_url=item.get("stream_url"),
                logo_url=item.get("logo_url"),
                category=item.get("category"),
                tvg_id=item.get("tvg_id"),
                stream_id=item.get("stream_id"),
                has_catchup=item.get("has_catchup", False),
                catchup_days=item.get("catchup_days", 0),
                current_program=current_prog,
            )
            channels.append(channel)
            self._channels[channel.id] = channel
        
        _LOGGER.debug("Récupéré %d chaînes depuis Noopy TV", len(channels))
        return channels
    
    async def get_categories(self) -> list[NoopyCategory]:
        data = await self._request("/api/v1/categories")
        categories_data = data.get("categories", [])
        self._categories = [
            NoopyCategory(name=item.get("name", ""), channels_count=item.get("channels_count", 0))
            for item in categories_data
        ]
        return self._categories
    
    async def get_now_playing(self) -> list[dict[str, Any]]:
        data = await self._request("/api/v1/now")
        return data.get("now_playing", [])
    
    async def get_player_status(self) -> dict[str, Any]:
        data = await self._request("/api/v1/player")
        return data
    
    async def play_channel(self, channel_id: str) -> bool:
        session = await self._ensure_session()
        url = f"{self._base_url}/api/v1/player/play"
        
        try:
            async with session.post(url, json={"channel_id": channel_id}, headers={"Content-Type": "application/json"}) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("success", False)
                return False
        except aiohttp.ClientError as err:
            _LOGGER.error("Erreur lors du changement de chaîne: %s", err)
            return False
    
    async def get_channel_detail(self, channel_id: str) -> dict[str, Any] | None:
        try:
            data = await self._request(f"/api/v1/channel/{channel_id}")
            return data
        except NoopyTVAPIError:
            return None
    
    async def refresh_data(self) -> dict[str, Any]:
        channels = await self.get_channels()
        categories = await self.get_categories()
        player_status = await self.get_player_status()
        
        channels_data = {}
        for channel in channels:
            channels_data[channel.id] = {
                "id": channel.id,
                "name": channel.name,
                "logo_url": channel.logo_url,
                "stream_url": channel.stream_url,
                "category": channel.category,
                "tvg_id": channel.tvg_id,
                "stream_id": channel.stream_id,
                "has_catchup": channel.has_catchup,
                "catchup_days": channel.catchup_days,
            }
            
            if channel.current_program:
                channels_data[channel.id].update({
                    "current_program": channel.current_program.get("title"),
                    "current_program_start": channel.current_program.get("start"),
                    "current_program_end": channel.current_program.get("end"),
                    "current_program_description": channel.current_program.get("description"),
                    "current_program_icon": channel.current_program.get("icon_url"),
                    "progress_percent": channel.current_program.get("progress_percent", 0),
                })
        
        return {
            "channels": channels_data,
            "categories": {cat.name: {"name": cat.name, "channels_count": cat.channels_count} for cat in categories},
            "total_channels": len(channels),
            "total_categories": len(categories),
            "player": player_status,
        }
    
    @property
    def channels(self) -> dict[str, NoopyChannel]:
        return self._channels
    
    @property
    def categories(self) -> list[NoopyCategory]:
        return self._categories
    
    @property
    def info(self) -> dict[str, Any]:
        return self._info

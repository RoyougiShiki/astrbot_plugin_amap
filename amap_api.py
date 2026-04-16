"""高德地图 Web 服务 API 封装层

提供天气查询、地理编码/逆地理编码、路线规划（驾车/步行/骑行/公交）、
公交线路查询等功能的异步 HTTP 接口封装。
"""

from typing import Any

import aiohttp

from astrbot.api import logger

# ─── 常量 ────────────────────────────────────────────────

_BASE_URL = "https://restapi.amap.com"

# 路线规划 v3
_WALKING_URL = f"{_BASE_URL}/v3/direction/walking"
_DRIVING_URL = f"{_BASE_URL}/v3/direction/driving"
_TRANSIT_URL = f"{_BASE_URL}/v3/direction/transit/integrated"

# 路线规划 v5（更丰富）
_V5_DRIVING_URL = f"{_BASE_URL}/v5/direction/driving"
_V5_WALKING_URL = f"{_BASE_URL}/v5/direction/walking"
_V5_BICYCLING_URL = f"{_BASE_URL}/v5/direction/bicycling"
_V5_TRANSIT_URL = f"{_BASE_URL}/v5/direction/transit/integrated"

# 天气
_WEATHER_URL = f"{_BASE_URL}/v3/weather/weatherInfo"

# 地理编码
_GEO_URL = f"{_BASE_URL}/v3/geocode/geo"
_REGEO_URL = f"{_BASE_URL}/v3/geocode/regeo"

# 公交查询
_BUS_LINE_NAME_URL = f"{_BASE_URL}/v3/bus/linename"
_BUS_LINE_ID_URL = f"{_BASE_URL}/v3/bus/lineid"
_BUS_STOP_NAME_URL = f"{_BASE_URL}/v3/bus/stopname"
_BUS_STOP_ID_URL = f"{_BASE_URL}/v3/bus/stopid"

# 行政区查询
_DISTRICT_URL = f"{_BASE_URL}/v3/config/district"


class AmapApiError(Exception):
    """高德 API 调用异常"""

    def __init__(self, infocode: str, info: str):
        self.infocode = infocode
        self.info = info
        super().__init__(f"[{infocode}] {info}")


class AmapApi:
    """高德地图 Web 服务 API 异步封装"""

    def __init__(self, api_key: str):
        self._key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ─── 底层请求 ─────────────────────────────────────────

    async def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """发起 GET 请求并校验返回状态"""
        params["key"] = self._key
        params.setdefault("output", "JSON")

        session = await self._get_session()
        try:
            async with session.get(url, params=params) as resp:
                resp.raise_for_status()
                data: dict[str, Any] = await resp.json()
        except aiohttp.ClientError as e:
            logger.error(f"高德 API 请求失败: {e}")
            raise AmapApiError("NETWORK_ERROR", str(e)) from e

        status = data.get("status", "0")
        infocode = data.get("infocode", "UNKNOWN")
        info = data.get("info", "未知错误")

        if status != "1":
            logger.warning(f"高德 API 返回错误: [{infocode}] {info}")
            raise AmapApiError(infocode, info)

        return data

    # ─── 天气查询 ─────────────────────────────────────────

    async def weather(self, city: str, extensions: str = "base") -> dict[str, Any]:
        """查询天气

        Args:
            city: 城市 adcode
            extensions: base=实况天气, all=预报天气
        """
        return await self._request(
            _WEATHER_URL, {"city": city, "extensions": extensions}
        )

    # ─── 地理编码 ─────────────────────────────────────────

    async def geocode(self, address: str, city: str = "") -> dict[str, Any]:
        """地理编码：地址 → 经纬度

        Args:
            address: 结构化地址
            city: 可选，限定城市
        """
        params: dict[str, Any] = {"address": address}
        if city:
            params["city"] = city
        return await self._request(_GEO_URL, params)

    async def regeocode(
        self, location: str, extensions: str = "base", radius: int = 1000
    ) -> dict[str, Any]:
        """逆地理编码：经纬度 → 地址

        Args:
            location: 经度,纬度
            extensions: base=基本信息, all=含 POI
            radius: 搜索半径(米)
        """
        return await self._request(
            _REGEO_URL,
            {"location": location, "extensions": extensions, "radius": str(radius)},
        )

    # ─── 路线规划 (v3) ────────────────────────────────────

    async def walking(self, origin: str, destination: str) -> dict[str, Any]:
        """步行路线规划 (v3, ≤100km)

        Args:
            origin: 起点经度,纬度
            destination: 终点经度,纬度
        """
        return await self._request(
            _WALKING_URL, {"origin": origin, "destination": destination}
        )

    async def driving(
        self,
        origin: str,
        destination: str,
        strategy: int = 10,
        extensions: str = "base",
    ) -> dict[str, Any]:
        """驾车路线规划 (v3)

        Args:
            origin: 起点经度,纬度
            destination: 终点经度,纬度
            strategy: 策略 (10=躲避拥堵+最短时间, 0=速度优先, 等)
            extensions: base/all
        """
        return await self._request(
            _DRIVING_URL,
            {
                "origin": origin,
                "destination": destination,
                "strategy": str(strategy),
                "extensions": extensions,
            },
        )

    async def transit(
        self,
        origin: str,
        destination: str,
        city: str,
        cityd: str = "",
        strategy: int = 0,
        extensions: str = "base",
    ) -> dict[str, Any]:
        """公交路线规划 (v3)

        Args:
            origin: 起点经度,纬度
            destination: 终点经度,纬度
            city: 起点城市(citycode 或城市名)
            cityd: 终点城市(跨城时必填)
            strategy: 0=最快捷, 1=最经济, 2=最少换乘, 3=最少步行, 5=不乘地铁
            extensions: base/all
        """
        params: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "city": city,
            "strategy": str(strategy),
            "extensions": extensions,
        }
        if cityd:
            params["cityd"] = cityd
        return await self._request(_TRANSIT_URL, params)

    # ─── 路线规划 (v5, 更丰富) ────────────────────────────

    async def v5_driving(
        self,
        origin: str,
        destination: str,
        strategy: int = 32,
        show_fields: str = "cost",
    ) -> dict[str, Any]:
        """驾车路线规划 v5

        Args:
            origin: 起点经度,纬度
            destination: 终点经度,纬度
            strategy: 策略编号
            show_fields: 返回字段, 如 cost,tmcs,navi,cities,polyline
        """
        return await self._request(
            _V5_DRIVING_URL,
            {
                "origin": origin,
                "destination": destination,
                "strategy": str(strategy),
                "show_fields": show_fields,
            },
        )

    async def v5_walking(self, origin: str, destination: str) -> dict[str, Any]:
        """步行路线规划 v5"""
        return await self._request(
            _V5_WALKING_URL, {"origin": origin, "destination": destination}
        )

    async def v5_bicycling(self, origin: str, destination: str) -> dict[str, Any]:
        """骑行路线规划 v5"""
        return await self._request(
            _V5_BICYCLING_URL, {"origin": origin, "destination": destination}
        )

    async def v5_transit(
        self,
        origin: str,
        destination: str,
        city1: str,
        city2: str = "",
        strategy: int = 0,
    ) -> dict[str, Any]:
        """公交路线规划 v5

        Args:
            origin: 起点经度,纬度
            destination: 终点经度,纬度
            city1: 起点城市 citycode
            city2: 终点城市 citycode
            strategy: 策略
        """
        params: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "city1": city1,
            "strategy": str(strategy),
        }
        if city2:
            params["city2"] = city2
        return await self._request(_V5_TRANSIT_URL, params)

    # ─── 公交信息查询 ─────────────────────────────────────

    async def bus_line_by_name(
        self, keywords: str, city: str, extensions: str = "base"
    ) -> dict[str, Any]:
        """按名称查询公交线路

        Args:
            keywords: 线路名称关键词
            city: 城市 adcode/citycode
            extensions: base/all(含站点时刻)
        """
        return await self._request(
            _BUS_LINE_NAME_URL,
            {
                "keywords": keywords,
                "city": city,
                "extensions": extensions,
            },
        )

    async def bus_line_by_id(
        self, line_id: str, extensions: str = "base"
    ) -> dict[str, Any]:
        """按 ID 查询公交线路"""
        return await self._request(
            _BUS_LINE_ID_URL, {"id": line_id, "extensions": extensions}
        )

    async def bus_stop_by_name(self, keywords: str, city: str = "") -> dict[str, Any]:
        """按名称查询公交站点"""
        params: dict[str, Any] = {"keywords": keywords}
        if city:
            params["city"] = city
        return await self._request(_BUS_STOP_NAME_URL, params)

    async def bus_stop_by_id(self, stop_id: str) -> dict[str, Any]:
        """按 ID 查询公交站点"""
        return await self._request(_BUS_STOP_ID_URL, {"id": stop_id})

    # ─── 行政区查询 ───────────────────────────────────────

    async def district(
        self, keywords: str = "", subdistrict: int = 1
    ) -> dict[str, Any]:
        """查询行政区信息

        Args:
            keywords: 搜索关键词
            subdistrict: 子级层数(0=不返回, 1=返回下一级, 2=下两级, 3=下三级)
        """
        params: dict[str, Any] = {"subdistrict": str(subdistrict)}
        if keywords:
            params["keywords"] = keywords
        return await self._request(_DISTRICT_URL, params)

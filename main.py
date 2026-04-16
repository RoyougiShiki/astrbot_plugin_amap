"""高德地图 AstrBot 插件

提供天气查询、公交查询、路线规划、地理编码等功能。

命令:
  /amap weather [城市]       查询天气（实况+预报）
  /amap geo <地址>           地理编码（地址→经纬度）
  /amap regeo <经度,纬度>    逆地理编码（经纬度→地址）
  /amap route <方式> <起点> <终点>  路线规划
  /amap bus <线路名> [城市]  查询公交线路
  /amap help                 显示帮助
"""

from __future__ import annotations

from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

from .amap_api import AmapApi, AmapApiError

# ─── 常用城市 adcode 映射 ────────────────────────────────

_CITY_MAP: dict[str, str] = {
    "北京": "110000",
    "上海": "310000",
    "广州": "440100",
    "深圳": "440300",
    "成都": "510100",
    "杭州": "330100",
    "武汉": "420100",
    "南京": "320100",
    "重庆": "500000",
    "天津": "120000",
    "西安": "610100",
    "苏州": "320500",
    "长沙": "430100",
    "郑州": "410100",
    "东莞": "441900",
    "青岛": "370200",
    "昆明": "530100",
    "合肥": "340100",
    "佛山": "440600",
    "沈阳": "210100",
    "济南": "370100",
    "大连": "210200",
    "厦门": "350200",
    "福州": "350100",
    "哈尔滨": "230100",
    "长春": "220100",
    "石家庄": "130100",
    "太原": "140100",
    "贵阳": "520100",
    "南宁": "450100",
    "兰州": "620100",
    "海口": "460100",
    "银川": "640100",
    "西宁": "630100",
    "呼和浩特": "150100",
    "乌鲁木齐": "650100",
    "拉萨": "540100",
}

# citycode 映射（用于公交路线规划 v5）
_CITYCODE_MAP: dict[str, str] = {
    "北京": "010",
    "上海": "021",
    "广州": "020",
    "深圳": "0755",
    "成都": "028",
    "杭州": "0571",
    "武汉": "027",
    "南京": "025",
    "重庆": "023",
    "天津": "022",
    "西安": "029",
    "苏州": "0512",
    "长沙": "0731",
    "郑州": "0371",
    "青岛": "0532",
    "昆明": "0871",
    "合肥": "0551",
    "沈阳": "024",
    "济南": "0531",
    "大连": "0411",
    "厦门": "0592",
    "福州": "0591",
    "哈尔滨": "0451",
    "长春": "0431",
    "石家庄": "0311",
    "太原": "0351",
    "贵阳": "0851",
    "南宁": "0771",
    "兰州": "0931",
    "海口": "0898",
    "银川": "0951",
    "西宁": "0971",
    "呼和浩特": "0471",
    "乌鲁木齐": "0991",
    "拉萨": "0891",
}


def _resolve_adcode(city_input: str, default: str = "110000") -> str:
    """将城市名/adcode 解析为 adcode"""
    if not city_input:
        return default
    if city_input.isdigit() and len(city_input) >= 4:
        return city_input
    return _CITY_MAP.get(city_input, city_input)


def _resolve_citycode(city_name: str) -> str:
    """将城市名解析为 citycode"""
    return _CITYCODE_MAP.get(city_name, "")


def _fmt_duration(seconds: int | str) -> str:
    """格式化时长（秒 → 可读文本）"""
    s = int(seconds)
    if s < 60:
        return f"{s}秒"
    minutes = s // 60
    secs = s % 60
    if minutes < 60:
        return f"{minutes}分{secs}秒" if secs else f"{minutes}分钟"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}小时{mins}分" if mins else f"{hours}小时"


def _fmt_distance(meters: int | str | float) -> str:
    """格式化距离（米 → 可读文本）"""
    m = float(meters)
    if m < 1000:
        return f"{int(m)}米"
    return f"{m / 1000:.1f}公里"


# ─── 插件主体 ─────────────────────────────────────────────


@register(
    "astrbot_plugin_amap",
    "RoyougiShiki",
    "高德地图服务：天气查询、公交查询、路线规划、地理编码",
    "0.1.0",
)
class AmapPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._api_key: str = config.get("amap_api_key", "")
        self._default_city: str = config.get("default_city", "110000")
        self._default_city_name: str = config.get("default_city_name", "北京")
        self._api: AmapApi | None = None

    def _get_api(self) -> AmapApi:
        """获取 API 实例（懒初始化）"""
        if not self._api_key:
            raise AmapApiError(
                "CONFIG_ERROR", "未配置高德 API Key，请在插件配置中填写 amap_api_key"
            )
        if self._api is None:
            self._api = AmapApi(self._api_key)
        return self._api

    # ─── 命令入口 ─────────────────────────────────────────

    @filter.command("amap")
    async def handle_amap(self, event: AstrMessageEvent):
        """高德地图服务"""
        # AstrBot @filter.command 会按空格拆分参数，
        # 所以直接从 message_str 取完整文本，去掉 /amap 前缀
        msg = (event.message_str or "").strip()
        # 兼容不同前缀格式: /amap, /amap xxx
        for prefix in ("/amap ", "/amap"):
            if msg.lower().startswith(prefix):
                remainder = msg[len(prefix) :].strip()
                break
        else:
            remainder = ""

        parts = remainder.split(None, 1)
        subcommand = parts[0].lower() if parts else ""
        argument = parts[1] if len(parts) > 1 else ""

        if not subcommand or subcommand in ("help", "帮助"):
            async for result in self._cmd_help(event):
                yield result
        elif subcommand in ("weather", "天气", "w"):
            async for result in self._cmd_weather(event, argument):
                yield result
        elif subcommand in ("geo", "编码", "地理编码"):
            async for result in self._cmd_geo(event, argument):
                yield result
        elif subcommand in ("regeo", "逆编码", "逆地理编码"):
            async for result in self._cmd_regeo(event, argument):
                yield result
        elif subcommand in ("route", "路线", "导航", "r"):
            async for result in self._cmd_route(event, argument):
                yield result
        elif subcommand in ("bus", "公交", "b"):
            async for result in self._cmd_bus(event, argument):
                yield result
        else:
            yield event.plain_result(
                f"❌ 未知子命令: {subcommand}\n\n"
                "可用命令:\n"
                "  /amap weather [城市]   查询天气\n"
                "  /amap geo <地址>       地理编码\n"
                "  /amap regeo <经度,纬度> 逆地理编码\n"
                "  /amap route <方式> <起点> <终点>  路线规划\n"
                "  /amap bus <线路名> [城市] 查询公交\n"
                "  /amap help             显示帮助"
            )

    # ─── 帮助 ─────────────────────────────────────────────

    async def _cmd_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "🗺️ 高德地图插件\n\n"
            "命令:\n"
            "  /amap weather [城市]        查询天气（实况+预报）\n"
            "  /amap geo <地址>            地址 → 经纬度\n"
            "  /amap regeo <经度,纬度>     经纬度 → 地址\n"
            "  /amap route <方式> <起点> <终点>  路线规划\n"
            "  /amap bus <线路名> [城市]   查询公交线路\n\n"
            "路线方式: drive/驾车, walk/步行, bike/骑行, transit/公交\n\n"
            "示例:\n"
            "  /amap weather 上海\n"
            "  /amap geo 北京市朝阳区阜通东大街6号\n"
            "  /amap regeo 116.481481,39.990464\n"
            "  /amap route drive 北京天安门 北京故宫\n"
            "  /amap route transit 人民广场 陆家嘴\n"
            "  /amap bus 451路 上海"
        )

    # ─── 天气查询 ─────────────────────────────────────────

    async def _cmd_weather(self, event: AstrMessageEvent, city_input: str):
        """查询天气（实况 + 预报）"""
        api = self._get_api()
        city_name = city_input or self._default_city_name
        adcode = _resolve_adcode(city_input, self._default_city)

        try:
            # 实况天气
            data_live = await api.weather(adcode, extensions="base")
            # 预报天气
            data_forecast = await api.weather(adcode, extensions="all")
        except AmapApiError as e:
            yield event.plain_result(f"❌ 天气查询失败: {e}")
            return

        lines: list[str] = [f"🌤️ {city_name} 天气", ""]

        # 实况
        lives = data_live.get("lives", [])
        if lives:
            live = lives[0]
            lines.append("【实况天气】")
            lines.append(f"  天气: {live.get('weather', '-')}")
            lines.append(f"  气温: {live.get('temperature', '-')}°C")
            lines.append(
                f"  风向: {live.get('winddirection', '-')}  风力: {live.get('windpower', '-')}级"
            )
            lines.append(f"  湿度: {live.get('humidity', '-')}%")
            lines.append(f"  更新: {live.get('reporttime', '-')}")
            lines.append("")

        # 预报
        forecasts = data_forecast.get("forecasts", [])
        if forecasts:
            casts = forecasts[0].get("casts", [])
            if casts:
                lines.append("【未来天气预报】")
                for cast in casts[:4]:
                    date = cast.get("date", "")
                    week = cast.get("week", "")
                    day_w = cast.get("dayweather", "-")
                    night_w = cast.get("nightweather", "-")
                    day_t = cast.get("daytemp", "-")
                    night_t = cast.get("nighttemp", "-")
                    lines.append(
                        f"  {date} {week}\n"
                        f"    白天: {day_w} {day_t}°C  夜间: {night_w} {night_t}°C"
                    )

        if len(lines) <= 2:
            lines.append("暂无天气数据")

        yield event.plain_result("\n".join(lines))

    # ─── 地理编码 ─────────────────────────────────────────

    async def _cmd_geo(self, event: AstrMessageEvent, address: str):
        """地址 → 经纬度"""
        if not address:
            yield event.plain_result(
                "❌ 请输入地址，如: /amap geo 北京市朝阳区阜通东大街6号"
            )
            return

        api = self._get_api()
        try:
            data = await api.geocode(address)
        except AmapApiError as e:
            yield event.plain_result(f"❌ 地理编码失败: {e}")
            return

        geocodes = data.get("geocodes", [])
        if not geocodes:
            yield event.plain_result(f"未找到地址: {address}")
            return

        lines: list[str] = [f"📍 地理编码: {address}", ""]
        for i, geo in enumerate(geocodes[:5], 1):
            location = geo.get("location", "")
            province = geo.get("province", "")
            city = geo.get("city", "")
            district = geo.get("district", "")
            street = geo.get("street", "")
            number = geo.get("number", "")
            level = geo.get("level", "")

            full_addr = f"{province}{city}{district}{street}{number}"
            lines.append(f"  [{i}] {full_addr}")
            lines.append(f"      坐标: {location}")
            lines.append(f"      匹配级别: {level}")

        yield event.plain_result("\n".join(lines))

    # ─── 逆地理编码 ───────────────────────────────────────

    async def _cmd_regeo(self, event: AstrMessageEvent, location: str):
        """经纬度 → 地址"""
        if not location:
            yield event.plain_result(
                "❌ 请输入经纬度，如: /amap regeo 116.481481,39.990464"
            )
            return

        # 校验格式
        if "," not in location:
            yield event.plain_result(
                "❌ 格式错误，应为: 经度,纬度（如 116.481481,39.990464）"
            )
            return

        api = self._get_api()
        try:
            data = await api.regeocode(location, extensions="base")
        except AmapApiError as e:
            yield event.plain_result(f"❌ 逆地理编码失败: {e}")
            return

        regeo = data.get("regeocode", {})
        if not regeo:
            yield event.plain_result(f"未找到位置: {location}")
            return

        formatted = regeo.get("formatted_address", "")
        comp = regeo.get("addressComponent", {})

        lines: list[str] = [f"📍 逆地理编码: {location}", ""]
        lines.append(f"  地址: {formatted}")
        lines.append(f"  省份: {comp.get('province', '')}")
        lines.append(f"  城市: {comp.get('city', '')}")
        lines.append(f"  区县: {comp.get('district', '')}")
        lines.append(f"  街道: {comp.get('township', '')}")

        yield event.plain_result("\n".join(lines))

    # ─── 路线规划 ─────────────────────────────────────────

    async def _cmd_route(self, event: AstrMessageEvent, args: str):
        """路线规划

        格式: /amap route <方式> <起点> <终点>
        方式: drive/驾车, walk/步行, bike/骑行, transit/公交
        起点终点可以是地址或经度,纬度
        """
        if not args:
            yield event.plain_result(
                "❌ 请输入路线规划参数\n"
                "格式: /amap route <方式> <起点> <终点>\n"
                "方式: drive/驾车, walk/步行, bike/骑行, transit/公交\n"
                "示例: /amap route drive 北京天安门 北京故宫"
            )
            return

        parts = args.split(None, 2)
        if len(parts) < 3:
            yield event.plain_result("❌ 参数不足，需要: 方式 起点 终点")
            return

        mode_raw, origin_raw, dest_raw = parts[0], parts[1], parts[2]

        # 解析方式
        mode_map = {
            "drive": "driving",
            "驾车": "driving",
            "开车": "driving",
            "walk": "walking",
            "步行": "walking",
            "走路": "walking",
            "bike": "bicycling",
            "骑行": "bicycling",
            "骑车": "bicycling",
            "transit": "transit",
            "公交": "transit",
            "公共交通": "transit",
        }
        mode = mode_map.get(mode_raw.lower())
        if not mode:
            yield event.plain_result(
                f"❌ 未知方式: {mode_raw}\n可选: drive/驾车, walk/步行, bike/骑行, transit/公交"
            )
            return

        api = self._get_api()

        # 解析起终点：如果是地址则先地理编码
        try:
            origin_loc = await self._resolve_location(api, origin_raw)
            dest_loc = await self._resolve_location(api, dest_raw)
        except AmapApiError as e:
            yield event.plain_result(f"❌ 地址解析失败: {e}")
            return

        if not origin_loc or not dest_loc:
            yield event.plain_result(
                "❌ 无法解析起点或终点地址，请尝试更精确的地址或直接使用经纬度"
            )
            return

        try:
            if mode == "walking":
                data = await api.walking(origin_loc, dest_loc)
                text = self._format_walking(data)
            elif mode == "driving":
                data = await api.driving(
                    origin_loc, dest_loc, strategy=10, extensions="base"
                )
                text = self._format_driving(data)
            elif mode == "bicycling":
                data = await api.v5_bicycling(origin_loc, dest_loc)
                text = self._format_bicycling(data)
            elif mode == "transit":
                # 需要城市信息
                city_name = self._default_city_name
                citycode = _resolve_citycode(city_name)
                if not citycode:
                    citycode = "010"  # 默认北京
                data = await api.transit(
                    origin_loc, dest_loc, city=citycode, extensions="base"
                )
                text = self._format_transit(data)
            else:
                text = "❌ 不支持的路线方式"
        except AmapApiError as e:
            yield event.plain_result(f"❌ 路线规划失败: {e}")
            return

        yield event.plain_result(text)

    async def _resolve_location(self, api: AmapApi, text: str) -> str:
        """解析位置文本为经度,纬度字符串

        如果是经纬度格式直接返回，否则做地理编码
        """
        text = text.strip()
        # 检查是否已经是经纬度格式
        if "," in text:
            parts = text.split(",")
            if len(parts) == 2:
                try:
                    lng, lat = float(parts[0]), float(parts[1])
                    if 73 < lng < 136 and 3 < lat < 54:
                        return f"{lng:.6f},{lat:.6f}"
                except ValueError:
                    pass

        # 地理编码
        data = await api.geocode(text)
        geocodes = data.get("geocodes", [])
        if geocodes:
            return geocodes[0].get("location", "")
        return ""

    # ─── 路线结果格式化 ───────────────────────────────────

    def _format_walking(self, data: dict[str, Any]) -> str:
        route = data.get("route", {})
        paths = route.get("paths", [])
        if not paths:
            return "未找到步行路线"

        path = paths[0]
        distance = path.get("distance", "0")
        duration = path.get("duration", "0")

        lines = ["🚶 步行路线规划", ""]
        lines.append(f"  距离: {_fmt_distance(distance)}")
        lines.append(f"  用时: {_fmt_duration(duration)}")
        lines.append("")

        steps = path.get("steps", [])
        if steps:
            lines.append("【路线详情】")
            for i, step in enumerate(steps[:15], 1):
                instruction = step.get("instruction", "")
                step_dist = step.get("distance", "0")
                lines.append(f"  {i}. {instruction} ({_fmt_distance(step_dist)})")

        return "\n".join(lines)

    def _format_driving(self, data: dict[str, Any]) -> str:
        route = data.get("route", {})
        paths = route.get("paths", [])
        if not paths:
            return "未找到驾车路线"

        path = paths[0]
        distance = path.get("distance", "0")
        duration = path.get("duration", "0")

        lines = ["🚗 驾车路线规划", ""]
        lines.append(f"  距离: {_fmt_distance(distance)}")
        lines.append(f"  用时: {_fmt_duration(duration)}")

        taxi_cost = route.get("taxi_cost", "")
        if taxi_cost:
            lines.append(f"  打车约: ¥{taxi_cost}")
        lines.append("")

        steps = path.get("steps", [])
        if steps:
            lines.append("【路线详情】")
            for i, step in enumerate(steps[:20], 1):
                instruction = step.get("instruction", "")
                step_dist = step.get("distance", "0")
                road = step.get("road", "")
                prefix = f"[{road}] " if road else ""
                lines.append(
                    f"  {i}. {prefix}{instruction} ({_fmt_distance(step_dist)})"
                )

        return "\n".join(lines)

    def _format_bicycling(self, data: dict[str, Any]) -> str:
        route = data.get("route", {})
        paths = route.get("paths", [])
        if not paths:
            return "未找到骑行路线"

        path = paths[0]
        distance = path.get("distance", "0")
        duration = path.get("duration", "0")

        lines = ["🚲 骑行路线规划", ""]
        lines.append(f"  距离: {_fmt_distance(distance)}")
        lines.append(f"  用时: {_fmt_duration(duration)}")

        return "\n".join(lines)

    def _format_transit(self, data: dict[str, Any]) -> str:
        route = data.get("route", {})
        transits = route.get("transits", [])
        if not transits:
            return "未找到公交路线"

        distance = route.get("distance", "0")
        lines = ["🚌 公交路线规划", ""]
        lines.append(f"  起终点直线距离: {_fmt_distance(distance)}")
        lines.append("")

        for i, transit in enumerate(transits[:3], 1):
            cost = transit.get("cost", {})
            duration = cost.get("duration", "0")
            walking_dist = transit.get("walking_distance", "0")

            lines.append(f"【方案 {i}】")
            lines.append(
                f"  用时: {_fmt_duration(duration)}  步行: {_fmt_distance(walking_dist)}"
            )

            segments = transit.get("segments", [])
            for j, seg in enumerate(segments[:10], 1):
                bus_info = seg.get("bus", {})
                walking_info = seg.get("walking", {})

                # 步行段
                if walking_info:
                    walk_dist = walking_info.get("distance", "0")
                    if int(walk_dist) > 0:
                        walk_steps = walking_info.get("steps", [])
                        if walk_steps:
                            desc = walk_steps[0].get("instruction", "步行")
                            lines.append(
                                f"    {j}. 🚶 {desc} ({_fmt_distance(walk_dist)})"
                            )

                # 公交段
                if bus_info:
                    buslines = bus_info.get("buslines", [])
                    if buslines:
                        bl = buslines[0]
                        bl_name = bl.get("name", "")
                        dep_stop = bl.get("departure_stop", {}).get("name", "")
                        arr_stop = bl.get("arrival_stop", {}).get("name", "")
                        via_num = bl.get("via_num", "0")
                        lines.append(
                            f"    {j}. 🚌 {bl_name}\n"
                            f"       {dep_stop} → {arr_stop} ({via_num}站)"
                        )

            lines.append("")

        return "\n".join(lines)

    # ─── 公交线路查询 ─────────────────────────────────────

    async def _cmd_bus(self, event: AstrMessageEvent, args: str):
        """查询公交线路信息

        格式: /amap bus <线路名> [城市]
        """
        if not args:
            yield event.plain_result("❌ 请输入公交线路名，如: /amap bus 451路 上海")
            return

        parts = args.split(None, 1)
        line_name = parts[0]
        city_input = parts[1] if len(parts) > 1 else self._default_city_name
        city = _resolve_adcode(city_input, self._default_city)

        api = self._get_api()
        try:
            data = await api.bus_line_by_name(line_name, city, extensions="all")
        except AmapApiError as e:
            yield event.plain_result(f"❌ 公交查询失败: {e}")
            return

        buslines = data.get("buslines", [])
        if not buslines:
            yield event.plain_result(f"未找到公交线路: {line_name}")
            return

        lines: list[str] = [f"🚌 公交线路: {line_name}", ""]

        for i, bl in enumerate(buslines[:5], 1):
            name = bl.get("name", "")
            bl_type = bl.get("type", "")
            start_stop = bl.get("start_stop", "")
            end_stop = bl.get("end_stop", "")
            start_time = bl.get("start_time", "")
            end_time = bl.get("end_time", "")
            basic_price = bl.get("basic_price", "")
            total_price = bl.get("total_price", "")

            lines.append(f"  [{i}] {name}")
            lines.append(f"      类型: {bl_type}")
            lines.append(f"      {start_stop} → {end_stop}")
            if start_time and end_time:
                lines.append(
                    f"      运营: {start_time[:2]}:{start_time[2:]}-{end_time[:2]}:{end_time[2:]}"
                )
            if basic_price:
                price_str = f"¥{basic_price}"
                if total_price and total_price != basic_price:
                    price_str += f"~¥{total_price}"
                lines.append(f"      票价: {price_str}")

            # 站点列表
            busstops = bl.get("busstops", [])
            if busstops:
                stop_names = [s.get("name", "") for s in busstops]
                # 如果站点太多，只显示首尾和中间几个
                if len(stop_names) <= 15:
                    lines.append(f"      站点: {' → '.join(stop_names)}")
                else:
                    first_3 = " → ".join(stop_names[:3])
                    last_3 = " → ".join(stop_names[-3:])
                    lines.append(
                        f"      站点: {first_3} ... {last_3} ({len(stop_names)}站)"
                    )

            lines.append("")

        yield event.plain_result("\n".join(lines))

    # ─── LLM 工具 ─────────────────────────────────────────

    @filter.llm_tool(name="amap_weather")
    async def tool_weather(self, event: AstrMessageEvent, city: str = ""):
        """查询指定城市的天气信息（实况+预报）。用户询问天气时使用。

        Args:
            city(string): 城市名称，如"北京"、"上海"、"深圳"
        """
        async for result in self._cmd_weather(event, city):
            yield result

    @filter.llm_tool(name="amap_route")
    async def tool_route(
        self, event: AstrMessageEvent, mode: str, origin: str, destination: str
    ):
        """路线规划。用户询问如何从A到B时使用。

        Args:
            mode(string): 出行方式: driving/驾车, walking/步行, bicycling/骑行, transit/公交
            origin(string): 起点地址或经度,纬度
            destination(string): 终点地址或经度,纬度
        """
        args = f"{mode} {origin} {destination}"
        async for result in self._cmd_route(event, args):
            yield result

    @filter.llm_tool(name="amap_geocode")
    async def tool_geocode(self, event: AstrMessageEvent, address: str):
        """将地址转换为经纬度坐标。用户需要地址定位时使用。

        Args:
            address(string): 结构化地址，如"北京市朝阳区阜通东大街6号"
        """
        async for result in self._cmd_geo(event, address):
            yield result

    @filter.llm_tool(name="amap_bus_line")
    async def tool_bus_line(
        self, event: AstrMessageEvent, line_name: str, city: str = ""
    ):
        """查询公交线路信息，包括站点、运营时间、票价。用户询问公交信息时使用。

        Args:
            line_name(string): 公交线路名称，如"451路"
            city(string): 城市名称，如"上海"
        """
        args = f"{line_name} {city}" if city else line_name
        async for result in self._cmd_bus(event, args):
            yield result

    # ─── 生命周期 ─────────────────────────────────────────

    async def initialize(self):
        """插件初始化"""
        if not self._api_key:
            logger.warning("高德地图插件: 未配置 API Key，插件将无法正常工作")
        else:
            logger.info("高德地图插件已加载")

    async def terminate(self):
        """插件销毁"""
        if self._api:
            await self._api.close()
        logger.info("高德地图插件已卸载")

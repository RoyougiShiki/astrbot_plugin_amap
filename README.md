# astrbot_plugin_amap

高德地图 AstrBot 插件，提供天气查询、公交查询、路线规划、地理编码等功能。

## 功能

| 命令 | 功能 | 示例 |
|---|---|---|
| `/amap weather [城市]` | 天气查询（实况+预报） | `/amap weather 上海` |
| `/amap geo <地址>` | 地理编码（地址→经纬度） | `/amap geo 天安门` |
| `/amap regeo <经度,纬度>` | 逆地理编码 | `/amap regeo 116.397,39.908` |
| `/amap route <方式> <起点> <终点>` | 路线规划 | `/amap route drive 天安门 故宫` |
| `/amap bus <线路名> [城市]` | 公交线路查询 | `/amap bus 451路 上海` |
| `/amap busstop <站名> [城市]` | 公交站查询（经过的线路） | `/amap busstop 人民广场 上海` |
| `/amap help` | 显示帮助 | `/amap help` |

### 路线规划方式

| 关键字 | 方式 |
|---|---|
| `drive` / `驾车` / `开车` | 驾车 |
| `walk` / `步行` / `走路` | 步行 |
| `bike` / `骑行` / `骑车` | 骑行 |
| `transit` / `公交` / `公共交通` | 公交 |

### LLM 工具

插件注册了 5 个 LLM 工具，AI 可主动调用：

- `amap_weather` — 查询天气
- `amap_route` — 路线规划
- `amap_geocode` — 地理编码
- `amap_bus_line` — 公交线路查询
- `amap_bus_stop` — 公交站查询

## 配置

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `amap_api_key` | 高德地图 Web 服务 API Key | 无（必填） |
| `default_city` | 默认城市 adcode | `110000`（北京） |
| `default_city_name` | 默认城市名称 | `北京` |

### 获取 API Key

1. 注册 [高德开放平台](https://console.amap.com)
2. 创建应用，添加 **Web 服务 API** 类型的 Key
3. 将 Key 填入插件配置

## 安装

在 AstrBot WebUI 插件页点击 `+`，输入仓库地址：

```
https://github.com/RoyougiShiki/astrbot_plugin_amap
```

## 依赖

- aiohttp

## 许可

MIT

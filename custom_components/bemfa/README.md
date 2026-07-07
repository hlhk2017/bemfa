# Bemfa Home Assistant 集成

这是巴法云 Bemfa 的 Home Assistant 自定义集成。本地版本基于原集成继续维护，并加入了同步实体选择体验优化及 `1.4.4` 的 MQTT 兼容修复。

## 本地修改

### 同步实体选择优化

在“设置 -> 设备与服务 -> Bemfa -> 配置 -> 同步实体”中，原版同步实体时只能从所有支持实体中单选，实体多时很难查找。

当前版本调整为：

- 先按设备类型筛选，例如灯、开关、摄像头、二元传感器、环境传感器等。
- 选择实体时支持 Home Assistant 原生搜索。
- 支持一次多选多个实体并批量创建同步。
- 设备类型下拉项已做中文显示，例如“二元传感器”“摄像头”“灯”“环境传感器”“开关”。
- 选择“环境传感器”时显示真正的 `sensor.*` 实体，而不是区域列表。

注意：多选多个实体时，会直接使用 Home Assistant 当前实体名称作为巴法云设备名称；如果只选择一个实体，仍会进入原来的详细配置页面，可以自定义名称或配置空调、传感器等高级选项。

环境传感器会暴露所有 `sensor.*` 实体，不再按 `device_class` 筛选。批量选择时，每个传感器实体会创建为一个巴法云环境传感器设备；如果实体带有湿度、光照、PM2.5 或二氧化碳类别，会自动写入对应字段，其余传感器默认按温度字段同步。原有按区域打包的同步仍可在编辑同步中继续维护。

### 同步上游 1.4.4 修复

已同步 `skddyj/bemfa` `1.4.4` 中与 MQTT 相关的修复：

- `mqtt.Client` 改为关键字参数调用，避免 paho-mqtt 2.x 参数位置歧义。
- `manifest.json` 增加 `loggers` 配置。
- 增加 MQTT 消息接收和解析到 Home Assistant 服务调用的 debug 日志。
- 集成版本号更新为 `1.4.4`。

## 使用方式

1. 将 `custom_components/bemfa` 放入 Home Assistant 配置目录。
2. 重启 Home Assistant。
3. 在“设置 -> 设备与服务”中添加或配置 Bemfa。
4. 进入 Bemfa 的配置菜单，选择“同步实体”。
5. 先选择设备类型，再搜索并选择一个或多个实体。

## 调试日志

如需查看 MQTT 收发和指令解析日志，可在 `configuration.yaml` 中添加：

```yaml
logger:
  default: info
  logs:
    custom_components.bemfa: debug
```

保存后重启 Home Assistant，即可在日志中查看 Bemfa 的调试信息。

## 兼容性说明

- 依赖 `paho-mqtt==2.1.0`。
- 需要通过 Home Assistant 配置流使用。
- 修改后建议重启 Home Assistant，以刷新后端代码和前端翻译缓存。

## 主要文件

- `config_flow.py`: 配置流和选项流，包含实体同步筛选、多选和搜索体验。
- `mqtt.py`: 巴法云 MQTT 连接、订阅、发布和消息接收。
- `sync.py`: 同步抽象和 MQTT 指令解析。
- `manifest.json`: 集成元数据和版本信息。

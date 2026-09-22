# DEV-043 消息推送契约清单

## 目标

为 `DEV-044/045` 建立可复跑的前置红灯，只验证真实源码与契约是否存在，不冒充集成测试。

## 检查清单

| 检查 ID | 对应验收项 | 必须满足的事实 |
| --- | --- | --- |
| backend_parent_module_declared | AC-PUSH-101、AC-PUSH-301 | 后端父 POM 声明 `yunjikeji-module-notification` |
| backend_module_pom_exists | AC-PUSH-101、AC-PUSH-301 | `yunjikeji-module-notification/pom.xml` 存在 |
| backend_admin_controller_exists | AC-PUSH-101、AC-PUSH-301 | 管理端推送控制器存在 |
| backend_app_controller_exists | AC-PUSH-101、AC-PUSH-102 | App 设备绑定/消息中心控制器存在 |
| backend_service_exists | AC-PUSH-101、AC-PUSH-102、AC-PUSH-201 | 消息发送、设备绑定、读开回流 service 存在 |
| backend_push_provider_exists | AC-PUSH-102、AC-PUSH-301 | 后端存在 basename 精确等于 `PushProvider.java`、`NoopPushProvider.java`、`UniCloudHttpPushProvider.java` 的文件，不期待 Java UniPush SDK |
| backend_admin_api_contract_declared | AC-PUSH-101、AC-PUSH-201、AC-PUSH-301 | 后端源码能定位 Admin page/get/create/update/delete/publish/cancel/retry/delivery-page/statistics 契约，且兼容类级+方法级映射 |
| backend_app_api_contract_declared | AC-PUSH-101、AC-PUSH-102、AC-PUSH-301 | 后端源码能定位 App device bind/unbind、message page/{id}/unread/{id}/read/read-all/{id}/open 契约，且兼容类级+方法级映射 |
| admin_ui_push_api_exists | AC-PUSH-101、AC-PUSH-201 | 管理端存在 `page/get/create/update/delete/publish/cancel/retry/delivery-page/statistics` 推送 API 封装 |
| admin_ui_push_view_exists | AC-PUSH-101、AC-PUSH-201 | 管理端存在推送页面或投递明细页面，且命中预设候选路径与明确推送特征 |
| app_service_contract_exists | AC-PUSH-101、AC-PUSH-102 | App 存在 `bind/unbind`、`page`、`/{id}`、`unread`、`/{id}/read`、`read-all`、`/{id}/open` 服务契约 |
| app_message_center_page_registered | AC-PUSH-101 | `pages.json` 已登记消息中心页面 |
| app_push_lifecycle_exists | AC-PUSH-102 | `App.vue` 已接入 `clientId` 与 `onPushMessage` 生命周期 |
| app_manifest_push_config_exists | AC-PUSH-102 | `manifest.json` 出现 UniPush 配置锚点 |
| app_unicloud_push_bridge_exists | AC-PUSH-102、AC-PUSH-301 | App 仓存在 `uniCloud-aliyun/cloudfunctions/yj-push-bridge/index.js` 或等价正式桥接路径 |
| sql_push_tables_exist | AC-PUSH-201、AC-PUSH-301 | 仓库可定位四张推送表：`yj_push_message`、`yj_push_recipient`、`yj_push_device`、`yj_push_delivery` |

## 当前红灯口径

- 2026-08-10 首次执行必须返回 `FAIL`，且原因只能是上述真实缺失实现。
- `PushProvider.java` 需要以 basename 精确独立存在，不能由 `NoopPushProvider.java`、`FooPushProvider.java` 或 `FooBridge.java` 代替。
- App 前端的 `{id}` 是契约占位符，源码可使用 `${id}` 或 `${encodeURIComponent(recordId)}` 等模板表达式；检查必须同时匹配动态表达式前后的固定路径。
- 一旦 `verify_notification_contract.py` 返回 `PASS`，说明可进入后续转绿复验，不代表业务已自动验收通过。

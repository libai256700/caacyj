# UniVerify 一键登录配置

本目录记录小技一键登录的配置边界与部署规则，不保存任何密钥、令牌或证书密码。

## 应用与服务空间

| 项目 | 值 |
| --- | --- |
| App 名称 | 小技 |
| DCloud AppID | `__UNI__F4DBB06` |
| Android 包名 | `com.caacyj.app` |
| uniCloud 服务空间 | `xiaoji` |
| uniCloud SpaceID | `mp-21f9faf6-cfd6-4d33-bbd1-f4c15de5daa6` |
| 云函数 | `code/develop/yunjikeji/uniCloud-aliyun/cloudfunctions/yj-univerify-login` |
| 正式业务服务 | `https://xiaojiapp.caacyj.com/yunjikeji-admin-api` |
| 测试业务服务 | `https://yunjikeji.lai-do.com/yunjikeji-admin-api` |

## 原生配置

- 客户端原生模块配置位于 `code/develop/yunjikeji/src/manifest.json` 的 `app-plus.distribute.sdkConfigs.oauth.univerify`。
- Android 自定义基座或发行包必须使用 `com.caacyj.app`，并在云端打包时勾选 OAuth 的 `univerify` 模块。
- iOS 同样支持 UniVerify；iOS 自定义基座或发行包必须使用 `com.caacyj.app`、有效的开发证书和描述文件，并在云端打包时包含 OAuth 的 `univerify` 模块。Apple 登录配置继续保留。

## 配置位置

| 位置 | 变量 | 用途 |
| --- | --- | --- |
| uniCloud 配置中心 | `univerify.backendBaseUrl` | 业务服务根地址；正式发布使用 `https://xiaojiapp.caacyj.com/yunjikeji-admin-api` |
| uniCloud 配置中心 | `univerify.hmacSecret` | 云函数到业务服务的请求签名密钥 |
| 业务服务 Spring 配置 | `huiyitech.univerify.hmac-secret` | 校验云函数请求签名的共享密钥；配置存在即启用 UniVerify |

uniCloud 配置中心与业务服务 Spring 配置中的 HMAC 值必须相同，长度至少 32 位。业务服务配置必须写在 `application.yaml`（或对应 Spring 配置文件）中，不通过环境变量或启动脚本注入。配置文件应限制访问权限，密钥不允许出现在 Markdown、构建产物、浏览器地址栏、日志或 Git 提交中。

## 发布顺序

1. 在 `uni-config-center` 中配置运行参数，上传公共模块后部署 `yj-univerify-login`。
2. 在业务服务的 Spring 配置文件中配置同一份 HMAC 密钥并重启后端；无需额外启用开关或启动脚本参数。
3. 重新云打包 Android 或 iOS 自定义基座/测试安装包，并安装到具备 SIM 卡和蜂窝网络的设备。
4. 在学员和企业两个角色分别验证一键登录；不支持的网络或设备应自动回退到短信验证码方式。

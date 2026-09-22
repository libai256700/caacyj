# UniVerify 一键登录云函数

此函数只运行在 uniCloud。它使用运营商授权令牌换取手机号，再通过 HMAC 签名请求业务服务；手机号和签名密钥均不会下发到 App。

## 部署前配置

在部署到与 App 绑定的 uniCloud 阿里云服务空间前，在 `uniCloud-aliyun/cloudfunctions/common/uni-config-center/yj-univerify/config.json` 配置运行参数。该文件被 Git 忽略，上传 `uni-config-center` 公共模块后由云函数读取。

| 配置项 | 必填 | 说明 |
| --- | --- | --- |
| `univerify.backendBaseUrl` | 是 | `https://xiaojiapp.caacyj.com/yunjikeji-admin-api` |
| `univerify.hmacSecret` | 是 | 至少 32 位随机值；与业务服务配置文件中的 `huiyitech.univerify.hmac-secret` 完全一致 |
| `univerify.appId` | 否 | 默认 `__UNI__F4DBB06`，仅当 DCloud AppID 变更时设置 |

业务服务只需在 Spring 配置文件的 `huiyitech.univerify` 节点中写入与本文件相同的 `hmac-secret`，配置存在即自动启用；不再依赖环境变量或启动脚本注入配置。

## 发布步骤

1. 在 DCloud uniCloud 控制台申请并审核通过“一键登录”服务，并把本项目 AppID 与 Android 包名关联。
2. 在 HBuilderX 关联 `uniCloud-aliyun` 到该服务空间，先上传 `uni-config-center` 公共模块，再部署 `yj-univerify-login`。
3. 部署业务服务，确保其 Spring 配置文件中的 `huiyitech.univerify.hmac-secret` 与云函数配置相同；无需额外启用开关。
4. 在云端打包时启用 App OAuth 的 `univerify` 模块，重新打包 Android 安装包。

若设备没有有效 SIM 卡、未开启蜂窝数据或运营商预登录失败，客户端不会展示一键登录入口，用户仍可使用短信验证码登录。

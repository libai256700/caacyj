# 移动端签名与打包

| 平台 | 目录 | 用途 |
| --- | --- | --- |
| Android | `Android/` | Android 签名证书、签名信息与应用签名记录 |
| iOS | `iOS/` | iOS 开发证书、描述文件与打包说明 |
| UniVerify | `UniVerify/` | 一键登录的 Android 原生模块、uniCloud 云函数与测试环境配置说明 |

私钥、`.p12` 和 `.mobileprovision` 文件不得提交到 Git。仅允许在本机存放，使用 HBuilderX 本地或云端打包时手动选择。

## Apple 登录测试前置

1. Apple Developer 中为 `com.caacyj.app` 启用 **Sign in with Apple**。
2. 重新生成并下载包含 `com.apple.developer.applesignin` 权限的开发描述文件。
3. 使用对应的开发证书与已注册的真机进行云端自定义基座或发行打包。

## 一键登录测试前置

1. 在 DCloud 控制台审核通过一键登录，并为 `com.caacyj.app` 启用 `univerify` 原生模块。
2. 将 `yj-univerify-login` 部署到项目关联的 uniCloud 服务空间。
3. 在 uniCloud 与测试业务服务分别配置同一份 HMAC 密钥。密钥只能保存在云端环境变量与服务器受控环境文件，不能写入 Git。

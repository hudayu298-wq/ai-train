# 练伴：App 备案准备资料

整理日期：2026-10-18。此文件是项目技术资料草稿，不是已提交订单或审核结论。

## 图标文件（已准备）

备案上传：[`assets/filing/lianban-icon-512.png`](assets/filing/lianban-icon-512.png)，512×512 PNG，不透明，94,236 字节，小于 100KB；图案与应用启动图标一致。高清图与生成说明见 [BRANDING.md](BRANDING.md)。

## 现在需要办理的事项

在华为云备案系统选择 App 备案，按实际身份提交。华为云材料清单包含个人主办者，个人身份不因缺少微信开放平台登录资质而自动失去 App 备案资格；服务内容和地区的具体要求仍以备案审核为准。

App 备案和网站备案分别对应实际服务。仅给 App 提供接口时，不默认要求先办网站备案；若根域名后续开设官网，再按实际网站办理。App 使用 `api.lianbanfit.top`，应在订单中填写该实际子域名，不能只凭根域名注册成功视为完成 App 备案。

## 已有项目参数

| 备案项目 | 当前工程信息 |
|---|---|
| 安装后名称 | 练伴（已更新 Android、iOS、Web 显示名称） |
| 平台 | Android，当前已有构建与真机调试基础 |
| 包名 | com.liftlab.liftlab；正式提交前确认最终包名 |
| 接口域名 | api.lianbanfit.top |
| 根域名 | lianbanfit.top |
| 接入商 | 华为云 |
| 公网 IP | 113.45.193.50 |
| 实际功能 | AI 对话、画像、训练计划、训练记录、饮食记录、姿态检测与提醒 |
| 运行状态 | 云端业务仅监听本机，尚未开放公网；域名尚未备案 |

用途描述建议按实际功能填写：为成年用户提供个人健身计划、训练与饮食记录，以及基于用户提供信息的 AI 辅助建议。不得为适配类目而隐瞒实际功能；服务类目和是否有额外要求由华为云/管局审核确认。

## 当前还缺什么

1. App 显示名称已确定为“练伴”，图标见下方交付文件；包名提交前再次确认。备案名称需与安装后名称一致。
2. 正式安卓签名已生成并通过 release APK 核验，公钥及证书 MD5 已导出。请将本机密钥库与口令配置备份到自己控制的加密存储，保管方式见 [ANDROID_SIGNING.md](ANDROID_SIGNING.md)。
3. 在华为云控制台确认服务器属于可备案资源。官方基本条件包含大陆包周期三个月及以上等要求，不能仅凭已租用服务器假定满足，先检查订单/备案资源校验结果。
4. 核对主办者、华为云账号与域名实名信息的一致性；身份证件、联系电话和人脸核验材料由本人在官方控制台提交。
5. 完善隐私政策、用户协议、联系信息及实际 SDK 清单；当前协议页面仍为内测草案。

本机和服务器都不存放用户提交备案用的身份证照片；无需把身份证件、短信验证码或云账号密码发到聊天。

## 签名状态：正式签名已生成并核验

当前 release 构建使用独立的正式签名，已由 Android apksigner 验证实际 APK，并与本机生成的证书核对一致。安装名称为“练伴”，包名为 `com.liftlab.liftlab`。

- 证书主体：`CN=Lianban Android Signing`
- 算法：RSA-3072 / SHA256withRSA；有效期至 2054-03-05（UTC）。
- 签名 MD5：`EE473B11FBF59CC96EB26CF91334DC92`
- 公钥字段：[RSA 模数十进制](assets/filing/android/lianban-public-key-modulus.txt)，复制整行。
- 三项汇总：[备案复制资料](assets/filing/android/lianban-app-filing.txt)。
- 核验记录：[lianban-app-identity.json](assets/filing/android/lianban-app-identity.json)。

证书指纹与公钥是公开信息，私钥和口令不能提交 Git。签名发生变化可能影响后续覆盖安装与平台身份匹配。最终分发若经应用商店重新签名，需以实际分发签名重新核对备案信息。此 release APK 配置了未来的 HTTPS 接口，备案和公网 HTTPS 尚未完成，构建成功不代表已可联网使用。

## SDK 与模型说明

- 安卓工程集成 ML Kit 姿态检测，用于本地姿态处理，应按实际 SDK 情况申报。
- 工程包含 fluwx/微信 OpenSDK 接入代码，当前微信登录关闭、客户端入口隐藏。正式发布前根据是否保留 SDK 核对申报与隐私清单，不能把“入口隐藏”等同于“APK 未包含 SDK”。
- DeepSeek 通过后端 API 调用；App 不内置该服务的 API 密钥。后端接口调用和移动端嵌入 SDK 是不同技术项，应按平台表单的实际定义填写。
- 相机、通知、文件选择和系统语音等依赖也需在最终发布包的权限/第三方组件清单中核对。

## 已有参考资料

- [华为云 App 备案准备](https://support.huaweicloud.com/prepare-icp/icp_02_0049.html)
- [华为云 App 备案 FAQ](https://support.huaweicloud.com/icp_faq/icp_05_0241.html)
- [特征信息与获取方式](https://support.huaweicloud.com/usermanual-icp/zh-cn_topic_0000002085120221.html)
- [华为云可备案资源限制](https://support.huaweicloud.com/icprb-icp/icp_01_0008.html)
- [HTTPS 部署进度](DOMAIN_SETUP.md)

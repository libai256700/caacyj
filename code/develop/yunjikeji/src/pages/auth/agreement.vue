<template>
  <view id="agreement-page" class="agreement-page" :style="$appSafeAreaStyle">
    <image class="agreement-page__background" :src="loginPrimaryUrl" mode="aspectFill" />
    <view class="agreement-page__shade" />

    <view id="agreement-nav" class="agreement-nav" :style="agreementNavStyle">
      <button class="agreement-nav__back" aria-label="返回" @tap="goBack">
        <text class="agreement-nav__back-icon">‹</text>
      </button>
      <text class="agreement-nav__title">{{ currentAgreement.navTitle }}</text>
    </view>

    <scroll-view id="agreement-scroll" class="agreement-scroll" :style="agreementScrollStyle" scroll-y>
      <view id="agreement-content" class="agreement-card" :style="agreementCardStyle">
        <text class="agreement-title">{{ currentAgreement.title }}</text>

        <view class="agreement-intro">
          <text v-for="paragraph in currentAgreement.intro" :key="paragraph" class="agreement-paragraph">
            {{ paragraph }}
          </text>
        </view>

        <view class="agreement-divider" />

        <view v-for="section in currentAgreement.sections" :key="section.title" class="agreement-section">
          <text class="agreement-section__title">{{ section.title }}</text>
          <view class="agreement-section__body">
            <view v-for="(item, index) in section.items" :key="item" class="agreement-item">
              <text class="agreement-item__marker">{{ index + 1 }}.</text>
              <text class="agreement-item__text">{{ item }}</text>
            </view>
          </view>
        </view>

        <view class="agreement-note">
          <view class="agreement-note__icon">
            <image class="agreement-note__icon-image" src="/static/agreement/notice-shield.png" mode="aspectFit" />
          </view>
          <view class="agreement-note__copy">
            <text v-for="line in currentAgreement.notice" :key="line" class="agreement-note__line">{{ line }}</text>
          </view>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onReady } from '@dcloudio/uni-app'
import { getSafeAreaInsets } from '@/utils/safeArea'
import loginPrimaryUrl from '@/static/backgrounds/login-primary.png'

type AgreementType = 'user' | 'privacy'

type AgreementSection = {
  title: string
  items: string[]
}

type AgreementContent = {
  navTitle: string
  title: string
  intro: string[]
  sections: AgreementSection[]
  notice: string[]
}

const agreementType = ref<AgreementType>('user')
const safeAreaTop = ref(0)

const agreementNavStyle = computed(() => ({
  height: `calc(${safeAreaTop.value}px + 118rpx)`,
  paddingTop: `${safeAreaTop.value}px`
}))

const agreementScrollStyle = computed(() => ({
  height: `calc(100vh - ${safeAreaTop.value}px - 118rpx)`
}))

const agreementCardStyle = computed(() => ({
  minHeight: `calc(100vh - ${safeAreaTop.value}px - 164rpx)`
}))

function syncSafeAreaTop() {
  safeAreaTop.value = Math.ceil(getSafeAreaInsets().top)
}

const agreements: Record<AgreementType, AgreementContent> = {
  user: {
    navTitle: '用户服务协议',
    title: '用户服务协议',
    intro: [
      '欢迎您使用小技（以下简称“小技”或“我们”）提供的无人机学习、训练、测评与相关服务。',
      '版本号：1.0.3；生效日期：2026年8月30日。请您在注册、登录或使用服务前仔细阅读本《用户服务协议》（以下简称“本协议”）。',
      '您点击“同意”或开始使用小技，即表示您已理解并接受本协议及《隐私政策》。如您不同意，请停止注册或使用相关服务。'
    ],
    sections: [
      {
        title: '一、协议的确认与接受',
        items: [
          '本协议约定您与小技之间使用服务时的权利、义务和责任边界。',
          '如您未满18周岁，请在监护人阅读并同意本协议后使用服务；监护人应对未成年人使用服务进行合理指导。',
          '我们会在法律法规要求或服务发生重要变化时更新本协议，并通过应用内页面或合理方式提示您。'
        ]
      },
      {
        title: '二、账号与登录',
        items: [
          '手机号是注册、登录和识别同一用户所必需的信息。您可按照页面提示使用短信验证码或本机号码一键登录。',
          '请使用本人手机号并妥善保管登录凭证，不得出借、出售、转让或以其他方式允许他人使用您的账号。',
          '发现账号异常或他人未经授权使用时，请及时通过应用内客服入口联系我们。'
        ]
      },
      {
        title: '三、课程学习、训练与考证服务说明',
        items: [
          '小技提供的课程、练习、测评、岗位信息及其他内容以页面展示为准，供学习和训练参考。',
          '实际飞行、训练和考试报名应遵守适用的法律法规、行业规则、场地管理要求及教员、安全人员的指引。',
          '培训结果、考试资格、证书取得及岗位录用由相应培训机构、考试机构、主管部门或招聘单位依其规则独立决定，小技不作通过、取证或录用承诺。',
          '需要预约、报名或提交资料的服务，以对应页面展示的条件、流程和提示为准。'
        ]
      },
      {
        title: '四、使用规则与安全',
        items: [
          '您不得利用小技发布、传播或协助实施违法违规、欺诈、侵权、危害飞行安全或损害他人合法权益的内容或行为。',
          '进行线下实操时，请遵守禁飞、限飞、场地、设备和天气等安全要求；在不具备安全条件时不得开展飞行活动。',
          '您通过小技提交的文字、图片、视频或其他资料应当合法、真实且不侵犯他人权益；因您提交内容引发的争议由您依法承担相应责任。'
        ]
      },
      {
        title: '五、服务内容与知识产权',
        items: [
          '小技中的课程、题目、图文、视频、软件界面、标识及其他内容受法律保护。除法律允许或我们另行授权外，您不得复制、出售、出租、传播、改编或用于商业用途。',
          '您为使用个人资料、测评、企业入驻或客服功能而主动提交的内容，仅用于提供对应服务、处理请求或保障服务安全；具体个人信息处理规则以《隐私政策》为准。'
        ]
      },
      {
        title: '六、服务变更、暂停与终止',
        items: [
          '我们可能基于服务运营、法律法规、技术维护或安全需要调整、暂停或终止部分服务，并在合理范围内向您提示。',
          '如您违反本协议、法律法规或服务规则，我们可视情节采取提醒、限制功能、暂停或终止服务等措施。',
          '您可以停止使用服务；如需注销账号或处理个人信息相关请求，请通过应用内客服入口提交。'
        ]
      },
      {
        title: '七、免责声明与责任限制',
        items: [
          '在法律允许的范围内，因不可抗力、网络与通信故障、第三方服务异常、系统维护或其他非我们可合理控制的原因导致服务中断或延迟，我们将尽力恢复，但不承担由此产生的间接损失。',
          '小技提供的学习和训练内容不替代现场安全管理、飞行许可审查、专业教员指导或考试机构的正式要求。'
        ]
      },
      {
        title: '八、适用法律与争议解决',
        items: [
          '本协议的订立、效力、解释、履行及争议解决适用中华人民共和国法律。',
          '发生争议时，您可先通过应用内客服入口与我们沟通；协商不成的，双方可依法向有管辖权的人民法院提起诉讼。'
        ]
      }
    ],
    notice: [
      '本协议于2026年8月30日生效。',
      '感谢您选择小技，请在安全、合法的前提下开展学习和训练。'
    ]
  },
  privacy: {
    navTitle: '隐私协议',
    title: '隐私协议',
    intro: [
      '小技重视您的个人信息与隐私安全，并遵循合法、正当、必要和诚信原则处理个人信息。',
      '版本号：1.0.3；生效日期：2026年8月30日。手机号是注册和登录所必需的信息；其余信息仅在您主动使用相应功能时按需处理。'
    ],
    sections: [
      {
        title: '一、我们收集的信息',
        items: [
          '手机号：仅在您注册或登录时收集，用于创建账号、登录验证和识别同一用户。这是使用账号服务所必需的信息。',
          '个人资料：您主动设置昵称、上传头像时，我们处理相应的昵称和头像图片，用于在您的个人资料页展示。',
          '测评资料：您主动进入自我测评并提交资料时，我们处理姓名、手机号以及您自愿填写的身份证号、毕业院校和专业，用于生成和保存您的测评资料及结果。',
          '企业入驻资料：您选择企业注册时，我们处理您提交的企业名称、统一社会信用代码、法人和联系人资料、营业执照图片，用于审核企业入驻申请。',
          '客服资料：您主动向客服发送文字、图片或视频时，我们处理您提交的内容，用于回复、跟进和解决您的问题。',
          '一键登录结果：您选择本机号码一键登录时，我们接收用于完成账号验证的认证结果和手机号；该功能由 Uni-Verify 及相应运营商提供。'
        ]
      },
      {
        title: '二、我们如何使用信息',
        items: [
          '我们使用手机号完成账号注册、登录验证、账号安全和必要的服务通知，不将其用于与账号服务无关的目的。',
          '我们仅在您主动使用资料编辑、测评、企业入驻或客服功能时，使用相应资料提供该项服务。',
          '我们不会将您的个人信息出售给任何第三方，也不会以您的个人信息为基础进行与服务无关的营销。'
        ]
      },
      {
        title: '三、权限与第三方服务',
        items: [
          '您主动选择头像、营业执照或客服媒体时，应用会在当次操作中请求相册或相机权限；您拒绝授权不影响手机号登录等不依赖该权限的功能。',
          '短信验证码由阿里云短信服务发送；本机号码一键登录由 Uni-Verify 和相应运营商完成认证；您主动上传的图片、视频或资料会使用云存储服务保存。我们仅向这些服务提供完成相应功能所必需的信息，并要求其按约定保护信息。',
          '除上述为实现功能所必需的情形外，未经您的同意，我们不会向其他组织、个人共享您的个人信息；法律法规另有规定的除外。'
        ]
      },
      {
        title: '四、保存与保护',
        items: [
          '我们在实现对应服务所需的期限内保存个人信息；法律法规要求保存的，按其规定执行。',
          '我们采取访问控制、传输保护、权限管理等合理措施，降低信息被未经授权访问、披露、篡改或丢失的风险。'
        ]
      },
      {
        title: '五、您的权利',
        items: [
          '您可在应用内查看或修改昵称、头像等个人资料；也可通过应用内客服入口申请查询、更正、删除个人信息、注销账号或撤回已授权的可选权限。',
          '我们会在核验您的身份后处理您的请求；法律法规规定的例外情形除外。'
        ]
      },
      {
        title: '六、未成年人信息保护',
        items: [
          '若您未满18周岁，请在监护人同意和指导下使用小技。',
          '监护人可通过应用内客服入口就未成年人个人信息提出查询、更正、删除或其他合理请求。'
        ]
      },
      {
        title: '七、政策更新与联系我们',
        items: [
          '我们可能因法律法规、产品功能或信息处理方式变化更新本政策，并在生效前通过应用内页面或合理方式提示您。',
          '如您对本政策有疑问、意见或个人信息请求，请通过“我的 - 客服中心”联系小技客服。'
        ]
      }
    ],
    notice: [
      '手机号是唯一必需的账号信息；其余资料均在您主动使用对应功能时处理。',
      '本政策于2026年8月30日生效。感谢您信任小技。'
    ]
  }
}

const currentAgreement = computed(() => agreements[agreementType.value])

onLoad((query) => {
  const type = typeof query?.type === 'string' ? query.type : ''
  agreementType.value = type === 'privacy' ? 'privacy' : 'user'
  syncSafeAreaTop()
})

onReady(() => {
  syncSafeAreaTop()
})

function goBack() {
  const pages = getCurrentPages()
  if (pages.length > 1) {
    uni.navigateBack()
    return
  }

  uni.reLaunch({
    url: '/pages/auth/login'
  })
}
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #edf7ff;
}

button::after {
  border: 0;
}

.agreement-page {
  position: relative;
  box-sizing: border-box;
  min-height: 100vh;
  padding: 0;
  overflow: hidden;
  color: #142544;
  background: #eef6ff;
}

.agreement-page__background,
.agreement-page__shade {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.agreement-page__background {
  z-index: 0;
  top: -100rpx;
  height: calc(100% + 100rpx);
}

.agreement-page__shade {
  z-index: 1;
  background:
    radial-gradient(circle at 42% 25%, rgba(255, 255, 255, 0.25) 0, rgba(255, 255, 255, 0) 30%),
    linear-gradient(180deg, rgba(247, 252, 255, 0.28) 0%, rgba(247, 252, 255, 0.56) 45%, rgba(247, 252, 255, 0.86) 100%);
  pointer-events: none;
}

.agreement-nav {
  position: relative;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  height: calc(env(safe-area-inset-top) + 118rpx);
  padding: env(safe-area-inset-top) 42rpx 0;
}

.agreement-nav__back {
  position: absolute;
  left: 28rpx;
  bottom: 10rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72rpx;
  height: 72rpx;
  margin: 0;
  padding: 0;
  border-radius: 50%;
  background: transparent;
  color: #0b66d8;
  line-height: 1;
}

.agreement-nav__back-icon {
  display: block;
  margin-top: -4rpx;
  font-size: 82rpx;
  line-height: 0.72;
  font-weight: 280;
}

.agreement-nav__title {
  max-width: 520rpx;
  overflow: hidden;
  color: #061936;
  font-size: 38rpx;
  line-height: 1.25;
  font-weight: 800;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agreement-scroll {
  position: relative;
  z-index: 3;
  box-sizing: border-box;
  height: calc(100vh - env(safe-area-inset-top) - 118rpx);
  padding: 34rpx 24rpx calc(env(safe-area-inset-bottom) + 24rpx);
}

.agreement-card {
  box-sizing: border-box;
  width: 100%;
  min-height: calc(100vh - env(safe-area-inset-top) - 164rpx);
  padding: 44rpx 40rpx 34rpx;
  border: 1rpx solid rgba(255, 255, 255, 0.78);
  border-radius: 30rpx;
  background: rgba(255, 255, 255, 0.88);
  box-shadow:
    0 20rpx 58rpx rgba(57, 100, 145, 0.11),
    inset 0 1rpx 0 rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10rpx);
}

.agreement-title {
  display: block;
  color: #061936;
  font-size: 54rpx;
  line-height: 1.14;
  font-weight: 900;
}

.agreement-intro {
  margin-top: 30rpx;
}

.agreement-paragraph {
  display: block;
  margin-top: 12rpx;
  color: #526680;
  font-size: 24rpx;
  line-height: 1.82;
}

.agreement-divider {
  height: 2rpx;
  margin: 34rpx 0 30rpx;
  background-image: linear-gradient(90deg, rgba(38, 122, 218, 0.16) 0 50%, rgba(255, 255, 255, 0) 50% 100%);
  background-size: 12rpx 2rpx;
}

.agreement-section {
  margin-top: 28rpx;
}

.agreement-section__title {
  display: block;
  color: #0862c8;
  font-size: 28rpx;
  line-height: 1.35;
  font-weight: 820;
}

.agreement-section__body {
  margin-top: 12rpx;
}

.agreement-item {
  display: flex;
  align-items: flex-start;
  gap: 12rpx;
  margin-top: 7rpx;
}

.agreement-item__marker {
  flex: 0 0 auto;
  min-width: 30rpx;
  color: #273d5c;
  font-size: 23rpx;
  line-height: 1.72;
}

.agreement-item__text {
  flex: 1;
  min-width: 0;
  color: #344962;
  font-size: 23rpx;
  line-height: 1.72;
}

.agreement-note {
  display: flex;
  align-items: center;
  gap: 18rpx;
  box-sizing: border-box;
  margin-top: 38rpx;
  padding: 22rpx 24rpx;
  border: 1rpx solid rgba(68, 160, 248, 0.34);
  border-radius: 12rpx;
  background: rgba(237, 247, 255, 0.78);
}

.agreement-note__icon {
  display: flex;
  flex: 0 0 54rpx;
  align-items: center;
  justify-content: center;
  width: 54rpx;
  height: 54rpx;
}

.agreement-note__icon-image {
  display: block;
  width: 46rpx;
  height: 46rpx;
}

.agreement-note__copy {
  flex: 1;
  min-width: 0;
}

.agreement-note__line {
  display: block;
  color: #1674df;
  font-size: 22rpx;
  line-height: 1.58;
  font-weight: 650;
}

@media screen and (min-width: 768px) {
  .agreement-nav,
  .agreement-scroll {
    max-width: 945px;
    margin-right: auto;
    margin-left: auto;
  }

  .agreement-card {
    padding: 64rpx 56rpx 36rpx;
  }
}

@media screen and (max-width: 360px) {
  .agreement-scroll {
    padding-top: 34rpx;
    padding-right: 22rpx;
    padding-left: 22rpx;
  }

  .agreement-card {
    padding-right: 34rpx;
    padding-left: 34rpx;
  }

  .agreement-title {
    font-size: 50rpx;
  }
}
</style>

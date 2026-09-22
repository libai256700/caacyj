<script setup lang="ts">
import { onLaunch, onShow, onHide } from "@dcloudio/uni-app";
import { applySafeAreaVariables } from '@/utils/safeArea'
import { prepareUniverify } from '@/utils/univerify'

const syncSafeAreaVariables = () => {
  applySafeAreaVariables()
  setTimeout(applySafeAreaVariables, 300)
  setTimeout(applySafeAreaVariables, 1000)
}

onLaunch(() => {
  console.log("App Launch");
  syncSafeAreaVariables()
  // Start the carrier SDK before the login page becomes interactive. This
  // avoids the transient 30001 error that can occur on a cold app start.
  // #ifdef APP-PLUS
  void prepareUniverify()
  // #endif
  if (typeof document !== 'undefined') {
    document.addEventListener('plusready', syncSafeAreaVariables, { once: true })
  }
});
onShow(() => {
  console.log("App Show");
  syncSafeAreaVariables()
});
onHide(() => {
  console.log("App Hide");
});
</script>
<style lang="scss">
@use "@climblee/uv-ui/index.scss";

:root {
  --app-safe-top: 0px;
  --app-safe-right: 0px;
  --app-safe-bottom: 0px;
  --app-safe-left: 0px;
}

page,
html,
body,
#app {
  --app-safe-area-top: env(safe-area-inset-top);
  --app-safe-area-top-extra: max(0px, calc(var(--app-safe-area-top) - 44rpx));
  --app-page-header-height: 60rpx;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

page::-webkit-scrollbar,
html::-webkit-scrollbar,
body::-webkit-scrollbar,
#app::-webkit-scrollbar,
*::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}

.uni-tabbar__label {
  font-weight: 700;
}

.uni-tabbar {
  display: none !important;
  overflow: visible !important;
  left: 32rpx !important;
  right: 32rpx !important;
  bottom: 0 !important;
  width: auto !important;
  height: 128rpx !important;
  padding-top: 16rpx !important;
  padding-bottom: calc(env(safe-area-inset-bottom) + 18rpx) !important;
  border-radius: 28rpx 28rpx 0 0 !important;
  background: #ffffff !important;
  box-shadow: 0 -12rpx 36rpx rgba(58, 83, 111, 0.12) !important;
}

.uni-tabbar::before {
  display: none !important;
}

.uni-tabbar::after {
  display: none !important;
}

.uni-tabbar-border {
  display: none !important;
}

.uni-tabbar__item {
  height: 104rpx !important;
}

.uni-tabbar__bd {
  height: 104rpx !important;
  justify-content: center !important;
}

.uni-tabbar__icon {
  width: 50rpx !important;
  height: 50rpx !important;
}

.uni-tabbar__label {
  margin-top: 8rpx !important;
  font-size: 28rpx !important;
  line-height: 1.25 !important;
}
</style>

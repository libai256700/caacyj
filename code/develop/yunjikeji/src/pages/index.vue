<template>
  <view class="launch-page" :style="$appSafeAreaStyle"></view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { appState } from '@/stores/appState'

const hasRedirected = ref(false)

onShow(() => {
  if (hasRedirected.value) {
    return
  }

  hasRedirected.value = true

  if (!appState.userSession) {
    uni.reLaunch({
      url: '/pages/auth/login'
    })
    return
  }

  uni.reLaunch({
    url: '/pages/home'
  })
})
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #F4F8FC;
}

.launch-page {
  min-height: 100vh;
  background: #F4F8FC;
}
</style>

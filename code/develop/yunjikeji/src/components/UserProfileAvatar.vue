<template>
  <image class="user-profile-avatar" :src="normalizedAvatarId" mode="aspectFill" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { normalizeProfileAvatarId } from '@/utils/profileAvatar'

const props = defineProps<{
  avatarId?: string
}>()

const normalizedAvatarId = computed(() => normalizeProfileAvatarId(props.avatarId))
</script>

<style scoped lang="scss">
.user-profile-avatar {
  display: block;
  box-sizing: border-box;
  overflow: hidden;
  border-radius: 50%;
}
</style>

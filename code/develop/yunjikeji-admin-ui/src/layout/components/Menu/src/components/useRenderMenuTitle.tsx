import type { RouteMeta } from 'vue-router'
import { Icon } from '@/components/Icon'
import { useI18n } from '@/hooks/web/useI18n'

export const useRenderMenuTitle = () => {
  const renderMenuTitle = (meta: RouteMeta) => {
    const { t } = useI18n()
    const { title = '', icon } = meta
    const menuTitle = title ? t(title as string) : ''

    return icon ? (
      <>
        <Icon icon={meta.icon}></Icon>
        {menuTitle ? (
          <span class="v-menu__title overflow-hidden overflow-ellipsis whitespace-nowrap">
            {menuTitle}
          </span>
        ) : undefined}
      </>
    ) : (
      menuTitle ? (
        <span class="v-menu__title overflow-hidden overflow-ellipsis whitespace-nowrap">
          {menuTitle}
        </span>
      ) : undefined
    )
  }

  return {
    renderMenuTitle
  }
}

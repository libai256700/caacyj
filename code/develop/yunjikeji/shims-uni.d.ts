/// <reference types='@dcloudio/types' />
import 'vue'

declare module 'vue' {
  interface ComponentCustomProperties {
    $appSafeAreaStyle: Record<string, string>;
  }
}

declare module '@vue/runtime-core' {
  type Hooks = App.AppInstance & Page.PageInstance;

  interface ComponentCustomProperties {
    $appSafeAreaStyle: Record<string, string>;
  }

  interface ComponentCustomOptions extends Hooks {

  }
}

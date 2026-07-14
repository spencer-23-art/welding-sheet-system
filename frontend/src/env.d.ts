/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// Univer preset 语言包为纯 JS，无类型声明
declare module '@univerjs/*/lib/locales/zh-CN' {
  const locale: any
  export default locale
}

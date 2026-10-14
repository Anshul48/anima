/** STC bundle browser face: locale, detail section, row config (v1). */
window.__ModuleLoader__.load({
  id: '@stc/dsh-plugin-stc',
  factory(require) {
    const React = require('react')
    return {
      inject: ['slots', 'locale'],
      apply(ctx) {
        ctx.effect(() => ctx.locale.register('stcBundle', {
          en: {
            section: 'STC execution',
            sectionBody: 'Backend runs launch through stc_run with typed RUN confirmation; stc_dossier and stc_preview are read-only.',
            configSummary: 'STC backend roots and run store',
            configForm: 'STC bundle configuration',
            stcRoot: 'STC root',
            runStore: 'Run store',
            toolsNote: 'Tools: stc_ping, stc_dossier, stc_preview, stc_run, stc_status, stc_log, stc_cancel.',
          },
          zh: {
            section: 'STC 执行',
            sectionBody: '后端运行通过 stc_run 启动，需要键入 RUN 确认；stc_dossier 与 stc_preview 为只读。',
            configSummary: 'STC 后端根目录与运行存储',
            configForm: 'STC 插件配置',
            stcRoot: 'STC 根目录',
            runStore: '运行存储',
            toolsNote: '工具：stc_ping、stc_dossier、stc_preview、stc_run、stc_status、stc_log、stc_cancel。',
          },
        }))
        const mine = (subject) => (subject.kind === 'bundle' || subject.kind === 'row')
          && subject.pkg.name === '@stc/dsh-plugin-stc'
        ctx.slots.inject('plugins.detail.section', () => ctx.slots.register({
          name: 'plugins.detail.section', id: '@stc/dsh-plugin-stc', locale: 'stcBundle',
        }, ({ t, subject }) => mine(subject)
          ? React.createElement('section', { 'data-stc-section': subject.kind, 'aria-label': t('section') },
            React.createElement('h4', null, t('section')),
            React.createElement('p', null, t('sectionBody')),
            React.createElement('p', null, t('toolsNote')))
          : null))
        ctx.slots.inject('plugins.row.config', () => ctx.slots.register({
          name: 'plugins.row.config', key: '@stc/dsh-plugin-stc#stc-bundle', locale: 'stcBundle',
        }, ({ t, view }) => view === 'summary'
          ? t('configSummary')
          : React.createElement('div', { 'data-stc-config': '' },
            React.createElement('p', null, `${t('stcRoot')}: `, React.createElement('code', null, 'STC_ROOT')),
            React.createElement('p', null, `${t('runStore')}: `, React.createElement('code', null, 'STC_DSH_STORE')))))
      },
    }
  },
})

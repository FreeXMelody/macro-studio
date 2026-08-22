import { createRouter, createWebHashHistory } from 'vue-router'
import PlaylistPage from '../pages/PlaylistPage.vue'
import RunCenter from '../pages/RunCenter.vue'
import TargetLibraryPage from '../pages/TargetLibraryPage.vue'
import WorkflowPage from '../pages/WorkflowPage.vue'
import SettingsPage from '../pages/SettingsPage.vue'
import StagePage from '../pages/StagePage.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'run', component: RunCenter, meta: { title: '运行中心' } },
    { path: '/playlists', name: 'playlists', component: PlaylistPage, meta: { title: '队列管理' } },
    { path: '/workflows', name: 'workflows', component: WorkflowPage, meta: { title: '工作流' } },
    { path: '/targets', name: 'targets', component: TargetLibraryPage, meta: { title: '目标库' } },
    { path: '/stage', name: 'stage', component: StagePage, meta: { title: '剧组站' } },
    { path: '/settings', name: 'settings', component: SettingsPage, meta: { title: '目标程序' } },
  ],
})

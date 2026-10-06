<template>
  <div>
    <div class="alert-bar" v-if="alerts.length">临期预警：{{ alerts.map(a => a.name + '(' + a.level + ')').join(' · ') }}</div>
    <div class="alert-bar" v-else>临期预警带：暂无紧急批次</div>
    <div class="wrap">
      <nav class="layer-tabs">
        <router-link to="/">全层</router-link>
        <router-link to="/layer/upper">上层</router-link>
        <router-link to="/layer/mid">中层</router-link>
        <router-link to="/layer/lower">下层</router-link>
        <router-link to="/inbound">入库</router-link>
        <router-link to="/consume">消费</router-link>
        <router-link to="/settings">设置</router-link>
      </nav>
      <router-view />
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from './api'
const alerts = ref([])
async function loadAlerts() { try { alerts.value = await api('/alerts') } catch { alerts.value = [] } }
// 转层/扣减/收走任一写操作成功后，紧急条按同一提交后的状态重取：
// 不会再出现条上已当过期消失、分层页还挂着，或反之的错位。
onMounted(() => { loadAlerts(); window.addEventListener('pantry:changed', loadAlerts) })
onUnmounted(() => window.removeEventListener('pantry:changed', loadAlerts))
</script>

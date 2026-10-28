<template>
<div class="resource-library-view">
<section class="library-card">
      <div class="section-heading">
        <div>
          <h4>绑定微信账号</h4>
          <p class="hint">绑定会校验平台登录账号，不保存密码或 Cookie。必须与发布设置中的登录账号保持一致；旧作品需要你明确确认归属。</p>
        </div>
      </div>
      <div class="form-row account-row">
        <label class="field grow">
          <span>平台登录账号</span>
          <input v-model.trim="accountInput" data-test="account-id" type="text" placeholder="与发布设置中的登录账号保持一致" />
        </label>
        <label class="check-line legacy-check">
          <input v-model="confirmLegacy" data-test="legacy-confirm" type="checkbox" />
          <span>我确认待绑定的旧作品属于这个账号</span>
        </label>
        <button class="btn primary" data-test="bind-account" :disabled="binding || !accountInput || !confirmLegacy" @click="bindAccount">
          {{ binding ? '绑定中…' : '确认绑定' }}
        </button>
      </div>
      <p v-if="accountTip" class="success-text">{{ accountTip }}</p>
    </section>
</div>
</template>
<script setup>
import { useLibraryContext } from './context'
const { accountInput, confirmLegacy, binding, bindAccount, accountTip } = useLibraryContext()
</script>

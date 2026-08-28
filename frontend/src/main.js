import { createApp } from 'vue'
import { setConfig, frappeRequest, resourcesPlugin } from 'frappe-ui'
import App from './App.vue'
import router from './router'
import './index.css'

setConfig('resourceFetcher', frappeRequest)

const app = createApp(App)
app.use(router)
app.use(resourcesPlugin)

if (import.meta.env.DEV) {
  // Mirror the production Jinja boot injection: fetch boot from the bench and
  // copy every key onto window before mounting.
  fetch('/api/method/agile_projects.www.agile.get_context_for_dev', {
    headers: { 'X-Frappe-Site-Name': window.location.hostname },
  })
    .then((res) => res.json())
    .then((data) => {
      const values = data.message || {}
      for (const key in values) {
        window[key] = values[key]
      }
    })
    .finally(() => app.mount('#app'))
} else {
  app.mount('#app')
}

import Vue from 'vue'
import HelloWorld from './HelloWorld.vue'

Vue.config.productionTip = false

new Vue({
  render: h => h(HelloWorld),
}).$mount('#app')

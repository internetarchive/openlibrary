<template>
    <div class="page">
        <h1>Hello Vuorld!</h1>

        New Vue? Read the <a href="https://vuejs.org/v2/guide/">Getting Started Guide</a>. Here are some quick examples:
        <hr />

        <p>Here's a list ({{sampleList.length}} items):</p>
        <ol v-if="sampleList.length">
            <li v-for="(item, i) in sampleList" :key="i">{{item}}</li>
        </ol>
        <p v-else>Your list is empty!</p>

        <hr />

        <p>Here's some logic:</p>
        <!-- v-model is used to bind inputs to data fields. See https://vuejs.org/v2/guide/forms.html -->
        <input type="number" v-model.number="num1"> + <input type="number" v-model.number="num2"> = {{num1 + num2}}
    </div>
</template>

<script>
export default {
    // Props are for external options; if a subelement of this is modified,
    // the view automatically re-renders
    props: {
        sampleList: {
            type: Array,
            default: () => ['A', 'B', 'C'],
        },
    },

    // Data is for internal stuff. This needs to be a function so that we get
    // a fresh object every time this is initialized.
    data: () => {
        return {
            num1: 31,
            num2: 11,
        }
    },

    // Essentially getters
    computed: {

    },

    // Methods :)
    methods: {

    },
}
</script>

<style lang="less">
.page {
  max-width: 800px;
  margin: 0 auto;
  margin-top: 60px;
  padding: 10px;

  input[type="number"] {
    width: 3em;
  }
}
</style>

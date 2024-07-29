<template>
  <div>
    <OLCarousel :query="`${classification.field}:${activeSection.query} ${filter}`" :offset="activeSection.position">
      <template v-slot:cover-label="{book}">
        <span
          :title="book[classification.field].join('\n')"
        >{{book[classification.field][0]}}</span>
      </template>
    </OLCarousel>

    <ClassSlider v-for="(lvl, i) of levels" :node="lvl" :key="i"/>
  </div>
</template>

<script>
import OLCarousel from './OLCarousel';
import ClassSlider from './ClassSlider';

export default {
  components: {
    OLCarousel,
    ClassSlider
  },
  props: {
    filter: {
      default: '',
      type: String
    },
    classification: Object
  },
  methods: {
  },
  data() {
    return {};
  },

  computed: {
    activeSection() {
      return this.levels[0].children[this.levels[0].position];
    },

    levels() {
      const result = [];
      let cur = this.classification.root;
      while (cur.children) {
        result.push(cur);
        cur = cur.children[cur.position];
      }
      return result.reverse();
    }
  }
};
</script>

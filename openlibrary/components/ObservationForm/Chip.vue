<template>
  <span
    class="chip"
    v-bind:class="{ 'chip--selectable': selectable, 'chip--selected': isSelected }"
    @[canSelect]="onClick"
    >
    {{text}}
    <slot></slot>
  </span>
</template>

<script>
export default {
    name: 'Chip',
    props: {
        text: {
            type: String,
            required: true
        },
        selectable: {
            type: Boolean,
            required: false,
            default: false
        },
        selected: {
            type: Boolean,
            required: false,
            default: false
        }
    },
    data: function() {
        return {
            isSelected: this.selected
        }
    },
    computed: {
        canSelect: function() {
            return this.selectable ? 'click' : null;
        }
    },
    methods: {
        onClick: function() {
            this.toggleSelected();
            this.$emit('update-selected', this.isSelected, this.text)
        },
        toggleSelected: function() {
            this.isSelected = !this.isSelected;
        }
    }
}
</script>

<style scoped>
.chip {
  padding: 4px 12px;
  border: 1px solid #999999;
  border-radius: 16px;
  user-select: none;
}

.chip--selectable {
  cursor: pointer;
}

.chip--selectable:hover {
  background-color: #e6e6e6;
}

.chip--selected {
  background-color: white;
  border-color: #1976d2;
  color: #1976d2;
  background-color: #f6fafe;
}

.chip--selected:hover {
  background-color: white;
}
</style>

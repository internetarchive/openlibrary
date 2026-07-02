<template>
  <span
    class="chip"
    :class="[{ 'chip--selectable': selectable, 'chip--selected': isSelected }, classList]"
    @[canSelect]="onClick"
  >
    <slot name="before" />
    {{ text }}
    <slot name="after" />
  </span>
</template>

<script>
/**
 * Displays text within a pill-shaped outline.
 */
export default {
    name: 'OLChip',
    props: {
        /**
         * Text that will be displayed by the chip.
         */
        text: {
            type: String,
            required: true
        },
        /**
         * Determines whether the chip can be selected.
         * A selected chip changes color and emits an
         * `update-selected` event.
         */
        selectable: {
            type: Boolean,
            required: false,
            default: false
        },
        /**
         * Determines whether this chip is initially selected.
         */
        selected: {
            type: Boolean,
            required: false,
            default: false
        },
        /**
         * A list of space-seperated classes that will be assigned to the chip.
         */
        classList: {
            type: String,
            required: false,
            default: ''
        }
    },
    data: function() {
        return {
            /**
             * Tracks whether this chip is currently selected.
             *
             * @type {boolean}
             */
            isSelected: this.selected
        };
    },
    computed: {
        /**
         * Used to determine whether this chip has a click listener.
         *
         * @returns 'click' if this chip can be selected, otherwise `null`
         */
        canSelect: function() {
            return this.selectable ? 'click' : null;
        }
    },
    watch: {
        selected(newValue) {
            this.isSelected = newValue;
        }
    },
    methods: {
        /**
         * Toggles the value of `isSelected` and fires an `update-selected` event.
         */
        onClick: function() {
            this.toggleSelected();
            /**
             * Update selected event.
             *
             * @property {boolean} isSelected Selected status of this chip.
             * @property {String} text Main text displayed by this chip.
             */
            this.$emit('update-selected', this.isSelected, this.text);
        },
        /**
         * Toggles the state of `isSelected`
         */
        toggleSelected: function() {
            this.isSelected = !this.isSelected;
        }
    }
};
</script>

<style scoped>
.chip {
  padding: 4px 12px;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  user-select: none;
}

.chip--selectable {
  cursor: pointer;
}

.chip--selectable:hover {
  background-color: var(--neutral-200);
}

.chip--selected {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background-color: var(--color-primary-subtle);
}

.chip--selected:hover {
  background-color: var(--color-surface);
}
</style>

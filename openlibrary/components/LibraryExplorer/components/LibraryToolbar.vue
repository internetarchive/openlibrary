<template>
    <div class="floating-controls-wrapper">
      <div class="floating-controls">
        <details>
          <summary>
            <div class="chunky-icon">
              <div class="chunky-icon--icon">
                <FilterIcon/>
              </div>
              <div class="chunky-icon--label">
                Filter
                <span style="opacity: .55" v-if="activeFiltersCount">({{activeFiltersCount}})</span>
              </div>
            </div>
          </summary>
          <main>
            <input class="filter" v-model="filterState.filter">
            <!-- <small>{{computedFilter}}</small> -->
            <div class="click-controls">
              <div class="horizontal-selector">
                <div>First Published Year</div>
                <div class="options">
                  <label>
                    <input type="radio" v-model="filterState.year" value>Any
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.year" value="[2010 TO 9998]">New (2010+)
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.year" value="[1985 TO 9998]">Modern (1985+)
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.year" value="[* TO 1924]">Public Domain (&lt;1924)
                  </label>
                </div>
              </div>
              <div class="horizontal-selector">
                <div>Has ebook?</div>
                <div class="options">
                  <label>
                    <input type="radio" v-model="filterState.has_ebook" value>Any
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.has_ebook" value="true">Yes
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.has_ebook" value="false">No
                  </label>
                </div>
              </div>
              <div class="horizontal-selector">
                <div>Age Range</div>
                <div class="options">
                  <label>
                    <input type="radio" v-model="filterState.age" value>Any
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.age" value="juvenile">Juvenile
                  </label>
                </div>
              </div>
              <div class="horizontal-selector">
                <div>Language</div>
                <div class="options">
                  <label>
                    <input type="radio" v-model="filterState.language" value>Any
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.language" value="eng">English
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.language" value="ger">German
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.language" value="fre">French
                  </label>
                  <button title="todo">...</button>
                </div>
              </div>
            </div>
            <!-- <pre>{{parsedFilter}}</pre> -->
          </main>
        </details>
        <details>
          <summary>
            <div class="chunky-icon">
              <div class="chunky-icon--icon">
                <SettingsIcon/>
              </div>
              <div class="chunky-icon--label">Settings</div>
            </div>
          </summary>
          <main class="click-controls">
            <div class="horizontal-selector">
              <div>Classification</div>
              <div class="options">
                <label v-for="c of settingsState.classifications" :key="c.name">
                  <input type="radio" v-model="settingsState.selectedClassification" :value="c">
                  {{c.name}}
                </label>
              </div>
            </div>
            <div class="horizontal-selector" v-for="(opts, name) of settingsState.styles" :key="name">
              <div>{{name}} style</div>
              <div class="options">
                <label v-for="cls of opts.options" :key="cls">
                  <input type="radio" v-model="opts.selected" :value="cls">
                  {{cls}}
                </label>
              </div>
            </div>
          </main>
        </details>
      </div>
    </div>
</template>

<script>
import lucenerQueryParser from 'lucene-query-parser';
import SettingsIcon from './icons/SettingsIcon';
import FilterIcon from './icons/FilterIcon';

export default {
    components: {
        FilterIcon,
        SettingsIcon
    },

    props: {
        filterState: Object,
        settingsState: Object,
    },

    computed: {
        activeFiltersCount() {
            return Object.values(this.filterState).filter(v => v).length;
        },


        parsedFilter() {
            return lucenerQueryParser.parse(this.filterState.filter);
        },
    }
}
</script>

<style lang="less">
.floating-controls-wrapper {
  position: -webkit-sticky;
  position: sticky;
  bottom: 0;
  left: 0;
  display: flex;
  justify-content: center;
  pointer-events: none;

  .chunky-icon {
    padding: 4px;
    margin: 4px;
    width: 48px;
    transition: background-color .2s;

    &--icon svg {
      width: 48px;
      height: 24px;
    }

    &--label {
      font-size: .8em;
      text-align: center;
    }
  }

  .floating-controls {
    pointer-events: all;
    display: flex;
    border-radius: 4px 4px 0 0;
    overflow: hidden;
    box-shadow: 0 0 5px rgba(0, 0, 0, .2);
    // white/grey:
    // background: linear-gradient(
    //   to bottom,
    //   #e9e9e9,
    //   white 10%,
    //   #e9e9e9 90%,
    //   #b6b6b6
    // );
    // white/page-colored
    background: linear-gradient(to bottom, #fff, #ebdfc5 150%);
    max-width: 100%;
    max-height: 80vh;

    & > details {
      border-right: 1px solid rgba(0, 0, 0, .2);
      &:last-child {
        border: 0;
      }
      &[open] {
        flex: 1;
      }
      &[open] > summary > .chunky-icon {
        background-color: rgba(0, 0, 0, .1);
        display: inline-block;
        border-radius: 4px;
      }

      & > summary {
        &::marker { display: none; }
        &::-webkit-details-marker { display: none; }

        display: inline-flex;
        cursor: pointer;
        transition: background-color .2s;
        &:hover {
          background-color: rgba(0, 0, 0, .1);
        }
      }

      & > main {
        padding: 8px;
      }
    }
  }
}

.click-controls {
  display: flex;
  flex-wrap: wrap;
}

.horizontal-selector {
  margin-right: 10px;

  .options {
    border: 1px solid currentColor;
    border-radius: 4px;
  }

  .options label {
    display: inline-block;
    padding: 4px;
  }
}

input.filter {
  padding: 8px;
  max-width: 100%;
  width: 300px;
  box-sizing: border-box;
}
</style>

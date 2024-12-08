<template>
  <div ref="ileToolbar" id="ile-toolbar" v-show="visibleToolbar">
    <div id="ile-selections">
      <div ref="dragStatus" id="ile-drag-status">
          <div ref="statusText" class="text"> {{ showText }}</div>
          <div ref="statusImages" class="images">
            <ul>
              <StatusImage v-for="statusImageObj in statusImageList" :key="statusImageObj.title"
              :title="statusImageObj.title" :image="statusImageObj.image" />
            </ul>
          </div>
      </div>
      <div id="ile-selection-actions">
        <a v-show="showClearSelection" @click="clearSelectedItems">Clear Selections</a>
      </div>
    </div>
    <div id="ile-drag-actions">
      <a v-show="showTagWorks" @click="tagWorksMenu">Tag Works</a>
      <a v-show="showMergeWorks" :href="hrefMergeWorks">Merge Works...</a>
      <a v-show="showMergeAuthors" :href="hrefMergeAuthors">Merge Authors...</a>
    </div>
    <div ref="ileHiddenForms" id="ile-hidden-forms" v-show="visibleBulkTaggerForm">
    </div>
  </div>
</template>

<script>
import { renderBulkTagger } from '../plugins/openlibrary/js/bulk-tagger';
import { BulkTagger } from '../plugins/openlibrary/js/bulk-tagger/BulkTagger';
import { SelectionManager } from './IntegratedLibrarianEnvironment/utils/classes.js';
import StatusImage from './IntegratedLibrarianEnvironment/components/StatusImage.vue';

export default {
    components: { StatusImage },
    data() {
        return {
            selectionManager: new SelectionManager(this),
            bulkTagger: null,
            visibleToolbar: null,
            showText: '',
            statusImageList: [],
            isMounted: false,
            showClearSelection: false,
            clearSelectedItems: () => {},
            showTagWorks: false,
            tagWorksMenu: () => {
                if (this.tagWorksContext) {
                    this.updateAndShowBulkTagger(this.tagWorksContext);
                }
            },
            tagWorksContext: [],
            showMergeWorks: false,
            hrefMergeWorks: '',
            showMergeAuthors: false,
            hrefMergeAuthors: '',
        }
    },
    computed: {
        visibleBulkTaggerForm: function() {
            if (!this.isMounted) return;
            return this.$refs.ileHiddenForms.classList.contains('hidden') ? false : true;
        }
    },

    methods: {
        init() {
            this.visibleToolbar = false;
            this.createBulkTagger();
            this.selectionManager.init();
        },

        setStatusText(text) {
            this.showText = text;
            this.visibleToolbar = text.length > 0;
        },

        reset() {
            this.statusImageList = [];
            this.setStatusText('');
            this.showClearSelection = false;
            this.showMergeAuthors = false;
            this.showMergeWorks = false;
        },

        createBulkTagger() {
            const target = this.$refs.ileHiddenForms;
            target.innerHTML += renderBulkTagger();
            const bulkTaggerElem = this.$refs.ileHiddenForms.querySelector('.bulk-tagging-form')
            this.bulkTagger = new BulkTagger(bulkTaggerElem);
            this.bulkTagger.initialize();
        },

        updateAndShowBulkTagger(workIds) {
            if (this.bulkTagger) {
                this.bulkTagger.updateWorks(workIds);
                this.bulkTagger.showTaggingMenu();
            }
        },
    },
    mounted() {
        document.body.appendChild(this.$refs.ileToolbar)
        this.isMounted = true;
        this.init();
        window.ILE = this;
    }

}

</script>

<style lang="less">
@selection-outline: #009fff;
@selection-background: #c2e8ff;
@ile-toolbar-background: #0067d5;
@ile-toolbar-text-color: white;

.hidden {
  display: none !important;
}


#ile-toolbar {
  display: flex;
  position: sticky;
  bottom: 12px;
  padding: 7px;
  margin: 0 15px;
  border-radius: 5px;
  background: @ile-toolbar-background;
  color: @ile-toolbar-text-color;
  z-index: 10;
  font-size: .9em;
}
#ile-toolbar a {
  padding: 4px 16px;
  display: inline-block;
  color: @ile-toolbar-text-color;
  text-decoration: none;
  border-left: 2px dotted @ile-toolbar-text-color;
  transition: background .2s;
  cursor: pointer;
}
#ile-selection-actions {
  display: inline-block;
}
#ile-selections {
  flex: 1;
}
#ile-drag-status {
  display: inline-block;
}
#ile-drag-status .drag-image {
  max-width: 300px;
}
#ile-drag-status .text {
  border-radius: 100px;
  background: @ile-toolbar-background;
  padding: 4px 16px;
}
#ile-drag-status .images {
  position: absolute;
  top: -90px;
  left: 8px;
}
#ile-drag-status ul {
  display: flex;
  list-style: none;
  margin: 0;
  padding: 0;
}

#ile-drag-actions a:hover { background: rgba(0,0,0,.15); }

// Bulk Tagger Styles
.bulk-tagging-form {
  width: 320px;
  height: fit-content;
  right: 30px;
  bottom: 50px;
  border: 1px solid hsl(0, 0%, 80%);
  box-shadow: 0 5px 5px 2px hsl(0, 0%, 46.3%);
  background-color: hsl(0, 0%, 100%);
  border-radius: 10px;
  position: absolute;
}

.bulk-tagging-form p {
  color: #333;
  font-size: .875em;
  line-height: 1.5em;
  box-sizing: border-box;
}

.form-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 33px;
  padding: 7px 15px;
  font-weight: bold;
  box-sizing: border-box;
}

.close-bulk-tagging-form {
  cursor: pointer;
  color: hsl(0, 0%, 0%);
  font-size: 17px;
  font-weight: normal;
}

.search-subject-container {
  border-top: 1px solid hsl(0, 0%, 80%);
  border-bottom: 1px solid hsl(0, 0%, 80%);
  width: 100%;
  padding: 5px;
  box-sizing: border-box;
}

.subjects-search-input {
  width: 100%;
  height: 100%;
  padding: 5px;
  border: 1px solid hsl(0, 0%, 80%);
  border-radius: 5px;
  background: hsl(0, 0%, 100%);
  font-size: 14px;
  color: hsl(0, 0%, 0%);
  box-sizing: border-box;

  &:focus {
    border-color: hsl(255, 100%, 60%);
  }
}
input[type="text"] {
  margin: 0 10px 5px 0;
  color: #444;
  font-size: .875em;
  font-family: "Lucida Grande", Veranda, Geneva, Helvetica, sans-serif;
}

// Menu option containers:
.selection-container {
  height: 266px;
  overflow-y: auto;

  .subjects-search-results,
  .selected-tag-subjects {
    padding: 0 5px;
  }

  &::-webkit-scrollbar {
    -webkit-appearance: none;
    background-color: hsl(0, 0%, 87%);
    width: 5px;
  }

  &::-webkit-scrollbar-thumb {
    border-radius: 4px;
    background-color: hsl(0, 0, 40%);
    -webkit-box-shadow: 0 0 1px hsl(0, 0, 40%);
  }
}

.search-subject-row {
  display: flex;
  align-items: center;
  font-size: 16px;
  border-bottom: 1px solid hsl(0, 0%, 80%);
  border-top: 1px solid hsl(0, 0%, 80%);
  padding: 7px;
  width: 100%;
  min-height: 38px;
  cursor: pointer;
}

.search-subject-row:hover {
  background-color: hsl(202, 57%, 61%);
}

// Holds the button
.submit-tags-section {
  padding: 5px;
}

.subject-type-option {
  font-size: 11px;
  color: hsl(0, 0%, 100%);
  font-weight: 700;
  width: fit-content;
  padding: 3px 6px;
  border-radius: 8px;
  cursor: pointer;

  &--place {
    background-color: hsl(8, 70%, 44%);
  }
  &--person {
    background-color: hsl(113, 38%, 29%);
  }
  &--time {
    background-color: hsl(57%, 60%, 72%);
    color: hsl(0, 0%, 0%);
  }
  &--subject {
    background-color: hsl(202, 96%, 37%);
  }
}

.search-subject-row-name {
  font-size: 13px;
  color: hsl(0, 0%, 0%);
  font-weight: 400;

  &.search-subject-row-name-create {
    height: 50px;
    width: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 9px 10px;
    border-bottom: 1px solid hsl(0, 0%, 80%);
    border-top: 1px solid hsl(0, 0%, 80%);

    .search-subject-row-name-create-p {
      font-size: 13px;
      color: hsl(0, 0%, 0%);
      font-weight: 400;
      margin-bottom: 5px;
    }

    .search-subject-row-name-create-select {
      width: 100%;
      display: flex;
      flex-direction: row;
      gap: 5px;
    }
  }
}

.search-subject-row-subject-info {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-end;
  gap: 2px;
  margin-left: auto;
}

.search-subject-work-count {
  color: hsl(0, 0, 40%);
  font-size: 8px;
  margin-right: 2px;
}

.search-subject-type {
  font-size: 11px;
  font-weight: 700;
  border-radius: 8px;
  padding: 2px 6px;
}

.new-selected-subject-tag {
  border: 1px solid hsl(0, 0%, 87%);
  padding: 2px 6px;
  font-size: 13px;
  height: 20px;
  width: fit-content;
  text-align: center;
}

.remove-selected-subject {
  font-size: 11px;
  color: hsl(0, 0%, 0%);
  font-weight: bold;
  cursor: pointer;
  margin-left: 7px;
}

.selected-tag {
  color: hsl(0, 0%, 0%);
  cursor: pointer;
  margin: 5px 0;
  padding: 5px 0;
  display: flex;
  align-items: center;
  font-weight: 700;

  .selected-tag__status {
    display: inline-block;
    width: 1em;
    text-align: center;
    margin-right: 5px;

    &--some-tagged::before {
      content: "-";
    }
    &--all-tagged::before {
      content: "✓";
    }
  }

  .selected-tag__name {
    overflow-wrap: anywhere;
    max-width: 190px;
  }

  .selected-tag__type-container {
    width: 80px;
    margin: 0 10px 0 auto;
  }

  .selected-tag__type {
    border-radius: 8px;
    display: inline-block;
    padding: 3px 6px;
    color: hsl(0, 0%, 100%);
    font-size: 11px;
    width: fit-content;

    &--place {
      background-color: hsl(8, 70%, 44%);
    }

    &--person {
      background-color: hsl(113, 38%, 29%);
    }

    &--time {
      background-color: hsl(57%, 60%, 72%);
      color: hsl(0, 0%, 0%);
    }

    &--subject {
      background-color: hsl(202, 96%, 37%);
    }
  }

  &--staged {
    background-color: hsl(58, 100%, 90%);
  }
}

.loading-indicator {
  height: 266px;
  background: hsl(0, 0%, 100%) url(/static/images/ajax-loader.gif) center center no-repeat;
}

</style>

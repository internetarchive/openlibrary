// @ts-check
import SelectionManager from './utils/SelectionManager/SelectionManager.js';
import { renderBulkTagger } from '../bulk-tagger/index.js';
import { BulkTagger } from '../bulk-tagger/BulkTagger.js';

export function init() {
  const ile = new IntegratedLibrarianEnvironment();
  // @ts-ignore
  window.ILE = ile;
  ile.init();
}

export class IntegratedLibrarianEnvironment {
  constructor() {
    this.selectionManager = new SelectionManager(this);
    /** This is the main ILE toolbar. Should be moved to a Vue component. */
    this.$toolbar = $(`
            <div id="ile-toolbar">
                <div id="ile-selections">
                    <div id="ile-drag-status">
                        <div class="text"></div>
                        <div class="images"><ul></ul></div>
                    </div>
                    <div id="ile-selection-actions"></div>
                </div>
                <div id="ile-drag-actions"></div>
                <div id="ile-hidden-forms"></div>
            </div>`.trim());
    this.$selectionActions = this.$toolbar.find('#ile-selection-actions');
    this.$statusText = this.$toolbar.find('.text');
    this.$statusImages = this.$toolbar.find('.images ul');
    this.$actions = this.$toolbar.find('#ile-drag-actions');
    this.$hiddenForms = this.$toolbar.find('#ile-hidden-forms');
    this.bulkTagger = null
  }

  init() {
    // Add the ILE toolbar to bottom of screen
    $(document.body).append(this.$toolbar.hide());

    // Ready bulk tagger:
    this.createBulkTagger();

    this.selectionManager.init();
  }

  /** @param {string} text */
  setStatusText(text) {
    this.$statusText.text(text);
    this.$toolbar.toggle(text.length > 0);
  }

  /**
     * Unselects selected search result items and resets status bar.
     */
  reset() {
    for (const elem of $('.ile-selected')) {
      elem.classList.remove('ile-selected')
    }
    this.setStatusText('');
    this.$selectionActions.empty();
    this.$statusImages.empty();
    this.$actions.empty();
  }

  /**
     * Creates a new Bulk Tagger component and attaches it to the DOM.
     *
     * Sets the value of `IntegratedLibrarianEnvironment.bulkTagger`
     */
  createBulkTagger() {
    const target = this.$hiddenForms[0]
    target.innerHTML += renderBulkTagger()
    const bulkTaggerElem = document.querySelector('.bulk-tagging-form')
    // @ts-ignore
    this.bulkTagger = new BulkTagger(bulkTaggerElem)
    this.bulkTagger.initialize()
  }

  /**
     * Updates the Bulk Tagger with the selected works, then displays the tagger.
     *
     * @param {Array<String>} workIds
     */
  updateAndShowBulkTagger(workIds) {
    if (this.bulkTagger) {
      this.bulkTagger.updateWorks(workIds)
      this.bulkTagger.showTaggingMenu()
    }
  }
}

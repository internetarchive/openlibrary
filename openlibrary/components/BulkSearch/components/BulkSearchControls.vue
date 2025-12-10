<template>
  <div class="bulk-search-controls">
    <div>
      <p v-if="showColumnHint">
        Please include a header row. Supported columns include: "Title", "Author", "ISBN".
      </p>

      <select
        v-model="selectedValue"
        class="sampleBar"
      >
        <option
          v-for="sample in sampleData"
          :key="sample.source"
          :value="sample.text"
        >
          {{ sample.name }}
        </option>
      </select>
      <textarea
        v-model="bulkSearchState.inputText"
        placeholder="Enter your books..."
      />
      <br>
      <div class="progressCarousel">
        <div class="progressCard">
          <div class="numeral">
            1
          </div>
          <div class="info">
            <div class="heading">
              <h3> Extract Books</h3>
              <p><i>How to convert your books above into structured information, like title and author.</i></p>
            </div>
            <label><strong> Extractor</strong> <br>
              <div
                class="custom-dropdown-trigger"
                :class="{ open: extractorDropdownOpen }"
                @click="toggleExtractorDropdown"
              >
                <span>{{ bulkSearchState.extractors[bulkSearchState._activeExtractorIndex].label }}</span>
                <svg
                  class="arrow"
                  xmlns="http://www.w3.org/2000/svg"
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                >
                  <path
                    d="M7 10l5 5 5-5z"
                    fill="currentColor"
                  />
                </svg>
              </div>
              <div
                v-if="extractorDropdownOpen"
                class="custom-dropdown-menu"
                :style="extractorDropdownStyle"
              >
                <div
                  v-for="(extractor, index) in bulkSearchState.extractors"
                  :key="index"
                  class="dropdown-item"
                  @click="selectExtractor(index)"
                >
                  {{ extractor.label }}
                </div>
              </div>
            </label>

            <label v-if="showApiKey"><strong>OpenAI API Key</strong> <br>
              <input
                v-model="bulkSearchState.extractionOptions.openaiApiKey"
                class="api-key-bar"
                :type="showPassword ? 'password' : 'text'"
                placeholder="OpenAI API key here...."
                @focus="showPassword = false"
                @blur="showPassword = true"
              >
            </label>


            <button
              :disabled="loadingExtractedBooks"
              @click="extractBooks"
            >
              {{ extractBooksText }}
            </button>
          </div>
        </div>
        <div
          class="progressCard"
          :class="{ progressCardDisabled: matchBooksDisabled}"
        >
          <div class="numeral">
            2
          </div>
          <div class="info">
            <div class="heading">
              <h3>Match Books</h3>
              <p><i>Once structured data has been found, it's time to match it to a book in OpenLibrary!</i></p>
            </div>
            <label><strong>Options</strong> <br>
              <input
                v-model="bulkSearchState.matchOptions.includeAuthor"
                type="checkbox"
              > Use author in
              search query
            </label>
            <button
              :disabled="loadingMatchedBooks || matchBooksDisabled"
              @click="matchBooks"
            >
              {{ matchBooksText }}
            </button>
          </div>
        </div>
        <div
          class="progressCard"
          :class="{ progressCardDisabled: createListDisabled }"
        >
          <div class="numeral">
            3
          </div>
          <div class="info">
            <div class="heading">
              <h3 class="heading">
                Save your Matches
              </h3>
              <p class="heading">
                <i> Now that you've found your books, why not save them to your reading log? Or a list?</i>
              </p>
            </div>

            <div class="list-actions">
              <label>
                <strong>Save to</strong>
                <div
                  class="custom-dropdown-trigger"
                  :class="{ open: listDropdownOpen }"
                  @click="toggleListDropdown"
                >
                  <span>{{ selectedListLabel }}</span>
                  <svg
                    class="arrow"
                    xmlns="http://www.w3.org/2000/svg"
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                  >
                    <path
                      d="M7 10l5 5 5-5z"
                      fill="currentColor"
                    />
                  </svg>
                </div>

                <div
                  v-if="listDropdownOpen"
                  class="custom-dropdown-menu"
                  :style="listDropdownStyle"
                >
                  <div
                    class="dropdown-item"
                    @click="selectOption('create', 'Create a new list')"
                  >
                    Create a new list
                  </div>
                  <div class="dropdown-divider" />
                  <div
                    v-for="list in formattedUserLists"
                    :key="list.key"
                    class="dropdown-item"
                    :title="list.tooltip"
                    @click="selectOption(list.value, list.label)"
                  >
                    {{ list.label }}
                  </div>
                </div>
              </label>

              <p
                v-if="listOptionsLoading"
                class="list-message"
              >
                Loading your lists...
              </p>
              <p
                v-else-if="listOptionsError"
                class="list-message list-message-error"
              >
                {{ listOptionsError }}
              </p>

              <button
                :disabled="saveButtonDisabled"
                @click.prevent="saveMatches"
              >
                {{ saveButtonText }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="bulkSearchState.errorMessage">
      <p
        v-for="error in bulkSearchState.errorMessage"
        :key="error"
      >
        {{ error }}
      </p>
    </div>
  </div>
</template>

<script>
import {sampleData} from '../utils/samples.js';
import { BulkSearchState} from '../utils/classes.js';
import { buildSearchUrl } from '../utils/searchUtils.js'

export default {
    props: {
        bulkSearchState: BulkSearchState
    },
    emits: ['list-selected'],
    data() {
        return {
            selectedValue: '',
            showPassword: true,
            sampleData: sampleData,
            loadingExtractedBooks: false,
            loadingMatchedBooks: false,
            matchBooksDisabled: true,
            createListDisabled: true,
            userLists: [],
            listOptionsLoading: false,
            listOptionsError: '',
            savingMatches: false,
            selectedListTarget: 'create',
            restoredSelection: false,
            listDropdownOpen: false,
            selectedListLabel: 'Create a new list',
            listDropdownStyle: {},
            extractorDropdownOpen: false,
            extractorDropdownStyle: {}
        }
    },
    computed: {
        showApiKey(){
            if (this.bulkSearchState.activeExtractor) return 'model' in this.bulkSearchState.activeExtractor
            return false
        },
        extractBooksText(){
            if (this.loadingExtractedBooks) return 'Loading...'
            return 'Extract Books'
        },
        matchBooksText(){
            if (this.loadingMatchedBooks) return 'Loading...'
            return 'Match Books'
        },
        showColumnHint(){
            if (this.bulkSearchState.activeExtractor) return this.bulkSearchState.activeExtractor.name === 'table_extractor'
            return false
        },
        saveButtonDisabled() {
            if (this.savingMatches) return true
            if (this.selectedListTarget === 'create') return this.createListDisabled
            return this.matchBooksDisabled || !this.selectedListTarget
        },
        saveButtonText() {
            if (this.savingMatches) return 'Saving...'
            return this.selectedListTarget === 'create' ? 'Create List' : 'Add to List'
        },
        formattedUserLists() {
            return this.userLists
                .map((list) => {
                    const name = (list.name || '').trim() || 'Untitled list'
                    const count = Array.isArray(list.list_items) ? list.list_items.length : null
                    const owner = list.owner?.displayname
                    const countLabel = typeof count === 'number' ? `${count} item${count === 1 ? '' : 's'}` : null
                    const tooltipParts = [name]

                    if (countLabel) tooltipParts.push(countLabel)
                    if (owner) tooltipParts.push(`Owner: ${owner}`)

                    return {
                        key: list.key,
                        value: list.add_url || `${list.key}/add`,
                        label: name,
                        tooltip: tooltipParts.join(' | ')
                    }
                })
                .sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }))
        }
    },
    watch: {
        selectedValue(newValue) {
            if (newValue!==''){
                this.bulkSearchState.inputText = newValue;
            }
        },
        selectedListTarget(newValue) {
            this.$emit('list-selected', newValue)
        }
    },
    mounted() {
        this.loadUserLists()
        document.addEventListener('click', this.closeDropdown)
        window.addEventListener('scroll', this.closeDropdown, true)
        window.addEventListener('resize', this.closeDropdown)
    },
    beforeUnmount() {
        document.removeEventListener('click', this.closeDropdown)
        window.removeEventListener('scroll', this.closeDropdown, true)
        window.removeEventListener('resize', this.closeDropdown)
    },
    methods: {
        toggleListDropdown(e) {
            e.stopPropagation()
            if (this.listDropdownOpen) {
                this.closeDropdown()
                return
            }
            this.closeDropdown() // Close others
            const rect = e.currentTarget.getBoundingClientRect()
            this.listDropdownStyle = {
                position: 'fixed',
                top: `${rect.bottom + 4}px`,
                left: `${rect.left}px`,
                width: `${rect.width}px`,
                zIndex: 9999
            }
            this.listDropdownOpen = true
        },
        toggleExtractorDropdown(e) {
            e.stopPropagation()
            if (this.extractorDropdownOpen) {
                this.closeDropdown()
                return
            }
            this.closeDropdown() // Close others

            const rect = e.currentTarget.getBoundingClientRect()
            this.extractorDropdownStyle = {
                position: 'fixed',
                top: `${rect.bottom + 4}px`,
                left: `${rect.left}px`,
                width: `${rect.width}px`,
                zIndex: 9999
            }
            this.extractorDropdownOpen = true
        },
        closeDropdown() {
            this.listDropdownOpen = false
            this.extractorDropdownOpen = false
        },
        selectExtractor(index) {
            this.bulkSearchState._activeExtractorIndex = index
            this.closeDropdown()
        },
        selectOption(value, label) {
            this.selectedListTarget = value
            this.selectedListLabel = label
            this.closeDropdown()
        },
        togglePasswordVisibility(){
            this.showPassword= !this.showPassword
        },
        async extractBooks() {
            this.loadingExtractedBooks = true
            const extractedData = await this.bulkSearchState.activeExtractor.run(this.bulkSearchState.extractionOptions, this.bulkSearchState.inputText)
            this.bulkSearchState.matchedBooks = extractedData
            this.loadingExtractedBooks = false
            this.matchBooksDisabled = false;
            this.createListDisabled = true;
        },
        async matchBooks() {
            const fetchSolrBook = async function (book, matchOptions) {
                try {
                    const data = await fetch(buildSearchUrl(book, matchOptions, true))
                    return await data.json()
                }
                catch (error) {}
            }
            this.loadingMatchedBooks = true
            for (const bookMatch of this.bulkSearchState.matchedBooks) {
                bookMatch.solrDocs = await fetchSolrBook(bookMatch.extractedBook, this.bulkSearchState.matchOptions)
            }
            this.loadingMatchedBooks = false
            this.createListDisabled = false
        },
        async loadUserLists() {
            this.listOptionsLoading = true
            this.listOptionsError = ''

            try {
                const response = await fetch('/account/lists/user_lists', {
                    headers: { Accept: 'application/json' }
                })

                if (!response.ok) {
                    if (response.status === 401 || response.status === 403) {
                        this.listOptionsError = 'Sign in to add books to an existing list.'
                    } else {
                        this.listOptionsError = 'Unable to load your lists.'
                    }
                    this.userLists = []
                    return
                }

                const data = await response.json()
                this.userLists = data.lists || []
            } catch (error) {
                this.listOptionsError = 'Unable to load your lists.'
                this.userLists = []
            } finally {
                this.listOptionsLoading = false
            }
        },
        async saveMatches() {
            if (this.savingMatches || this.matchBooksDisabled || this.createListDisabled) return

            if (this.selectedListTarget === 'create') {
                this.savingMatches = true
                try {
                    this.saveToNewList()
                } finally {
                    this.savingMatches = false
                }
            } else {
                this.savingMatches = true
                try {
                    await this.saveToExistingList()
                } finally {
                    this.savingMatches = false
                }
            }
        },
        saveToNewList() {
            if (!this.bulkSearchState.seedKeys.length) return

            if (this.bulkSearchState.matchedBooks.length < 50) {
                window.open(this.bulkSearchState.listUrl, '_blank')
                return
            }

            const form = document.createElement('form')
            form.method = 'POST'
            form.action = '/account/lists/add'
            form.target = '_blank'

            const seedsInput = document.createElement('input')
            seedsInput.type = 'hidden'
            seedsInput.name = 'seeds'
            seedsInput.value = this.bulkSearchState.listString
            form.appendChild(seedsInput)

            document.body.appendChild(form)
            form.submit()
            document.body.removeChild(form)
        },
        async saveToExistingList() {
            if (!this.selectedListTarget || this.selectedListTarget === 'create') {
                this.listOptionsError = 'Please select a list.'
                return
            }

            const seeds = this.bulkSearchState.listString

            if (!seeds) {
                this.listOptionsError = 'No matched books to add.'
                return
            }

            this.listOptionsError = ''
            const listUrl = `${this.selectedListTarget}?seeds=${encodeURIComponent(seeds)}`
            window.open(listUrl, '_blank')
        },
        canUseLocalStorage() {
            return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
        }
    }
}
</script>

<style lang="less">

.bulk-search-controls{
    padding:20px;
}
label input {
    flex: 1;
}

.sampleBar{
    float:right;
    margin-bottom: 5px;
}
textarea {
    width: 100%;
    height: 120px;
    display: flex;
    resize: vertical;
    box-sizing: border-box;
}
.progressCarousel{
    display:flex;
    overflow-x:scroll;
    column-gap:10px;
}
.progressCard{
    background-color:#C7E3FC;
    padding: 16px;
    width: min(450px, 66vw);
    border-radius:30px;
    display:flex;
    column-gap:16px;
    flex-shrink:0;
    .info{
        display:flex;
        flex-direction:column;
        row-gap:10px;
        .heading{
            color:#0376B8;
            h3{
                margin:0px;
            }
            p{
                margin:0px;
            }
        }
        select{
            width: 100%;
        }
        button{
            background-color:#0376B8;
            color:white;
            border-radius:4px;
            box-shadow: none;
            border:none;
            padding: 0.5rem;
            transition:  background-color 0.2s;
            min-width:140px;
            align-self:flex-start;
            &:not([disabled]) {
                cursor:pointer;
                &:hover{
                    background-color:#014c78;
                }
            }
        }
    }
    .numeral{
        border-radius: 50%;
        height:48px;
        width:48px;
        background-color:white;
        color:#0376B8;
        font-weight:bold;
        justify-content:center;
        flex-shrink: 0;
        display:flex;
        align-items:center;
        font-size:24px;
    }
}

.progressCardDisabled{
    opacity:50%;
}


.api-key-bar{
    width:100%;
    box-sizing:border-box;
}

.list-actions {
  display: flex;
  flex-direction: column;
  row-gap: 12px;
  position: relative;
}

.list-message {
  margin: 0;
  font-size: 0.9rem;
}

.list-message-error {
  color: #c0392b;
}

.list-message-hint {
  color: #046c9c;
}

.custom-dropdown-trigger {
  width: 100%;
  padding: 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background-color: #fff;
  color: #111827;
  font-size: 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  box-sizing: border-box;
  font-family: inherit;

  &:hover {
    border-color: #9ca3af;
  }

  &.open {
    border-color: #0376b8;
    box-shadow: 0 0 0 3px rgba(3, 118, 184, 0.1);
  }

  .arrow {
    transition: transform 0.2s ease;
  }

  &.open .arrow {
    transform: rotate(180deg);
  }
}

.custom-dropdown-menu {
  /* Position is handled dynamically via inline styles */
  background-color: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
  /* margin-top removed as we position exactly */
  padding: 0;
  padding: 0;
  max-height: 160px; /* Approx 4 items */
  overflow-y: auto;
  z-index: 10;
  width: 100%;
  box-sizing: border-box;
}

.dropdown-item {
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.15s ease;
  font-size: 14px;
  color: #111827;
  border-bottom: 1px solid #eee;

  &:hover {
    background-color: #f3f4f6;
  }
}

.dropdown-item:last-child {
  border-bottom: none;
}

.dropdown-divider {
  height: 1px;
  background-color: #e5e7eb;
  margin: 0;
}
</style>

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
              <h3>Extract Books</h3>
              <p>
                <i>
                  How to convert your books above into structured information, like title and
                  author.
                </i>
              </p>
            </div>

            <label>
              <strong>Extractor</strong>
              <br>
              <select v-model="bulkSearchState._activeExtractorIndex">
                <option
                  v-for="(extractor, index) in bulkSearchState.extractors"
                  :key="index"
                  :value="index"
                >
                  {{ extractor.label }}
                </option>
              </select>
            </label>

            <label v-if="showApiKey">
              <strong>OpenAI API Key</strong>
              <br>
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
          :class="{ progressCardDisabled: matchBooksDisabled }"
        >
          <div class="numeral">
            2
          </div>
          <div class="info">
            <div class="heading">
              <h3>Match Books</h3>
              <p>
                <i>
                  Once structured data has been found, it's time to match it to a book in
                  OpenLibrary!
                </i>
              </p>
            </div>

            <label>
              <strong>Options</strong>
              <br>
              <input
                v-model="bulkSearchState.matchOptions.includeAuthor"
                type="checkbox"
              >
              Use author in search query
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
          :class="{ progressCardDisabled: thirdStepLocked }"
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
                <i>
                  Now that you've found your books, why not save them to your reading log? Or a
                  list?
                </i>
              </p>
            </div>

            <div class="list-actions">
              <label>
                <strong>Save to</strong>
                <select
                  v-model="selectedListAction"
                  :disabled="thirdStepLocked"
                >
                  <option value="create">Create new list</option>
                  <option
                    value="existing"
                    :disabled="!userLists.length"
                  >
                    Add to existing list
                  </option>
                </select>
              </label>

              <div
                v-if="selectedListAction === 'existing'"
                class="list-dropdown-wrapper"
              >
                <strong>Select a list</strong>
                <div
                  class="custom-dropdown-trigger"
                  :class="{ open: dropdownOpen }"
                  @click="toggleDropdown"
                >
                  <span>{{ selectedListLabel || listPlaceholder }}</span>
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
                  v-if="dropdownOpen"
                  class="custom-dropdown-menu"
                >
                  <div
                    v-for="list in formattedUserLists"
                    :key="list.key"
                    class="dropdown-item"
                    :title="list.tooltip"
                    @click="selectList(list.value, list.label)"
                  >
                    <span class="list-name">{{ list.label }}</span>
                  </div>
                </div>
              </div>

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
              <p
                v-else-if="selectedListAction === 'existing' && !userLists.length"
                class="list-message list-message-hint"
              >
                You don't have any lists yet. Create one first to save matches here.
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
const LIST_KEY_STORAGE_KEY = 'bulkSearch.selectedExistingListKey'

import { sampleData } from '../utils/samples.js'
import { BulkSearchState } from '../utils/classes.js'
import { buildSearchUrl } from '../utils/searchUtils.js'

export default {
    props: {
        bulkSearchState: BulkSearchState
    },

    data() {
        return {
            selectedValue: '',
            showPassword: true,
            sampleData,
            loadingExtractedBooks: false,
            loadingMatchedBooks: false,
            matchBooksDisabled: true,
            createListDisabled: true,
            userLists: [],
            listOptionsLoading: false,
            listOptionsError: '',
            savingMatches: false,
            selectedListAction: 'create',
            selectedExistingListKey: '',
            restoredSelection: false,
            dropdownOpen: false,
            selectedListLabel: ''
        }
    },

    computed: {
        showApiKey() {
            if (this.bulkSearchState.activeExtractor) return 'model' in this.bulkSearchState.activeExtractor
            return false
        },

        extractBooksText() {
            return this.loadingExtractedBooks ? 'Loading...' : 'Extract Books'
        },

        matchBooksText() {
            return this.loadingMatchedBooks ? 'Loading...' : 'Match Books'
        },

        showColumnHint() {
            if (this.bulkSearchState.activeExtractor) return this.bulkSearchState.activeExtractor.name === 'table_extractor'
            return false
        },

        saveButtonDisabled() {
            if (this.savingMatches) return true
            if (this.selectedListAction === 'existing') return this.matchBooksDisabled || !this.selectedExistingListKey
            return this.createListDisabled || this.matchBooksDisabled
        },

        saveButtonText() {
            if (this.savingMatches) return 'Saving...'
            return this.selectedListAction === 'existing' ? 'Add to List' : 'Create List'
        },

        thirdStepLocked() {
            return this.matchBooksDisabled || this.createListDisabled
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
                        label: countLabel ? `${name} (${countLabel})` : name,
                        tooltip: tooltipParts.join(' | ')
                    }
                })
                .sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }))
        },

        listPlaceholder() {
            if (this.listOptionsLoading) return 'Loading your lists...'
            if (!this.formattedUserLists.length) return 'No lists available'
            return 'Select a list'
        },

        listMenuDisabled() {
            return this.thirdStepLocked || this.listOptionsLoading || !this.formattedUserLists.length
        }
    },

    watch: {
        selectedValue(newValue) {
            if (newValue !== '') this.bulkSearchState.inputText = newValue
        },

        selectedListAction(newAction) {
            if (newAction !== 'existing') {
                this.selectedExistingListKey = ''
                this.listOptionsError = ''
            }
        },

        selectedExistingListKey(newValue) {
            this.$emit('list-selected', newValue)
            this.persistSelectedList(newValue)
        }
    },

    mounted() {
        this.loadUserLists()
    },

    methods: {
        toggleDropdown() {
            if (this.listMenuDisabled) return
            this.dropdownOpen = !this.dropdownOpen
        },

        selectList(value, label) {
            this.selectedExistingListKey = value
            this.selectedListLabel = label
            this.dropdownOpen = false
            this.$emit('list-selected', value)
        },

        clearExtractionErrors() {
            if (!Array.isArray(this.bulkSearchState.errorMessage)) {
                this.$set(this.bulkSearchState, 'errorMessage', [])
                return
            }
            this.bulkSearchState.errorMessage = []
        },

        async extractBooks() {
            if (this.loadingExtractedBooks) return
            const extractor = this.bulkSearchState.activeExtractor
            if (!extractor) return

            this.clearExtractionErrors()
            this.loadingExtractedBooks = true
            this.matchBooksDisabled = true
            this.createListDisabled = true

            try {
                const extractedData = await extractor.run(
                    this.bulkSearchState.extractionOptions,
                    this.bulkSearchState.inputText
                )

                this.bulkSearchState.matchedBooks = extractedData

                if (!extractedData.length) {
                    this.bulkSearchState.errorMessage = ['No books detected. Try adjusting your input.']
                    return
                }

                this.matchBooksDisabled = false
            } catch (error) {
                const message = error instanceof Error ? error.message : 'Unable to extract books.'
                this.bulkSearchState.errorMessage = [message]
            } finally {
                this.loadingExtractedBooks = false
            }
        },

        async matchBooks() {
            if (this.loadingMatchedBooks || !this.bulkSearchState.matchedBooks.length) {
                if (!this.bulkSearchState.matchedBooks.length) {
                    this.bulkSearchState.errorMessage = ['Extract books before matching.']
                }
                return
            }

            this.clearExtractionErrors()

            const fetchSolrBook = async (book, matchOptions) => {
                try {
                    const response = await fetch(buildSearchUrl(book, matchOptions, true))
                    return await response.json()
                } catch (error) {
                    return undefined
                }
            }

            this.loadingMatchedBooks = true

            try {
                const results = await Promise.all(
                    this.bulkSearchState.matchedBooks.map(async (bookMatch) => {
                        const solrDocs = await fetchSolrBook(bookMatch.extractedBook, this.bulkSearchState.matchOptions)
                        bookMatch.solrDocs = solrDocs || { docs: [] }
                        return bookMatch
                    })
                )

                this.matchBooksDisabled = !this.bulkSearchState.matchedBooks.length
                const hasResults = results.some((result) => result?.solrDocs?.docs?.length)
                this.createListDisabled = !this.bulkSearchState.seedKeys.length

                if (!hasResults) {
                    this.bulkSearchState.errorMessage = ['Unable to find matches on Open Library.']
                }
            } catch (error) {
                const message = error instanceof Error ? error.message : 'Unable to match books.'
                this.bulkSearchState.errorMessage = [message]
            } finally {
                this.loadingMatchedBooks = false
            }
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
                this.restoreSavedSelection()
            } catch (error) {
                this.listOptionsError = 'Unable to load your lists.'
                this.userLists = []
            } finally {
                this.listOptionsLoading = false
            }
        },

        async saveMatches() {
            if (this.savingMatches || this.matchBooksDisabled || this.createListDisabled) return

            if (this.selectedListAction === 'existing') {
                this.savingMatches = true
                try {
                    await this.saveToExistingList()
                } finally {
                    this.savingMatches = false
                }
            } else {
                this.savingMatches = true
                try {
                    this.saveToNewList()
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
            if (!this.selectedExistingListKey) {
                this.listOptionsError = 'Please select a list.'
                return
            }

            const seeds = this.bulkSearchState.listString

            if (!seeds) {
                this.listOptionsError = 'No matched books to add.'
                return
            }

            this.listOptionsError = ''
            const listUrl = `${this.selectedExistingListKey}?seeds=${encodeURIComponent(seeds)}`
            window.open(listUrl, '_blank')
        },

        restoreSavedSelection() {
            if (this.restoredSelection || !this.canUseLocalStorage()) return

            const savedListKey = localStorage.getItem(LIST_KEY_STORAGE_KEY)
            if (savedListKey && this.formattedUserLists.some((list) => list.value === savedListKey)) {
                this.selectedExistingListKey = savedListKey
            }

            this.restoredSelection = true
        },

        persistSelectedList(listKey) {
            if (!this.canUseLocalStorage()) return

            if (!listKey) {
                localStorage.removeItem(LIST_KEY_STORAGE_KEY)
                return
            }

            localStorage.setItem(LIST_KEY_STORAGE_KEY, listKey)
        },

        canUseLocalStorage() {
            return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
        }
    }
}
</script>

<style lang="less">
.bulk-search-controls {
  padding: 20px;
}

label input {
  flex: 1;
}

.sampleBar {
  float: right;
  margin-bottom: 5px;
}

textarea {
  width: 100%;
  height: 120px;
  display: flex;
  resize: vertical;
  box-sizing: border-box;
}

.progressCarousel {
  display: flex;
  overflow-x: auto;
  overflow-y: visible;
  column-gap: 10px;
}

.progressCard {
  background-color: #c7e3fc;
  padding: 16px;
  width: min(450px, 66vw);
  height: fit-content;
  border-radius: 30px;
  display: flex;
  column-gap: 16px;
  flex-shrink: 0;
  overflow: visible;

  .info {
    display: flex;
    flex-direction: column;
    row-gap: 10px;

    .heading {
      color: #0376b8;

      h3 {
        margin: 0;
      }

      p {
        margin: 0;
      }
    }

    select {
      width: 100%;
    }

    button {
      background-color: #0376b8;
      color: white;
      border-radius: 4px;
      box-shadow: none;
      border: none;
      padding: 0.5rem;
      transition: background-color 0.2s;
      min-width: 140px;
      align-self: center;

      &:not([disabled]) {
        cursor: pointer;

        &:hover {
          background-color: #014c78;
        }
      }
    }
  }

  .numeral {
    border-radius: 50%;
    height: 48px;
    width: 48px;
    background-color: white;
    color: #0376b8;
    font-weight: bold;
    justify-content: center;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    font-size: 24px;
  }
}

.progressCardDisabled {
  opacity: 50%;
}

.list-actions {
  display: flex;
  flex-direction: column;
  row-gap: 12px;
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

.list-dropdown-wrapper {
  display: flex;
  flex-direction: column;
  row-gap: 8px;
  width: 100%;
}

.api-key-bar {
  width: 100%;
  box-sizing: border-box;
}

.custom-dropdown-trigger {
  width: 100%;
  padding: 0.75rem 1rem;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background-color: #fff;
  color: #111827;
  font-size: 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  box-sizing: border-box;

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
  background-color: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
  margin-top: 8px;
  padding: 0;
  max-height: 240px;
  overflow-y: auto;
  z-index: 10;
  width: 100%;
  box-sizing: border-box;
}

.dropdown-item {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  cursor: pointer;
  transition: background 0.15s ease;
  border-bottom: 1px solid #000;

  &:hover {
    background-color: #f3f4f6;
  }
}

.dropdown-item:last-child {
  border-bottom: none;
}

.list-name {
  font-weight: 500;
  color: #111827;
}

.list-icon {
  display: none;
}
</style>

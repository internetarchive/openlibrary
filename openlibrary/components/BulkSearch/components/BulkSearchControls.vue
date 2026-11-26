<template>
    <div class="bulk-search-controls">
        <div>
            <p v-if="showColumnHint">{{ strings.columnHint }}</p>
            <p class="bulk-search-instructions">
                <strong>{{ strings.enterBooks }}</strong> {{ strings.enterBooksHint }}
            </p>

            <select v-model="selectedValue" class="sampleBar">
                <option v-for="sample in sampleData" :key="sample.source" :value="sample.text">
                    {{ sample.name }}
                </option>
            </select>
            <textarea v-model="bulkSearchState.inputText" :placeholder="strings.inputPlaceholder" />
            <br />
            <div class="progressCarousel">
                <div ref="step1" class="progressCard" :class="{ activeStep: activeStep === 1 }">
                    <div class="numeral">1</div>
                    <div class="info">
                        <div class="heading">
                            <h3>{{ strings.extractBooks }}</h3>
                            <p>
                                <i>{{ strings.extractDescription }}</i>
                            </p>
                        </div>
                        <label
                            ><strong>{{ strings.extractor }}</strong> <br />
                            <select v-model="bulkSearchState._activeExtractorIndex">
                                <option v-for="(extractor, index) in bulkSearchState.extractors" :key="index" :value="index">
                                    {{ extractor.label }}
                                </option>
                            </select></label
                        >

                        <label v-if="showApiKey"
                            ><strong>{{ strings.apiKey }}</strong> <br />
                            <input
                                v-model="bulkSearchState.extractionOptions.openaiApiKey"
                                class="api-key-bar"
                                :type="showPassword ? 'password' : 'text'"
                                :placeholder="strings.apiKeyPlaceholder"
                                @focus="showPassword = false"
                                @blur="showPassword = true"
                            />
                        </label>

                        <button :disabled="loadingExtractedBooks" @click="extractBooks">
                            {{ extractBooksText }}
                        </button>
                    </div>
                </div>
                <div ref="step2" class="progressCard" :class="{ progressCardDisabled: matchBooksDisabled, activeStep: activeStep === 2 }">
                    <div class="numeral">2</div>
                    <div class="info">
                        <div class="heading">
                            <h3>{{ strings.matchBooks }}</h3>
                            <p>
                                <i>{{ strings.matchDescription }}</i>
                            </p>
                        </div>
                        <label
                            ><strong>{{ strings.options }}</strong> <br />
                            <input v-model="bulkSearchState.matchOptions.includeAuthor" type="checkbox" /> {{ strings.useAuthor }}
                        </label>
                        <button :disabled="loadingMatchedBooks || matchBooksDisabled" @click="matchBooks">
                            {{ matchBooksText }}
                        </button>
                    </div>
                </div>
                <div ref="step3" class="progressCard" :class="{ progressCardDisabled: createListDisabled, activeStep: activeStep === 3 }">
                    <div class="numeral">3</div>
                    <div class="info">
                        <div class="heading">
                            <h3 class="heading">{{ strings.saveMatches }}</h3>
                            <p class="heading">
                                <i>{{ strings.saveDescription }}</i>
                            </p>
                        </div>
                        <div v-if="bulkSearchState?.matchedBooks.length < 50">
                            <a id="listMakerLink" :href="bulkSearchState.listUrl" target="_blank"
                                ><button :disabled="createListDisabled">{{ strings.addToList }}</button></a
                            >
                        </div>
                        <form v-else method="POST" action="/account/lists/add" target="_blank">
                            <input type="hidden" name="seeds" :value="bulkSearchState?.listString" />
                            <button type="submit">{{ strings.addToList }}</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
        <div v-if="bulkSearchState.errorMessage">
            <p v-for="error in bulkSearchState.errorMessage" :key="error">
                {{ error }}
            </p>
        </div>
    </div>
</template>

<script>
import { _ } from '../../../plugins/openlibrary/js/i18n.js';
import { sampleData } from '../utils/samples.js';
import { BulkSearchState } from '../utils/classes.js';
import { buildSearchUrl } from '../utils/searchUtils.js';
export default {
    props: {
        bulkSearchState: BulkSearchState
    },
    data() {
        return {
            strings: {
                // NOTE: "Title", "Author" and "ISBN" are the column names the spreadsheet must use, so keep them in English.
                columnHint: _('Please include a header row. Supported columns include: "Title", "Author", "ISBN".'),
                enterBooks: _('Enter your books below.'),
                enterBooksHint: _('One per line, or paste from a spreadsheet.'),
                inputPlaceholder: _('Enter your books...'),
                extractBooks: _('Extract Books'),
                extractDescription: _('How to convert your books above into structured information, like title and author.'),
                extractor: _('Extractor'),
                apiKey: _('OpenAI API Key'),
                apiKeyPlaceholder: _('OpenAI API key here....'),
                loading: _('Loading...'),
                matchBooks: _('Match Books'),
                matchDescription: _("Once structured data has been found, it's time to match it to a book in OpenLibrary!"),
                options: _('Options'),
                useAuthor: _('Use author in search query'),
                saveMatches: _('Save your Matches'),
                saveDescription: _("Now that you've found your books, why not save them to your reading log? Or a list?"),
                addToList: _('Add to list')
            },
            selectedValue: '',
            showPassword: true,
            sampleData: sampleData,
            loadingExtractedBooks: false,
            loadingMatchedBooks: false,
            matchBooksDisabled: true,
            createListDisabled: true
        };
    },
    computed: {
        activeStep() {
            if (!this.createListDisabled) {
                return 3;
            } else if (!this.matchBooksDisabled) {
                return 2;
            } else {
                return 1;
            }
        },
        showApiKey() {
            if (this.bulkSearchState.activeExtractor) return 'model' in this.bulkSearchState.activeExtractor;
            return false;
        },
        extractBooksText() {
            return this.loadingExtractedBooks ? this.strings.loading : this.strings.extractBooks;
        },
        matchBooksText() {
            return this.loadingMatchedBooks ? this.strings.loading : this.strings.matchBooks;
        },
        showColumnHint() {
            if (this.bulkSearchState.activeExtractor) return this.bulkSearchState.activeExtractor.name === 'table_extractor';
            return false;
        }
    },
    watch: {
        selectedValue(newValue) {
            if (newValue !== '') {
                this.bulkSearchState.inputText = newValue;
            }
        },
        activeStep(newValue) {
            this.$nextTick(() => {
                this.$refs[`step${newValue}`]?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
            });
        }
    },
    methods: {
        togglePasswordVisibility() {
            this.showPassword = !this.showPassword;
        },
        async extractBooks() {
            this.loadingExtractedBooks = true;
            const extractedData = await this.bulkSearchState.activeExtractor.run(this.bulkSearchState.extractionOptions, this.bulkSearchState.inputText);
            this.bulkSearchState.matchedBooks = extractedData;
            this.loadingExtractedBooks = false;
            this.matchBooksDisabled = false;
            this.createListDisabled = true;
        },
        async matchBooks() {
            const fetchSolrBook = async function (book, matchOptions) {
                try {
                    const data = await fetch(buildSearchUrl(book, matchOptions, true));
                    return await data.json();
                } catch (error) {
                    // Silence errors - failing to match a book is expected
                }
            };
            this.loadingMatchedBooks = true;
            for (const bookMatch of this.bulkSearchState.matchedBooks) {
                bookMatch.solrDocs = await fetchSolrBook(bookMatch.extractedBook, this.bulkSearchState.matchOptions);
            }
            this.loadingMatchedBooks = false;
            this.createListDisabled = false;
        }
    }
};
</script>

<style>
.bulk-search-controls {
    padding: 20px;
}

.bulk-search-instructions {
    margin-bottom: 10px;
    padding: 8px 12px;
    background-color: #f0f7ff;
    border-left: 4px solid #0376b8;
    border-radius: 4px;
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
    overflow-x: scroll;
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
    border: 1px solid transparent;
    border-bottom: 5px solid transparent;
}

.progressCard.activeStep {
    border-color: #0376b8;
}
.progressCard .info {
    display: flex;
    flex-direction: column;
    row-gap: 10px;
}
.progressCard .info .heading {
    color: #0376b8;
}
.progressCard .info .heading h3 {
    margin: 0px;
}
.progressCard .info .heading p {
    margin: 0px;
}
.progressCard .info select {
    width: 100%;
}
.progressCard .info button {
    background-color: #0376b8;
    color: white;
    border-radius: 4px;
    box-shadow: none;
    border: none;
    padding: 0.5rem;
    transition: background-color 0.2s;
    min-width: 140px;
    align-self: center;
}
.progressCard .info button:not([disabled]) {
    cursor: pointer;
}
.progressCard .info button:not([disabled]):hover {
    background-color: #014c78;
}
.progressCard .numeral {
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

.progressCardDisabled {
    opacity: 50%;
}

.api-key-bar {
    width: 100%;
    box-sizing: border-box;
}
</style>

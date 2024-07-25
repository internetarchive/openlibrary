


<template>
    <details open class="bulk-search-controls">
        <summary>Input</summary>
        <div>
            <textarea v-model="bulkSearchState.inputText"></textarea>
            <br />
            <label>Format: <select @change="selectAlgorithm">
                    <option value="0">e.g. "The Wizard of Oz by L. Frank Baum"</option>
                    <option value="1">e.g. "L. Frank Baum - The Wizard of Oz" </option>
                    <option value="2">e.g. "The Wizard of Oz - L. Frank Baum" </option>
                    <option value="3">e.g. "The Wizard of Oz (L. Frank Baum)"</option>
                    <option value="4">Wikipedia Citation (e.g. Baum, Frank L. (1994). The Wizard of Oz)</option>
                    <option value="5">✨ AI Extraction</option>
                </select></label>
            <label v-if="this.showApiKey">OpenAI API Key:
                <input v-if="showPassword" type="password" v-on:click="togglePasswordVisibility()" v-model="bulkSearchState.extractionOptions.api_key" />

                <input v-else type="text" v-on:click="togglePasswordVisibility" v-model="bulkSearchState.extractionOptions.api_key" />
            </label>
            <label>Sample Data:
                <select v-model="selectedValue">
                    <option v-for="sample in sampleData" :value = "sample.text" :key = "sample.source"> {{sample.name}} </option>
                </select>
            </label>
            <label>
                <input v-model="bulkSearchState.matchOptions.includeAuthor" type="checkbox" /> Use author in
                search query
            </label>
            <br>
            <button v-on:click="extractBooks">Extract Books</button>
            <button v-on:click="matchBooks">Match Books</button>
        </div>
        <div v-if="bulkSearchState.errorMessage">
            <p v-for="error in bulkSearchState.errorMessage" :key="error">
                {{ error }}</p>
        </div>
    </details>
</template>

<script>
import {sampleData} from '../utils/samples.js';
import { BulkSearchState, RegexExtractor, AIExtractor} from '../utils/classes.js';
import { buildSearchUrl, buildListUrl } from '../utils/searchUtils.js'
export default {

    props: {
        bulkSearchState: BulkSearchState
    },
    data() {
        return {
            selectedValue: '',

            showPassword: true,
            sampleData: sampleData,
            extractors: [
                new RegexExtractor('e.g. "The Wizard of Oz by L. Frank Baum"', '(^|>)(?<title>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+(by|[-\u2013\u2014\\t])\\s+(?<author>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)'),
                new RegexExtractor('e.g. "L. Frank Baum - The Wizard of Oz"', '(^|>)(?<author>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+[,-\u2013\u2014\\t]\\s+(?<title>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)'),
                new RegexExtractor('e.g. "The Wizard of Oz - L. Frank Baum"', '(^|>)(?<title>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+[,-\u2013\u2014\\t]\\s+(?<author>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)'),
                new RegexExtractor('e.g. "The Wizard of Oz (L. Frank Baum)"', '^(?<title>[\\p{L}].{1,250})\\s\\(?<author>(.{3,70})\\)$$'),
                new RegexExtractor('Wikipedia Citation (e.g. Baum, Frank L. (1994). The Wizard of Oz)', '^(?<author>[^.()]+).*?\\)\\. (?<title>[^.]+)'),
                new AIExtractor('✨ AI Extraction', 'gpt-4o-mini')
            ]

        }
    },
    watch: {
        selectedValue(newValue) {
            if (newValue!==''){
                this.bulkSearchState.inputText = newValue;
            }
        }
    },
    computed: {
        showApiKey(){
            if (this.bulkSearchState.extractionMethod) return 'model' in this.bulkSearchState.extractionMethod
            return false
        }
    },
    methods: {
        togglePasswordVisibility(){
            this.showPassword= !this.showPassword
        },
        selectAlgorithm(e) {
            this.bulkSearchState.extractionMethod = this.extractors[e.target.value]
        },
        async extractBooks() {
            const extractedData = await this.bulkSearchState.extractionMethod.run(this.bulkSearchState.extractOptions, this.bulkSearchState.inputText)
            this.bulkSearchState.matchedBooks = extractedData
        },
        async matchBooks() {
            const fetchSolrBook = async function (book, matchOptions) {

                try {
                    const data = await fetch(buildSearchUrl(book, matchOptions, true))
                    return await data.json()
                }
                catch (error) {}
            }
            for (const bookMatch of this.bulkSearchState.matchedBooks) {
                bookMatch.solrDocs = await fetchSolrBook(bookMatch.extractedBook, this.bulkSearchState.matchOptions)
            }
            this.bulkSearchState.listUrl = buildListUrl(this.bulkSearchState.matchedBooks)
        },

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

textarea {
    width: 100%;
    display: flex;
    resize: vertical;
    box-sizing: border-box;
}
</style>




<template>
    <details open class="bulk-search-controls">
        <summary>Input</summary>
        <div>
            <textarea v-model="bulkSearchState.inputText"></textarea>
            <br />
            <label>Format: <select @change="selectAlgorithm">
                    <option value="1">e.g. "The Wizard of Oz by L. Frank Baum"</option>
                    <option value="2">e.g. "L. Frank Baum - The Wizard of Oz" </option>
                    <option value="3">e.g. "The Wizard of Oz - L. Frank Baum" </option>
                    <option value="4">e.g. "The Wizard of Oz (L. Frank Baum)"</option>
                    <option value="5">Wikipedia Citation (e.g. Baum, Frank L. (1994). The Wizard of Oz)</option>
                    <option value="6">✨ AI Extraction</option>
                </select></label>
            <label v-if="bulkSearchState.extractionOptions.use_gpt">OpenAI API Key:
                <input v-if="showPassword" type="password" @click="togglePasswordVisibility()" v-model="bulkSearchState.extractionOptions.api_key" />

                <input v-else type="text" @click="togglePasswordVisibility()" v-model="bulkSearchState.extractionOptions.api_key" />
            </label>
            <SampleBar @sample="(msg) => bulkSearchState.inputText = msg" />
            <label>
                <input v-model="bulkSearchState.matchOptions.includeAuthor" type="checkbox" /> Use author in
                search query
            </label>
            <br>
            <button @click="extractBooks">Extract Books</button>
            <button @click="matchBooks">Match Books</button>
        </div>
        <div v-if="bulkSearchState.errorMessage">
            <p v-for="error in bulkSearchState.errorMessage" :key="error">
                {{ error }}</p>
        </div>
    </details>
</template>

<script>
import SampleBar from './SampleBar.vue'
import { BulkSearchState, ExtractedBook, BookMatch } from '../utils/classes.js';
import { buildSearchUrl, buildListUrl } from '../utils/searchUtils.js'
export default {
    components: {
        SampleBar
    },
    props: {
        bulkSearchState: BulkSearchState
    },
    data() {
        return {
            showPassword: true,
            regexDict: {
                '': '',
                1: new RegExp('(^|>)(?<title>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+(by|[-\u2013\u2014\\t])\\s+(?<author>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)', 'gmu'),
                2: new RegExp('(^|>)(?<author>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+[,-\u2013\u2014\\t]\\s+(?<title>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)', 'gmu'),
                3: new RegExp('(^|>)(?<title>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+[,-\u2013\u2014\\t]\\s+(?<author>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)', 'gmu'),
                4: new RegExp('^(?<title>[\\p{L}].{1,250})\\s\\(?<author>(.{3,70})\\)$$', 'gmu'),
                5: new RegExp('^(?<author>[^.()]+).*?\\)\\. (?<title>[^.]+)', 'gmu')
            }
        }
    },
    methods: {
        togglePasswordVisibility(){
            this.showPassword= !this.showPassword
        },
        selectAlgorithm(e) {
            if (e.target.value === '6') {
                this.bulkSearchState.extractionOptions.use_gpt = true
            }
            else {
                this.bulkSearchState.extractionOptions.use_gpt = false
                this.bulkSearchState.extractionOptions.regex = this.regexDict[e.target.value]
            }
        },
        async extractBooks() {
            this.bulkSearchState.errorMessage = []
            if (this.bulkSearchState.extractionOptions.use_gpt) {
                const request = {

                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${this.bulkSearchState.extractionOptions.api_key}`
                    },
                    body: JSON.stringify({
                        model: 'gpt-3.5-turbo',
                        response_format: { type: 'json_object' },
                        messages: [
                            {
                                role: 'system',
                                content: 'You are a book extraction system. You will be given a free form passage of text containing references to books, and you will need to extract the book titles, author, and optionally ISBN in a JSON array.'
                            },
                            {
                                role: 'user',
                                content: `Please extract the books from the following text:\n\n${this.bulkSearchState.inputText}`,
                            }
                        ],
                    })

                }
                try {
                    const resp = await fetch('https://api.openai.com/v1/chat/completions', request)

                    if (!resp.ok) {
                        const status = resp.status
                        if (status === 401) {

                            this.bulkSearchState.errorMessage.push('Error: Incorrect Authorization key.')
                        }
                        throw new Error('Network response was not okay.')
                    }
                    const data = await resp.json()
                    this.bulkSearchState.extractedBooks = JSON.parse(data.choices[0].message.content)['books'].map((entry) => new ExtractedBook(entry?.title, entry?.author))
                    this.bulkSearchState.matchedBooks = JSON.parse(data.choices[0].message.content)['books'].map((entry) => new BookMatch(new ExtractedBook(entry?.title, entry?.author), {}))
                }
                catch (error) {

                }

            }
            else {
                const regex = this.bulkSearchState.extractionOptions.regex
                if (regex && this.bulkSearchState.inputText) {
                    const data = [...this.bulkSearchState.inputText.matchAll(regex)]

                    this.bulkSearchState.extractedBooks = data.map((entry) => new ExtractedBook(entry.groups?.title, entry.groups?.author))
                    this.bulkSearchState.matchedBooks = this.bulkSearchState.extractedBooks.map((entry) => new BookMatch(entry, []))
                }
            }
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

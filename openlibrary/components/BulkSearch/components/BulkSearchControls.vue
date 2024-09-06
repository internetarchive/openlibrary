


<template>
    <div class="bulk-search-controls">

        <div>
            <p v-if="showColumnHint">Please include a header row. Supported columns include: "Title", "Author".</p>

            <select class = "sampleBar" v-model="selectedValue">
                <option v-for="sample in sampleData" :value = "sample.text" :key = "sample.source"> {{sample.name}} </option>
            </select>
            <textarea v-model="bulkSearchState.inputText" placeholder = "Enter your books..."></textarea>
            <br />
            <div class = "progressCarousel">
                <div class="progressCard">
                    <div class = "numeral">1</div>
                    <div class = "info">
                        <h3 class="heading"> Extract Books</h3>
                        <p class="heading"><i>How to convert your books above into structured information, like title and author.</i></p>

                        <label><strong> Extractor:</strong> <br> <select v-model="bulkSearchState._activeExtractorIndex">
                            <option v-for="extractor, index in bulkSearchState.extractors" :value = "index" :key="index">
                                {{ extractor.label }}
                            </option>
                        </select></label>
                        <div v-if="this.showApiKey">
                        <label ><strong>OpenAI API Key:</strong> <br>
                            <input v-if="showPassword" placeholder= "Enter your OpenAI API key to use this feature." type="password" @click="togglePasswordVisibility()" v-model="bulkSearchState.extractionOptions.openaiApiKey" />

                            <input v-else type="text" placeholder= "OpenAI API key here...." @click="togglePasswordVisibility" v-model="bulkSearchState.extractionOptions.openaiApiKey" />
                        </label>
                        </div>

                        <button @click="extractBooks" :disabled="loadingExtractedBooks">{{ extractBooksText }}</button>
                    </div>
                </div>
                <div class = "progressCard" :class="{ progressCardDisabled: matchBooksDisabled}">
                    <div class = "numeral">2</div>
                    <div class="info">

                        <h3 class="heading">Match Books</h3>
                        <p class="heading"><i>Once structured data has been found, it's time to match it to a book in OpenLibrary!</i></p>

                        <label><strong>Options:</strong> <br>
                            <input v-model="bulkSearchState.matchOptions.includeAuthor" type="checkbox" /> Use author in
                            search query
                        </label>
                        <button @click="matchBooks" :disabled="loadingMatchedBooks || matchBooksDisabled">{{ matchBooksText }}</button>
                    </div>
                </div>
                <div class = "progressCard" :class="{ progressCardDisabled: createListDisabled }">
                    <div class = "numeral">3</div>
                    <div class="info">

                            <h3 class="heading">Save your Matches</h3>
                            <p class="heading"><i> Now that you've found your books, why not save them to your reading log? Or a list?</i></p>

                        <a :href="bulkSearchState.listUrl" target="_blank" id="listMakerLink"><button :disabled="createListDisabled">Add to list</button></a>
                    </div>
                </div>
            </div>



        </div>
        <div v-if="bulkSearchState.errorMessage">
            <p v-for="error in bulkSearchState.errorMessage" :key="error">
                {{ error }}</p>
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
    data() {
        return {
            selectedValue: '',
            showPassword: true,
            sampleData: sampleData,
            loadingExtractedBooks: false,
            loadingMatchedBooks: false,
            matchBooksDisabled: true,
            createListDisabled: true,
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
    },
    methods: {
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
    margin:0.25rem;
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
    padding: 16px 12px;
    width: 525px;
    height:fit-content;
    border-radius:1rem;
    display:flex;
    column-gap:16px;
    flex-shrink:0;
    .info{
        display:flex;
        flex-direction:column;
        align-items:center;
        justify-content: space-evenly;
        height:auto;
        width:auto;
        row-gap:10px;
        .heading{
            color:#0376B8;
        }
        button{
            background-color:#0376B8;
            color:white;
            border-radius:0.5rem;
            box-shadow: none;
            border:none;
            padding: 0.5rem;
            transition-duration: 0.5s;
        }
        button:hover{
            background-color: white;
            color: #0376B8;
            transition-duration: 0.5s;
            cursor:pointer;
        }
    }
    .numeral{
        border-radius: 50%;
        height:1rem;
        width:1rem;;
        padding:1rem;
        background-color:white;
        color:#0376B8;
        display:flex;
        font-weight:bold;
        justify-content:center;
    }
}

.progressCardDisabled{
    opacity:50%;
    .info{
        button:hover{
            background-color: #0376B8;
            color: white;
        }
    }
}

</style>

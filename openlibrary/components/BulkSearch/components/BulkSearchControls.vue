
<script>

import sampleBar from './SampleBar.vue'
import {BulkSearchState, ExtractedBook, BookMatch} from '../utils/classes.js';
import {buildSearchUrl} from '../utils/searchUtils.js'
export default {

    components: {
        sampleBar
    },
    props: {
        bulkSearchState: BulkSearchState
    },
    data() {
        return {

            regexDict: {
                '': '',
                1: /(^|>)(?<title>[A-Za-z][A-Za-z0-9\- ,]{1,250})\s+(by|[-–—])\s+(?<author>[A-Za-z][A-Za-z.\- ]{3,70})( \(.*)?($|<\/)/gm,
                2: /^(?<title>[A-Za-z].{1,250})\s\(?<author>(.{3,70})\)$$/gm,
                3: /^(?<author>[^.()]+).*?\)\. (?<title>[^.]+)/gm
            }
        }
    },
    methods: {
        selectAlgorithm(e){
            if (e.target.value=='4'){
                this.bulkSearchState.extractionOptions.use_gpt = true
            }
            else{
                this.bulkSearchState.extractionOptions.use_gpt = false
                this.bulkSearchState.extractionOptions.regex= this.regexDict[e.target.value]
            }
        },
        async extractBooks() {
            this.bulkSearchState.errorMessage = []
            if (this.bulkSearchState.extractionOptions.use_gpt){
                const request = {
                        
                        "method": "POST",
                        "headers": {
                            "Content-Type": "application/json",
                            "Authorization": `Bearer ${this.bulkSearchState.extractionOptions.api_key}`
                        },
                        "body": JSON.stringify({
                            "model": "gpt-3.5-turbo",
                            "response_format":{ "type": "json_object"},
            "messages": [
              {
                "role": "system",
                "content": "You are a book extraction system. You will be given a free form passage of text containing references to books, and you will need to extract the book titles, author, and optionally ISBN in a JSON array."
              },
              {
                "role": "user",
                "content": `Please extract the books from the following text:\n\n${this.bulkSearchState.inputText}`,
              }
            ],
                        })

                }
                try {
                const resp = await fetch('https://api.openai.com/v1/chat/completions', request)
                console.log(request)
                if (!resp.ok){
                    let status = resp.status
                    console.log(typeof status) 
                    if (status == 401){

                        this.bulkSearchState.errorMessage.push("Error: Incorrect Authorization key.")
                    }
                    throw new Error("Network response was not okay.")
                }
                const data = await resp.json()
                console.log(data)
                this.bulkSearchState.extractedBooks =  JSON.parse(data.choices[0].message.content)["books"].map((entry) =>  new ExtractedBook(entry?.title, entry?.author))
                this.bulkSearchState.matchedBooks=  JSON.parse(data.choices[0].message.content)["books"].map((entry) =>  new BookMatch(new ExtractedBook(entry?.title, entry?.author), {}))
            }
                catch (error){

                }
                
            }
            else{
                const regex = this.bulkSearchState.extractionOptions.regex
                if (regex && this.bulkSearchState.inputText){
                    const data = [...this.bulkSearchState.inputText.matchAll(regex)]

                    this.bulkSearchState.extractedBooks = data.map((entry) =>  new ExtractedBook(entry.groups?.title, entry.groups?.author))
                    this.bulkSearchState.matchedBooks = this.bulkSearchState.extractedBooks.map((entry) => new BookMatch(entry, []))
                }
            }
        },
        async matchBooks(){
            const fetchSolrBook= async function (book, matchOptions){

                try {

                    const data = await fetch(buildSearchUrl(book, matchOptions, true))
                    return await data.json()
                }
                catch (error) {
                    
                }

            }
            
            for (const bookMatch of this.bulkSearchState.matchedBooks) {
                bookMatch.solrDocs = await fetchSolrBook(bookMatch.extractedBook, this.bulkSearchState.matchOptions)

            }
        },

    }
}


</script>




<template>
    <details open>

        <summary>Input</summary>
  <div>
    <textarea  v-model="bulkSearchState.inputText"></textarea>
    <br />

    <label>Format: <select @change="selectAlgorithm">
      <option value="1">e.g. "The Wizard of Oz by L. Frank Baum"</option>
      <option value="2">e.g. "The Wizard of Oz (L. Frank Baum)"</option>
      <option value="3">Wikipedia Citation (e.g. Baum, Frank L. (1994). The Wizard of Oz)</option>
      <option value="4">GPT</option>
    </select></label>
    <label v-if="bulkSearchState.extractionOptions.use_gpt">API-Key:
    <input type="text" v-model="bulkSearchState.extractionOptions.api_key" /> 
    </label>
    <sampleBar @sample="(msg) => this.bulkSearchState.inputText = msg"/>
    <label>
      <input checked v-model="bulkSearchState.matchOptions.includeAuthor" type="checkbox"  /> Use author in search query
    </label>
    <br>
    <button @click="extractBooks">Extract Books</button>
    <button @click="matchBooks">Match Books</button>
  </div>
  <div class="ErrorBox" v-if="this.bulkSearchState.errorMessage">
    <p v-for="error in this.bulkSearchState.errorMessage">
    {{ error }}</p>
  </div>
</details>
</template>

<style lang="less">
body { padding :0;
    font-family: Roboto, Helvetica, sans-serif;
}

label input { flex: 1; }
textarea {
  width: 100%;
  display: flex;
}
</style>

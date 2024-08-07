export class ExtractedBook {
    constructor(title = '', author = '') {
        /** @type {string} */
        this.title = title;
        /**@type {string} */
        this.author = author;

    }
}

class ExtractionOptions {
    constructor() {
        this.use_gpt = false
        this.api_key = ''
        this.regex = ''
    }
}
class MatchOptions  {
    constructor (){
        this.includeAuthor = true;
    }
}
export class BookMatch {
    constructor(extractedBook, solrDocs){
        /** @type {ExtractedBook} */
        this.extractedBook = extractedBook;
        /** @type {SolrDoc[]} */
        this.solrDocs = solrDocs
    }
}


/** @type {string} */
const BASE_URL = 'https://openlibrary.org/lists/add?seeds='

export class ListUrl  {

    constructor(){
        this.base_url = BASE_URL
        /** @type {string[]} */
        this.seeds = []
    }

    /** @param {string} seed */
    addSeed(seed) {
        this.seeds.push(seed)
    }

    resetSeeds() {
        this.seeds = []
    }

    toString() {
        return this.base_url + this.seeds.join(',')
    }
}


export class BulkSearchState{
    constructor(){
        /** @type {string} */
        this.inputText= '';
        /** @type {ExtractedBook[]} */
        this.extractedBooks = [];
        /** @type {BookMatch[]} */
        this.matchedBooks = [];
        /** @type {MatchOptions} */
        this.matchOptions =  new MatchOptions()
        /** @type {ExtractionOptions} */
        this.extractionOptions = new ExtractionOptions();
        this.errorMessage = []
        /** @type {ListUrl} */
        this.listUrl = new ListUrl();

    }

}



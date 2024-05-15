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



export class BulkSearchState{
    constructor(){
        /** @type {string} */
        this.inputText= '';
        /** @type {ExtractedBooks[]} */
        this.extractedBooks = [];
        /** @type {BookMatch[]} */
        this.matchedBooks = [];
        /** @type {MatchOptions} */
        this.matchOptions =  new MatchOptions()
        /** @type {ExtractedOptions} */
        this.extractionOptions = new ExtractionOptions();
        this.errorMessage = []
    }

}



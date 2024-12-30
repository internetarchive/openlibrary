//@ts-check

export class ExtractedBook {
    constructor(title = '', author = '') {
        /** @type {string} */
        this.title = title;
        /**@type {string} */
        this.author = author;

    }
}

class AbstractExtractor {

    /**
     * @param {string} label
     */
    constructor(label) {
        /** @type {string} */
        this.label = label
    }
    /**
     * @param {ExtractionOptions} _extractOptions
     * @param {string} _text
     * @returns {Promise<BookMatch[]>}
     */
    async run(_extractOptions, _text) {  //eslint-disable-line no-unused-vars
        throw new Error('Not Implemented Error')
    }
}

export class RegexExtractor extends AbstractExtractor {

    name = 'regex_extractor'
    /**
     *
     * @param {string} label
     * @param {string} pattern
     */
    constructor(label, pattern){
        super(label)
        /** @type {RegExp} */
        this.pattern = new RegExp(pattern, 'gmu');
    }

    /**
     * @param {ExtractionOptions} _extractOptions
     * @param {string} text
     * @returns {Promise<BookMatch[]>}
     */
    async run(_extractOptions, text) {
        const data = [...text.matchAll(this.pattern)]
        const extractedBooks = data.map((entry) => new ExtractedBook(entry.groups?.title, entry.groups?.author))
        const matchedBooks = extractedBooks.map((entry) => new BookMatch(entry, []))
        return matchedBooks
    }
}

export class AiExtractor extends AbstractExtractor{

    name = 'ai_extractor'
    /**
     * @param {string} label
     * @param {string} model
     */
    constructor(label, model) {
        super(label)
        /** @type {string} */
        this.model = model
    }

    /**
     *
     * @param {ExtractionOptions} extractOptions
     * @param {string} text
     * @returns {Promise<BookMatch[]>}
     */
    async run(extractOptions, text) {
        const request = {

            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${extractOptions.openaiApiKey}`
            },
            body: JSON.stringify({
                model: this.model,
                response_format: { type: 'json_object' },
                messages: [
                    {
                        role: 'system',
                        content: 'You are a book extraction system. You will be given a free form passage of text containing references to books, and you will need to extract the book titles, author, and optionally ISBN in a JSON array.'
                    },
                    {
                        role: 'user',
                        content: `Please extract the books from the following text:\n\n${text}`,
                    }
                ],
            })

        }
        try {
            const resp = await fetch('https://api.openai.com/v1/chat/completions', request)

            if (!resp.ok) {
                const status = resp.status
                let errorMessage = 'Network response was not okay.'
                if (status === 401) {

                    errorMessage = `${errorMessage} Error: Incorrect Authorization key.`
                }
                throw new Error(errorMessage)
            }
            const data = await resp.json()
            return JSON.parse(data.choices[0].message.content)['books']
                .map((entry) =>
                    new BookMatch(new ExtractedBook(entry?.title, entry?.author), {})
                )
        }
        catch (error) {
            return []
        }


    }
}

export class TableExtractor extends AbstractExtractor{

    name = 'table_extractor'
    /**
     *
     * @param {string} label
     */
    constructor(label) {
        super(label)
        /** @type {string} */
        this.authorColumn = 'author'
        /** @type {string} */
        this.titleColumn = 'title'
    }

    /**
     * @param {ExtractionOptions} extractionOptions
     * @param {string} text
     * @return {Promise<BookMatch[]>}
     */
    async run(extractionOptions, text){

        /** @type {string[]} */
        const lines = text.split('\n')
        /** @type {string[][]} */
        const cells = lines.map(line => line.split('\t'))
        /** @type {{columns: String[], rows: {columnName: string}[]}} */
        const tableData = {
            columns: cells[0],
            rows: []
        }
        for (let i=1; i< cells.length; i++){
            const row = {}
            for (let j = 0; j < tableData.columns.length; j++){
                row[tableData.columns[j].trim().toLowerCase()] = cells[i][j]
            }
            // @ts-ignore
            tableData.rows.push(row)
        }
        return tableData.rows.map(
            row => new BookMatch(
                new ExtractedBook(
                    row[this.titleColumn] || '', row[this.authorColumn] || ''),
                {})
        )
    }
}

class ExtractionOptions {
    constructor() {
        /** @type {string} */
        this.openaiApiKey = ''
    }
}
class MatchOptions  {
    constructor (){
        /** @type {boolean} */
        this.includeAuthor = true;
    }
}
export class BookMatch {

    /**
     *
     * @param {ExtractedBook} extractedBook
     * @param {*} solrDocs
     */
    constructor(extractedBook, solrDocs){
        /** @type {ExtractedBook} */
        this.extractedBook = extractedBook;
        this.solrDocs = solrDocs
    }
}


const BASE_LIST_URL = 'https://openlibrary.org/account/lists/add?seeds='

export class BulkSearchState{
    constructor(){
        /** @type {string} */
        this.inputText= '';
        /** @type {BookMatch[]} */
        this.matchedBooks = [];
        /** @type {MatchOptions} */
        this.matchOptions =  new MatchOptions()
        /** @type {ExtractionOptions} */
        this.extractionOptions = new ExtractionOptions();
        /** @type {AbstractExtractor[]} */
        this.extractors =  [
            new RegexExtractor('Pattern: Title by Author', '(^|>)(?<title>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+(by|[-\u2013\u2014\\t])\\s+(?<author>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)'),
            new RegexExtractor('Pattern: Author - Title', '(^|>)(?<author>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+[,-\u2013\u2014\\t]\\s+(?<title>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)'),
            new RegexExtractor('Pattern: Title - Author', '(^|>)(?<title>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+[,-\u2013\u2014\\t]\\s+(?<author>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)'),
            new RegexExtractor('Pattern: Title (Author)', '^(?<title>[\\p{L}].{1,250})\\s\\(?<author>(.{3,70})\\)$$'),
            new RegexExtractor('Wikipedia Citation Pattern: (e.g. Baum, Frank L. (1994). The Wizard of Oz)', '^(?<author>[^.()]+).*?\\)\\. (?<title>[^.]+)'),
            new AiExtractor('✨ AI Extraction (Beta)', 'gpt-4o-mini'),
            new TableExtractor('Extract from a Table/Spreadsheet')
        ]
        /** @type {Number} */
        this._activeExtractorIndex = 0
    }

    /**@type {AbstractExtractor} */
    get activeExtractor() {
        return this.extractors[this._activeExtractorIndex]
    }
    /**@type {String} */
    get listUrl() {
        return BASE_LIST_URL + this.matchedBooks
            .map(bm => bm.solrDocs?.docs?.[0]?.key.split('/')[2])
            .filter(key => key);
    }
}



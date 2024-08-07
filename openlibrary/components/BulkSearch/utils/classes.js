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
     * @param {string} name
     */
    constructor(name) {
        /** @type {string} */
        this.name = name
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

    /**
     *
     * @param {string} name
     * @param {string} pattern
     */
    constructor(name, pattern){
        super(name)
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

    /**
     * @param {string} name
     * @param {string} model
     */
    constructor(name, model) {
        super(name)
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
        /** @type {string} */
        this.listUrl = ''
        /** @type {AbstractExtractor[]} */
        this.extractors =  [
            new RegexExtractor('e.g. "The Wizard of Oz by L. Frank Baum"', '(^|>)(?<title>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+(by|[-\u2013\u2014\\t])\\s+(?<author>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)'),
            new RegexExtractor('e.g. "L. Frank Baum - The Wizard of Oz"', '(^|>)(?<author>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+[,-\u2013\u2014\\t]\\s+(?<title>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)'),
            new RegexExtractor('e.g. "The Wizard of Oz - L. Frank Baum"', '(^|>)(?<title>[A-Za-z][\\p{L}0-9\\- ,]{1,250})\\s+[,-\u2013\u2014\\t]\\s+(?<author>[\\p{L}][\\p{L}\\.\\- ]{3,70})( \\(.*)?($|<\\/)'),
            new RegexExtractor('e.g. "The Wizard of Oz (L. Frank Baum)"', '^(?<title>[\\p{L}].{1,250})\\s\\(?<author>(.{3,70})\\)$$'),
            new RegexExtractor('Wikipedia Citation (e.g. Baum, Frank L. (1994). The Wizard of Oz)', '^(?<author>[^.()]+).*?\\)\\. (?<title>[^.]+)'),
            new AiExtractor('✨ AI Extraction', 'gpt-4o-mini')
        ]
        /** @type {Number} */
        this._activeExtractorIndex = 0
    }

    /**@type {AbstractExtractor} */
    get activeExtractor() {
        return this.extractors[this._activeExtractorIndex]
    }
}




/** @typedef {String} OLID @example OL123W */
/** @typedef {OLID} WorkOLID */
/** @typedef {OLID} EditionOLID */
/** @typedef {OLID} AuthorOLID */

/**
 * @param {EditionOLID[]} edition_ids 
 * @param {WorkOLID} old_work 
 * @param {WorkOLID} new_work 
 */
export async function move_to_work(edition_ids, old_work, new_work) {
    for (let olid of edition_ids) {
        const url = `/book/${olid}.json`;
        const record = await fetch(url).then(r => r.json());
        
        record.works = [{key: `/works/${new_work}`}];
        record._comment = 'move to correct work';
        const r = await fetch(url, { method: 'PUT', body: JSON.stringify(record) });
        console.log(`moved ${olid}; ${r.status}`);
    }
}

/**
 * @param {WorkOLID[]} edition_ids 
 * @param {AuthorOLID} old_author 
 * @param {AuthorOLID} new_author 
 */
export async function move_to_author(work_ids, old_author, new_author) {
    for (let olid of work_ids) {
        const url = `/works/${olid}.json`;
        const record = await fetch(url).then(r => r.json());
        const author = record.authors.find(a => a.author.key.includes(old_author));
        if (author) {
            author.author.key = `/authors/${new_author}`;
            record._comment = 'move to correct author';
            const r = await fetch(url, { method: 'PUT', body: JSON.stringify(record) });
            console.log(`moved ${olid}; ${r.status}`)
        } else {
            console.warn(`${old_author} not in ${url}!`);
        }
    }
}

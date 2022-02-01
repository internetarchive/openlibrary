import uniqBy from 'lodash/uniqBy';

/** @typedef {String} OLID @example OL123W */
/** @typedef {OLID} WorkOLID */
/** @typedef {OLID} EditionOLID */
/** @typedef {OLID} AuthorOLID */

/**
 * Move the given editions from one work to another.
 * @param {EditionOLID[]} edition_ids
 * @param {WorkOLID} old_work
 * @param {WorkOLID} new_work
 */
export async function move_to_work(edition_ids, old_work, new_work) {
    for (const olid of edition_ids) {
        const url = `/books/${olid}.json`;
        const record = await fetch(url).then(r => r.json());

        record.works = [{key: `/works/${new_work}`}];
        record._comment = 'move to correct work';
        const r = await fetch(url, { method: 'PUT', body: JSON.stringify(record) });
        // eslint-disable-next-line no-console
        console.log(`moved ${olid}; ${r.status}`);
    }
}

/**
 * Move the given works from one author to another.
 * @param {WorkOLID[]} edition_ids
 * @param {AuthorOLID} old_author
 * @param {AuthorOLID} new_author
 */
export async function move_to_author(work_ids, old_author, new_author) {
    for (const olid of work_ids) {
        const url = `/works/${olid}.json`;
        const record = await fetch(url).then(r => r.json());
        if (record.authors.find(a => a.author.key.includes(old_author))) {
            record.authors = uniqBy(record.authors.map(a => {
                if (!a.author.key.includes(old_author)) return a;

                const copy = JSON.parse(JSON.stringify(a));
                copy.author.key = `/authors/${new_author}`;
                return copy;
            }), a => a.author.key);
            record._comment = 'move to correct author';
            const r = await fetch(url, { method: 'PUT', body: JSON.stringify(record) });
            // eslint-disable-next-line no-console
            console.log(`moved ${olid}; ${r.status}`)
        } else {
            // eslint-disable-next-line no-console
            console.warn(`${old_author} not in ${url}!`);
        }
    }
}

/* eslint no-console: 0 */
import _ from 'lodash';

/**
 *
 * @param {string} field field from a work object
 * @param {*} value
 * @return {string}
 */
function hash_subel(field, value) {
    switch (field) {
    case 'authors':
        return (value.type.key || value.type) + value.author.key;
    case 'covers':
    case 'subjects':
    case 'subject_people':
    case 'subject_places':
    case 'subject_times':
    case 'excerpts':
    default:
        return JSON.stringify(value);
    }
}

/**
 *
 * @param {Object} master
 * @param {Object} dupes
 */
export function merge(master, dupes) {
    const result = _.cloneDeep(master);
    result.latest_revision++;
    result.revision = result.latest_revision;
    result.last_modified.value = (new Date()).toISOString().slice(0, -1);
    /** @type {{[field: string]: String}} field -> key where it came from */
    const sources = {};
    const subsources = {}; // for array elements

    for (const field in result) {
        sources[field] = [master.key];
        if (result[field] instanceof Array) {
            for (const el of result[field]) {
                subsources[field] = {
                    [hash_subel(field, el)]: [master.key]
                };
            }
        }
    }

    for (const dupe of dupes) {
        for (const field in dupe) {
            if (!(field in result) && field !== 'subtitle') {
                result[field] = dupe[field];
                sources[field] = [dupe.key];
            } else if (result[field] instanceof Array) {
                result[field] = result[field].concat(dupe[field])
                sources[field].push(dupe.key);
            }
        }
    }

    // dedup
    for (const key in result) {
        if (!(result[key] instanceof Array))
            continue;
        switch (key) {
        case 'authors':
            const authors = _.cloneDeep(result.authors);
            authors
                .filter(a => typeof a.type === 'string')
                .forEach(a => a.type = { key: a.type });
            result.authors = _.uniqWith(authors, _.isEqual);
            break;
        case 'covers':
        case 'subjects':
        case 'subject_people':
        case 'subject_places':
        case 'subject_times':
        case 'excerpts':
        default:
            result[key] = _.uniqWith(result[key], _.isEqual);
            break;
        }
    }

    return [result, sources];
}

export async function do_merge(merged_record, dupes, editions) {
    editions.forEach(ed => ed.works = [{key: merged_record.key}]);
    const edits = [
        merged_record,
        ...dupes.map(dupe => make_redirect(merged_record.key, dupe)),
        ...editions
    ];

    return await save_many(edits, 'Merge works');
}

export function make_redirect(master_key, dupe) {
    return {
        location: master_key,
        key: dupe.key,
        type: { key: '/type/redirect' }
    };
}

export function get_editions(work_key) {
    const endpoint = `${work_key}/editions.json`;
    // FIXME Fetch from prod openlibrary.org, otherwise it's outdated
    const url = location.host.endsWith('.openlibrary.org') ? `https://openlibrary.org${endpoint}` : endpoint;
    return fetch(url).then(r => r.json());
}

export function get_lists(key, limit=10) {
    return fetch(`${key}/lists.json?${new URLSearchParams({ limit })}`).then(r => r.json());
}

export function get_bookshelves(key) {
    return fetch(`${key}/bookshelves.json`).then(r => r.json());
}

export function get_ratings(key) {
    return fetch(`${key}/ratings.json`).then(r => r.json());
}


/**
 *
 * @param {Array<Object>} items
 * @param {String} comment
 */
function save_many(items, comment) {
    console.log(`Saving ${items.length} items`);
    const headers = {
        Opt: '"http://openlibrary.org/dev/docs/api"; ns=42',
        '42-comment': comment
    };

    return fetch('/api/save_many', {
        method: 'POST',
        headers,
        body: JSON.stringify(items)
    });
}

// /**
//  * @param {Object} record
//  * @param {string} comment
//  */
// function put_save(record, comment) {
//     record._comment = comment;
//     const url = `${record.key}.json`;
//     return fetch(url, {
//         method: 'PUT',
//         body: JSON.stringify(record)
//     });
// }

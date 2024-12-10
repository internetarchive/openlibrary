/* eslint no-console: 0 */
import _ from 'lodash';
import { approveRequest, declineRequest, createRequest, REQUEST_TYPES } from '../../plugins/openlibrary/js/merge-request-table/MergeRequestService'
import CONFIGS from '../configs.js';

const collator = new Intl.Collator('en-US', {numeric: true})
export const DEFAULT_EDITION_LIMIT = 200

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

export async function do_merge(merged_record, dupes, editions, mrid) {
    editions.forEach(ed => ed.works = [{key: merged_record.key}]);
    const edits = [
        merged_record,
        ...dupes.map(dupe => make_redirect(merged_record.key, dupe)),
        ...editions
    ];

    let comment = 'Merge works'
    if (mrid) {
        comment += ` (MRID: ${mrid})`
    }

    return await save_many(
        edits,
        comment,
        'merge-works',
        {
            master: merged_record.key,
            duplicates: dupes.map(dupe => dupe.key),
            mrid: mrid,
        },
    );
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
    let base = '';
    if (CONFIGS.OL_BASE_BOOKS) {
        base = CONFIGS.OL_BASE_BOOKS;
    } else {
        // FIXME Fetch from prod openlibrary.org, otherwise it's outdated
        base = location.host.endsWith('.openlibrary.org') ? 'https://openlibrary.org' : '';
    }
    return fetch(`${base}${endpoint}?${new URLSearchParams({limit: DEFAULT_EDITION_LIMIT})}`).then(r => {
        if (r.ok) return r.json();
        if (confirm(`Network error; failed to load editions for ${work_key}. Click OK to reload.`)) location.reload();
    });
}

export function get_lists(key, limit=10) {
    return fetch(`${CONFIGS.OL_BASE_BOOKS}${key}/lists.json?${new URLSearchParams({ limit })}`).then(r => {
        if (r.ok) return r.json();
        return {error: true};
    });
}

export function get_bookshelves(key) {
    return fetch(`${CONFIGS.OL_BASE_BOOKS}${key}/bookshelves.json`).then(r => {
        if (r.ok) return r.json();
        return {error: true};
    });
}

export function get_ratings(key) {
    return fetch(`${CONFIGS.OL_BASE_BOOKS}${key}/ratings.json`).then(r => {
        if (r.ok) return r.json();
        return {error: true};
    });
}

/**
 * Composes and POSTs a merge request update.
 *
 * @param {Number} mrid The unique ID of the merge request.
 * @param {'approve' | 'decline'} action What is to be done with this request.
 * @param {string} comment Optional comment from the reviewer.
 *
 * @returns {Promise<Response>} A response to the request
 */
export function update_merge_request(mrid, action, comment) {
    if (action === 'approve') {
        return approveRequest(mrid, comment)
    }
    else if (action === 'decline') {
        return declineRequest(mrid, comment)
    }
}

/**
 * Composes and POSTs a new merge request.
 *
 * @param {Array<string>} workIds Un-normalized work OLIDs
 * @param {string} primaryRecord The record in which to merge other records
 * @param {'create-merged'|'create-pending'} action Determines the status code of the new request
 * @param {string} comment Optional comment from request submitter
 *
 * @returns {Promise<Response>}
 */
export function createMergeRequest(workIds, primaryRecord, action = 'create-merged', comment = null) {
    const normalizedIds = prepareIds(workIds).join(',')
    return createRequest(normalizedIds, action, REQUEST_TYPES['WORK_MERGE'], comment, primaryRecord)
}

/**
 * Normalizes and sorts an array of OLIDs.
 *
 * OLIDs will be naturally ordered in the returned array.
 *
 * @param {Array<string>} workIds Un-normalized work OLIDs
 * @returns {Array<string>} Noralized and sorted array of OLIDs
 */
function prepareIds(workIds) {
    return Array.from(workIds, id => {
        const splitArr = id.split('/')
        return splitArr[splitArr.length - 1]
    }).sort(collator.compare)
}

/**
 *
 * @param {Array<Object>} items
 * @param {String} comment
 * @param {String} action
 * @param {Object} data
 */
function save_many(items, comment, action, data) {
    const headers = {
        Opt: '"http://openlibrary.org/dev/docs/api"; ns=42',
        '42-comment': comment,
        '42-action': action,
        '42-data': JSON.stringify(data),
    };

    return fetch(`${CONFIGS.OL_BASE_SAVES}/api/save_many`, {
        method: 'POST',
        headers,
        body: JSON.stringify(items)
    });
}

/**
 * Fetches name associated with the author key
 * @param {Object[]} works
 * @returns {Promise<Record<string,object>} A response to the request
 */
export async function get_author_names(works) {
    const authorIds = _.uniq(works).flatMap(record =>
        (record.authors || []).map(authorEntry => authorEntry.author.key)
    )

    if (!authorIds.length) return {};

    const queryParams = new URLSearchParams({
        q: `key:(${authorIds.join(' OR ')})`,
        mode: 'everything',
        fields: 'key,name',
    })

    const response = await fetch(`${CONFIGS.OL_BASE_SEARCH}/search/authors.json?${queryParams}`)

    if (!response.ok) {
        throw new Error('Failed to fetch author data');
    }

    const results = await response.json()

    const authorDirectory = {}

    for (const doc of results.docs) {
        authorDirectory[doc.key] = doc.name;
    }

    return authorDirectory
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

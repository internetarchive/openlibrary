// To run install k6 then run:
// k6 run openlibrary/fastapi/loadtest.js

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
const totalRequests = new Counter('total_http_requests');

const config = {
    old_api: {
        baseUrl: 'https://testing.openlibrary.org',
    },
    new_api: {
        baseUrl: 'https://testing.openlibrary.org/_fast',
    },
};

const test_duration = 60;
const delayBetweenScenarios = 5;

let total_duration = -1;
function getSenario(exec) {
    let startTime = '';
    if (total_duration === -1) {
        total_duration = 0;
        startTime = '0s';
    } else {
        startTime = `${total_duration += test_duration + delayBetweenScenarios}s`;
    }
    // vus are the number of virtual users
    return { executor: 'constant-vus', vus: 1, duration: `${test_duration}s`, exec, startTime };
}

const activeSenarios = [
    'authors',
    'shell',
    'languages_json',
    'search_works_html',
    'search_authors_html',
    'search_works_json',
    'works',
]

export const options = {
    // This is just some wacky code to auto generate the senarios. It's just to avoid duplicating.
    scenarios: Object.fromEntries(
        activeSenarios.flatMap(s => [
            [`new_${s}`, getSenario(`new_${s}`)],
            [`old_${s}`, getSenario(`old_${s}`)],
        ])
    ),
    thresholds: Object.fromEntries(activeSenarios.flatMap(s => [
        [`http_req_duration{endpoint:${s},version:fastapi}`, ['p(95)<2000']],
        [`http_req_duration{endpoint:${s},version:_web.py}`, ['p(95)<2000']],
    ])),
    summaryTrendStats: ['avg', 'min', 'max', 'med', 'p(95)', 'p(99)', 'count'],
};

function generateRandomString(length) {
    const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    const charactersLength = characters.length;
    for (let i = 0; i < length; i++) {
        result += characters.charAt(Math.floor(Math.random() * charactersLength));
    }
    return result;
}


export function genric_function(endpoint, label, legacy) {
    const tags = { version: legacy ? '_web.py' : 'fastapi', endpoint: label, };
    const url = `${config[legacy ? 'old_api' : 'new_api'].baseUrl}/${endpoint}`
    const res = http.get(url, { tags });
    check(res, { 'status is 200': (r) => r.status === 200 });
    totalRequests.add(1, tags);
}

export function old_search_works_json() { genric_function(`search.json?q=${generateRandomString(5)}&mode=everything`, 'search_works_json', true); }
export function new_search_works_json() { genric_function(`search.json?q=${generateRandomString(5)}&mode=everything`, 'search_works_json', false); }

export function old_languages_json() { genric_function('languages.json', 'languages_json', true); }
export function new_languages_json() { genric_function('languages.json', 'languages_json', false); }

export function old_authors() { genric_function('authors/OL26320A/J.R.R._Tolkien', 'authors', true); }
export function new_authors() { genric_function('authors/OL26320A/J.R.R._Tolkien', 'authors', false); }

export function old_works() { genric_function('works/OL54120W/The_wit_wisdom_of_Mark_Twain', 'works', true); }
export function new_works() { genric_function('works/OL54120W/The_wit_wisdom_of_Mark_Twain', 'works', false); }

export function old_search_works_html() { genric_function('search/?q=mark', 'search_works_html', true); }
export function new_search_works_html() { genric_function('search/?q=mark', 'search_works_html', false); }

export function old_search_authors_html() { genric_function('search/authors/?q=mark', 'search_authors_html', true); }
export function new_search_authors_html() { genric_function('search/authors/?q=mark', 'search_authors_html', false); }

export function old_shell() { genric_function('shell', 'shell', true); }
export function new_shell() { genric_function('shell', 'shell', false); }

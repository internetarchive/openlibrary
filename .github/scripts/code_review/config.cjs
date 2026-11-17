// Reads the code review bot's settings from .pr_agent.toml (PR-Agent's format).
// code_review_action.yml loads this module and the file from the BASE checkout, before the
// PR head is extracted, so a PR cannot change the settings that review it.
'use strict';

const fs = require('fs');
const path = require('path');

const bool = v => typeof v === 'boolean';
// Supported keys and their checks. A value that fails its check keeps the default.
const SCHEMA = {
    pr_reviewer: {
        extra_instructions: v => typeof v === 'string',
        num_max_findings: v => Number.isInteger(v) && v >= 1 && v <= 50,
        require_tests_review: bool,
        require_security_review: v => v === true, // cannot be turned off
        require_ticket_analysis_review: bool,
        inline_key_issues: bool
    },
    github_action_config: {
        handle_push_trigger: bool,
        push_trigger_ignore_bot_commits: bool,
        push_trigger_ignore_merge_commits: bool
    },
    openlibrary_reviewer: {
        require_accessibility_review: bool,
        require_styleguide_review: bool,
        push_review_delay_minutes: v => Number.isInteger(v) && v >= 1 && v <= 120
    }
};

// Today's behaviour. num_max_findings is unset: no fixed limit.
const defaults = () => ({
    pr_reviewer: {
        extra_instructions: '',
        require_tests_review: true,
        require_security_review: true,
        require_ticket_analysis_review: true,
        inline_key_issues: true
    },
    // PR-Agent's defaults: no review on push unless turned on.
    github_action_config: { handle_push_trigger: false, push_trigger_ignore_bot_commits: true, push_trigger_ignore_merge_commits: true },
    openlibrary_reviewer: { require_accessibility_review: true, require_styleguide_review: true, push_review_delay_minutes: 10 }
});

// Review dimensions a setting can turn off. Correctness and security are always reviewed.
const TOGGLES = {
    test_coverage: ['pr_reviewer', 'require_tests_review'],
    accessibility: ['openlibrary_reviewer', 'require_accessibility_review'],
    styleguide: ['openlibrary_reviewer', 'require_styleguide_review']
};

// One statement of a strict TOML subset: a comment, a [table] header, or key = value where the
// value is a string ("...", '...', '''...''', or """...""" without escapes), an integer or a boolean.
const STATEMENT =
    /\s*(?:#[^\n]*|\[([\w-]+)\]|([\w-]+)[ \t]*=[ \t]*(?:"""\n?([^\\]*?)"""|'''\n?([\s\S]*?)'''|("(?:[^"\\\n]|\\.)*")|'([^'\n]*)'|(true|false)|([+-]?(?:0|[1-9]\d*))))[ \t]*(?=#|\n|$)/y;

// Throws on anything outside the subset, and on a duplicate table or key.
function parse(text) {
    const s = text.replace(/\r\n/g, '\n');
    const root = Object.create(null);
    let table = null;
    STATEMENT.lastIndex = 0;
    while (s.slice(STATEMENT.lastIndex).trim()) {
        const at = STATEMENT.lastIndex;
        const m = STATEMENT.exec(s);
        if (!m) throw new Error(`unsupported syntax on line ${s.slice(0, at).split('\n').length}`);
        const [, header, key, multiBasic, multiLiteral, basic, literal, boolean, int] = m;
        if (header) {
            if (header in root) throw new Error(`duplicate [${header}]`);
            table = root[header] = Object.create(null);
        } else if (key) {
            if (!table || key in table) throw new Error(`unexpected key ${key}`);
            if (basic !== undefined) table[key] = JSON.parse(basic);
            else if (boolean !== undefined) table[key] = boolean === 'true';
            else if (int !== undefined) table[key] = Number(int);
            else table[key] = multiBasic ?? multiLiteral ?? literal;
        }
    }
    return root;
}

// The settings in `dir`/.pr_agent.toml. A missing or unparsable file gives the defaults.
function load(dir, log = () => {}) {
    const settings = defaults();
    let root;
    try {
        root = parse(fs.readFileSync(path.join(dir, '.pr_agent.toml'), 'utf8'));
    } catch (e) {
        log(`Using the default review settings: ${e.code === 'ENOENT' ? 'no .pr_agent.toml' : `could not read .pr_agent.toml (${e.message})`}.`);
        return settings;
    }
    for (const [section, table] of Object.entries(root)) {
        for (const [key, value] of Object.entries(table)) {
            const ok = Object.hasOwn(SCHEMA, section) && Object.hasOwn(SCHEMA[section], key) && SCHEMA[section][key];
            if (!ok) log(`.pr_agent.toml: ignoring unsupported setting ${section}.${key}`);
            else if (!ok(value)) log(`.pr_agent.toml: ignoring invalid value for ${section}.${key}`);
            else settings[section][key] = value;
        }
    }
    return settings;
}

const offDimensions = settings => Object.keys(TOGGLES).filter(d => settings[TOGGLES[d][0]][TOGGLES[d][1]] === false);

module.exports = { parse, load, defaults, offDimensions };

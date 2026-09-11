use std::collections::{HashMap, HashSet};

use serde_json::{json, Value};

use crate::helpers::{
    ddc::{choose_sorting_ddc, normalize_ddc},
    isbn::opposite_isbn,
    lcc::{choose_sorting_lcc, short_lcc_to_sortable_lcc},
    sort_title::sort_title,
};
use crate::query::IaLite;
use once_cell::sync::Lazy;

/// Port of bp.EbookAccess (openlibrary/book_providers.py:25). Keep in sync with solr/conf/enumsConfig.xml!
#[derive(PartialEq, Eq, PartialOrd, Ord, Clone, Copy, Debug)]
pub enum EbookAccess {
    NoEbook = 0,
    Unclassified = 1,
    Printdisabled = 2,
    Borrowable = 3,
    Public = 4,
}

impl EbookAccess {
    pub fn to_solr_str(self) -> &'static str {
        match self {
            EbookAccess::NoEbook => "no_ebook",
            EbookAccess::Unclassified => "unclassified",
            EbookAccess::Printdisabled => "printdisabled",
            EbookAccess::Borrowable => "borrowable",
            EbookAccess::Public => "public",
        }
    }

    /// Port of bp.EbookAccess.from_acquisition_access. Python raises on unknown literals;
    /// we degrade to NO_EBOOK instead.
    pub fn from_acquisition_access(literal: &str) -> EbookAccess {
        match literal {
            "sample" => EbookAccess::Printdisabled,
            "buy" | "subscribe" => EbookAccess::NoEbook,
            "open-access" => EbookAccess::Public,
            "borrow" => EbookAccess::Borrowable,
            _ => EbookAccess::NoEbook,
        }
    }
}

/// Maps the HTML-ish access literals some provider entries use (Acquisition.from_json).
fn acquisition_access_literal(p: &Value) -> Option<&str> {
    let raw = p
        .get("access")
        .and_then(|v| v.as_str())
        .unwrap_or("open-access");
    Some(match raw {
        "read" | "listen" => "open-access",
        "preview" => "sample",
        other => other,
    })
}

/// Minimal port of DirectProvider.get_access (book_providers.py:607): on editions the `providers`
/// field wins over IA, and the access level comes from providers[0]. DirectProvider only counts
/// when at least one acquisition has access >= PRINTDISABLED (get_identifiers filter).
fn direct_provider_ebook_access(ed: &Value) -> Option<EbookAccess> {
    let providers = ed.get("providers")?.as_array()?;
    if providers.is_empty()
        || providers
            .first()?
            .get("url")
            .and_then(|v| v.as_str())
            .is_none()
    {
        return None;
    }
    let qualifies = providers.iter().any(|p| {
        p.get("url").and_then(|v| v.as_str()).is_some()
            && acquisition_access_literal(p)
                .map(|a| EbookAccess::from_acquisition_access(a) >= EbookAccess::Printdisabled)
                .unwrap_or(false)
    });
    if !qualifies {
        return None;
    }
    acquisition_access_literal(&providers[0]).map(EbookAccess::from_acquisition_access)
}

/// Port of InternetArchiveProvider.get_access (book_providers.py:337). Missing metadata degrades
/// to UNCLASSIFIED, same as production when IA metadata can't be fetched.
pub fn ia_ebook_access(meta: Option<&IaLite>) -> EbookAccess {
    match meta {
        None => EbookAccess::Unclassified,
        Some(m) => {
            let in_collection = |c: &str| m.collections.iter().any(|x| x == c);
            if in_collection("inlibrary") {
                EbookAccess::Borrowable
            } else if in_collection("printdisabled") {
                EbookAccess::Printdisabled
            } else if m.access_restricted_item || m.collections.is_empty() {
                EbookAccess::Unclassified
            } else {
                EbookAccess::Public
            }
        }
    }
}

pub fn edition_ocaid(ed: &Value) -> Option<&str> {
    ed.get("ocaid")
        .and_then(|v| v.as_str())
        .map(str::trim)
        .filter(|s| !s.is_empty())
}

/// Identifier-based providers, in book_providers.py PROVIDER_ORDER order (after Direct,
/// before IA). Default AbstractBookProvider.get_access == PUBLIC for all of them.
const IDENTIFIER_PROVIDERS: [&str; 7] = [
    "librivox",
    "project_gutenberg",
    "project_runeberg",
    "standard_ebooks",
    "openstax",
    "cita_press",
    "wikisource",
];

pub struct EditionAccess {
    pub access: EbookAccess,
    /// provider_name values of ALL matching providers in PROVIDER_ORDER
    /// (edition.py:130 _providers / :349 ebook_provider). BWB omitted: its match is
    /// config-gated (bwb_test_holdings) and never fires for dumps.
    pub providers: Vec<String>,
}

fn edition_access_and_providers(ed: &Value, ia_map: &HashMap<String, IaLite>) -> EditionAccess {
    let mut providers: Vec<String> = Vec::new();
    let mut access: Option<EbookAccess> = None;
    if let Some(a) = direct_provider_ebook_access(ed) {
        providers.push("direct".to_string());
        access = Some(a);
    }
    let identifiers = ed.get("identifiers").cloned().unwrap_or(Value::Null);
    let has_id = |k: &str| identifiers.get(k).map(value_truthy).unwrap_or(false);
    for p in IDENTIFIER_PROVIDERS {
        if has_id(p) {
            providers.push(p.to_string());
            if access.is_none() {
                access = Some(EbookAccess::Public);
            }
        }
    }
    if edition_ocaid(ed).is_some() {
        providers.push("ia".to_string());
        if access.is_none() {
            access = Some(ia_ebook_access(
                edition_ocaid(ed).and_then(|o| ia_map.get(o)),
            ));
        }
    }
    EditionAccess {
        access: access.unwrap_or(EbookAccess::NoEbook),
        providers,
    }
}

pub fn edition_ebook_access(ed: &Value, ia_map: &HashMap<String, IaLite>) -> EbookAccess {
    edition_access_and_providers(ed, ia_map).access
}

/// EditionSolrBuilder.ia_collection (edition.py:303): metadata collections minus fav-*.
pub fn edition_ia_collection(ed: &Value, ia_map: &HashMap<String, IaLite>) -> Vec<String> {
    match edition_ocaid(ed).and_then(|o| ia_map.get(o)) {
        None => Vec::new(),
        Some(m) => m
            .collections
            .iter()
            .filter(|c| !c.starts_with("fav-"))
            .cloned()
            .collect(),
    }
}

/// Port of EditionScorecardForSolr (edition.py:498) + weights from edition_scorecard.py
/// (auto-generated from edition_scorecard.yml). Section maxima: access 367, discovery 216,
/// evaluation 222; usefulness normalized over the 805 total. normalized = 100 * score / max.
struct EditionScores {
    usefulness: i64,
    usefulness_n: i64,
    access: i64,
    access_n: i64,
    discovery: i64,
    discovery_n: i64,
    evaluation: i64,
    evaluation_n: i64,
}

fn link_contains(work: &Value, needle: &str) -> bool {
    work.get("links")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|l| l.get("url").and_then(|u| u.as_str()))
                .any(|u| u.contains(needle))
        })
        .unwrap_or(false)
}

#[allow(clippy::too_many_arguments)]
fn edition_scores(
    ed: &Value,
    ed_access: EbookAccess,
    ed_chapter_count: usize,
    ed_isbn_nonempty: bool,
    ed_oclc_nonempty: bool,
    ed_langs_nonempty: bool,
    ed_cover_i: Option<i64>,
    ed_publish_year: Option<i64>,
    ed_pubs_nonempty: bool,
    ed_pubs_all_sine_nomine: bool,
    work: &Value,
    doc: &serde_json::Map<String, Value>,
    authors: &[Value],
) -> EditionScores {
    let desc = description_text(ed);
    let identifiers = ed.get("identifiers").cloned().unwrap_or(Value::Null);
    let id_has = |k: &str| identifiers.get(k).map(value_truthy).unwrap_or(false);
    let number_of_pages = ed.get("number_of_pages").and_then(|v| match v {
        Value::String(s) => s.parse::<i64>().ok(),
        Value::Number(_) => v.as_i64(),
        _ => None,
    });
    let work_authors_present = work.get("authors").map(value_truthy).unwrap_or(false);
    let work_series_present = work.get("series").map(value_truthy).unwrap_or(false);

    // --- Access (max 367)
    let mut access = 0;
    if ed_access >= EbookAccess::Borrowable {
        access += 200;
    } // read_access
    if ed_access >= EbookAccess::Printdisabled {
        access += 50;
    } // search_inside_access
    if ed_access == EbookAccess::Public {
        access += 25;
    } // programmatic_access
    if ed_isbn_nonempty || id_has("amazon") || id_has("better_world_books") {
        access += 25;
    } // purchase_options
    if ed_isbn_nonempty || ed_oclc_nonempty {
        access += 25;
    } // library_options
    if link_contains(work, "archiveofourown.org") {
        access += 20;
    } // fan_fiction
    if work
        .get("identifiers")
        .map(|i| i.get("wikidata").map(value_truthy).unwrap_or(false))
        .unwrap_or(false)
        || link_contains(work, "wikipedia.org")
    {
        access += 20; // wikipedia
    }
    if ed.get("first_sentence").map(value_truthy).unwrap_or(false) {
        access += 2;
    }

    // --- Discovery (max 216)
    let mut discovery = 0;
    if ed
        .get("title")
        .and_then(|v| v.as_str())
        .map(|s| !s.is_empty())
        .unwrap_or(false)
    {
        discovery += 50;
    }
    if work_authors_present {
        discovery += 40;
    } // author_name
      // genre_tags: not a thing yet (always false)
    if work_series_present {
        discovery += 20;
    } // series
    if ed_chapter_count > 0 {
        discovery += 20;
    } // table_of_contents
    if doc.contains_key("ddc_sort") || doc.contains_key("lcc_sort") {
        discovery += 15;
    } // classifications
    if ed_langs_nonempty {
        discovery += 15;
    } // language
    if ed_isbn_nonempty {
        discovery += 15;
    } // isbn
    if doc.contains_key("lexile") {
        discovery += 5;
    } // lexile
    if doc
        .get("ratings_count")
        .and_then(|v| v.as_i64())
        .unwrap_or(0)
        > 0
    {
        discovery += 5;
    } // star_ratings
    if doc
        .get("readinglog_count")
        .and_then(|v| v.as_i64())
        .unwrap_or(0)
        > 0
    {
        discovery += 3;
    } // on_readinglogs
      // on_lists: not yet available in Solr builder
    if ed.get("contributions").map(value_truthy).unwrap_or(false) {
        discovery += 1;
    } // contributor_names

    // --- Evaluation (max 222)
    let mut evaluation = 0;
    if !desc.is_empty() {
        evaluation += 40;
    } // basic_description
    if ed_cover_i.map(|c| c != 0).unwrap_or(false) {
        evaluation += 35;
    } // cover
    if ed_chapter_count > 0 {
        evaluation += 30;
    } // table_of_contents
      // genre_tags: never
    if doc
        .get("ratings_count")
        .and_then(|v| v.as_i64())
        .unwrap_or(0)
        > 0
    {
        evaluation += 20;
    } // star_ratings
    if desc.chars().count() > 50 {
        evaluation += 10;
    } // rich_description
    if doc
        .get("readinglog_count")
        .and_then(|v| v.as_i64())
        .unwrap_or(0)
        > 0
    {
        evaluation += 10;
    } // readinglog_counts
      // list_count: not yet available
    if number_of_pages.map(|n| n != 0).unwrap_or(false) {
        evaluation += 10;
    } // page_count
    if work_series_present {
        evaluation += 10;
    } // series
    let author_photo = authors.iter().any(|a| {
        a.get("photos")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter().any(|p| {
                    p.as_i64()
                        .map(|x| x != -1 && x != 0)
                        .unwrap_or(!p.is_null())
                })
            })
            .unwrap_or(false)
    });
    if author_photo {
        evaluation += 5;
    }
    if doc.get("first_publish_year").is_some() {
        evaluation += 5;
    }
    if ed_publish_year.is_some() {
        evaluation += 5;
    } // publish_year
    let author_bio = authors.iter().any(|a| {
        a.get("bio").map(value_truthy).unwrap_or(false)
            || a.get("description").map(value_truthy).unwrap_or(false)
    });
    if author_bio {
        evaluation += 3;
    }
    if ed_pubs_nonempty && !ed_pubs_all_sine_nomine {
        evaluation += 2;
    } // publisher
    let author_links = authors
        .iter()
        .any(|a| a.get("remote_ids").map(value_truthy).unwrap_or(false));
    if author_links {
        evaluation += 2;
    }

    let usefulness = access + discovery + evaluation;
    EditionScores {
        usefulness,
        usefulness_n: 100 * usefulness / 805,
        access,
        access_n: 100 * access / 367,
        discovery,
        discovery_n: 100 * discovery / 216,
        evaluation,
        evaluation_n: 100 * evaluation / 222,
    }
}

static RE_YEAR: Lazy<regex::Regex> = Lazy::new(|| regex::Regex::new(r"\b(\d{4})\b").unwrap());
static RE_LANG_KEY: Lazy<regex::Regex> =
    Lazy::new(|| regex::Regex::new(r"^/(?:l|languages)/([a-z]{3})$").unwrap());
static RE_AUTHOR_KEY: Lazy<regex::Regex> =
    Lazy::new(|| regex::Regex::new(r"^/(?:a|authors)/(OL\d+A)").unwrap());
static RE_SOLR_FIELD: Lazy<regex::Regex> = Lazy::new(|| regex::Regex::new(r"^[-\w]+$").unwrap());
static RE_DDC_SMALL: Lazy<regex::Regex> = Lazy::new(|| regex::Regex::new(r"^0?\d{1,2}$").unwrap());
static RE_SOLR_ESCAPE: Lazy<regex::Regex> =
    Lazy::new(|| regex::Regex::new(r#"([\s\-+!()|&{}\[\]^"~*?:\\])"#).unwrap());

fn get_str(v: &Value, key: &str) -> Option<String> {
    v.get(key).and_then(|x| x.as_str()).map(|s| s.to_string())
}

fn get_array_str(v: &Value, key: &str) -> Vec<String> {
    v.get(key)
        .and_then(|x| x.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|e| e.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default()
}

fn uniq_strings(vals: Vec<String>) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for v in vals {
        if seen.insert(v.clone()) {
            out.push(v);
        }
    }
    out
}

fn extract_year(publish_date: &str) -> Option<i64> {
    RE_YEAR
        .captures(publish_date)
        .and_then(|c| c.get(1))
        .and_then(|m| m.as_str().parse().ok())
}

fn solr_escape(query: &str) -> String {
    RE_SOLR_ESCAPE.replace_all(query, r"\$1").to_string()
}

/// Python truthiness for a JSON value (bool(list/dict/str/num) semantics for the cases we hit).
fn value_truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().map(|f| f != 0.0).unwrap_or(true),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

/// EditionSolrBuilder._get_description_text: string or {value: str} form.
fn description_text(ed: &Value) -> String {
    match ed.get("description") {
        Some(Value::String(s)) => s.clone(),
        Some(Value::Object(o)) => o
            .get("value")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        _ => String::new(),
    }
}

/// is_sine_nomine (edition.py:94): strip non-letters, lowercase == "sn".
fn is_sine_nomine(pub_name: &str) -> bool {
    let letters: String = pub_name.chars().filter(|c| c.is_alphabetic()).collect();
    letters.to_lowercase() == "sn"
}

/// EditionSolrBuilder._identifiers (edition.py:323): sanitized id_* fields for one edition.
fn edition_identifiers(ed: &Value) -> Vec<(String, Vec<String>)> {
    let mut out = Vec::new();
    if let Some(id_map) = ed.get("identifiers").and_then(|v| v.as_object()) {
        for (key, val) in id_map {
            let solr_key = key
                .replace('.', "_")
                .replace(',', "_")
                .replace('(', "")
                .replace(')', "")
                .replace(':', "_")
                .replace('/', "")
                .replace('#', "")
                .to_lowercase();
            if !RE_SOLR_FIELD.is_match(&solr_key) {
                continue;
            }
            if let Some(arr) = val.as_array() {
                let vals = uniq_strings(
                    arr.iter()
                        .filter_map(|v| v.as_str())
                        .filter(|s| !s.is_empty())
                        .map(|s| s.trim().to_string())
                        .collect(),
                );
                if !vals.is_empty() {
                    out.push((format!("id_{}", solr_key), vals));
                }
            }
        }
    }
    out
}

/// EditionSolrBuilder.ia_box_id (edition.py:308): edition field + IA metadata, uniq case-insensitively.
fn edition_ia_box_id(ed: &Value) -> Vec<String> {
    let mut boxids: Vec<String> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    let mut push = |b: &str| {
        if seen.insert(b.to_lowercase()) {
            boxids.push(b.to_string());
        }
    };
    match ed.get("ia_box_id") {
        Some(Value::String(s)) => push(s),
        Some(Value::Array(arr)) => {
            for item in arr {
                if let Some(s) = item.as_str() {
                    push(s);
                }
            }
        }
        _ => {}
    }
    boxids
}

// Edition builder helpers
fn edition_isbn(ed: &Value) -> Vec<String> {
    let mut isbns = Vec::new();
    for k in &["isbn_13", "isbn_10"] {
        if let Some(arr) = ed.get(*k).and_then(|v| v.as_array()) {
            for v in arr {
                if let Some(s) = v.as_str() {
                    let t = s.replace('_', "").trim().to_string();
                    if !t.is_empty() {
                        isbns.push(t);
                    }
                }
            }
        }
    }
    let mut extra = Vec::new();
    for isbn in &isbns {
        if let Some(o) = opposite_isbn(isbn) {
            extra.push(o);
        }
    }
    isbns.extend(extra);
    uniq_strings(isbns.into_iter().filter(|s| !s.is_empty()).collect())
}

fn edition_publish_year(ed: &Value) -> Option<i64> {
    ed.get("publish_date")
        .and_then(|v| v.as_str())
        .and_then(extract_year)
}

fn edition_publishers(ed: &Value) -> Vec<String> {
    let pubs = get_array_str(ed, "publishers");
    uniq_strings(
        pubs.into_iter()
            .map(|p| {
                let trimmed: String = p.chars().filter(|c| c.is_alphabetic()).collect();
                if trimmed.to_lowercase() == "sn" {
                    "Sine nomine".to_string()
                } else {
                    p
                }
            })
            .collect(),
    )
}

fn edition_languages(ed: &Value) -> Vec<String> {
    let mut out = Vec::new();
    if let Some(arr) = ed.get("languages").and_then(|v| v.as_array()) {
        for lang in arr {
            let key = if let Some(s) = lang.as_str() {
                s.to_string()
            } else if let Some(o) = lang.as_object() {
                o.get("key")
                    .and_then(|k| k.as_str())
                    .unwrap_or("")
                    .to_string()
            } else {
                String::new()
            };
            if let Some(caps) = RE_LANG_KEY.captures(&key) {
                out.push(caps.get(1).unwrap().as_str().to_string());
            }
        }
    }
    uniq_strings(out)
}

pub fn build_solr_doc(
    work: &Value,
    editions: &[Value],
    authors: &[Value],
    ia_metadata: &HashMap<String, IaLite>,
    series_docs: &HashMap<String, String>,
) -> Value {
    let key = get_str(work, "key").unwrap_or_default();
    let title = work
        .get("title")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .or_else(|| {
            // fallback to first edition title
            editions
                .iter()
                .find_map(|ed| {
                    ed.get("title")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string())
                })
                .or(Some("__None__".to_string()))
        });
    let subtitle = work
        .get("subtitle")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());
    let title_sort = title.as_ref().map(|t| sort_title(t, subtitle.as_deref()));

    // edition_count
    let edition_count = editions.len() as i64;
    let edition_key: Vec<String> = editions
        .iter()
        .filter_map(|ed| {
            ed.get("key")
                .and_then(|k| k.as_str())
                .map(|s| s.split('/').last().unwrap_or(s).to_string())
        })
        .collect();

    // author fields
    let author_key: Vec<String> = authors
        .iter()
        .filter_map(|a| {
            let k = a.get("key")?.as_str()?;
            RE_AUTHOR_KEY
                .captures(k)
                .and_then(|c| c.get(1))
                .map(|m| m.as_str().to_string())
        })
        .collect();
    let author_name: Vec<String> = authors
        .iter()
        .map(|a| {
            a.get("name")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string()
        })
        .collect();
    let author_facet: Vec<String> = author_key
        .iter()
        .zip(author_name.iter())
        .map(|(k, n)| format!("{} {}", k, n))
        .collect();
    let author_alt: HashSet<String> = authors
        .iter()
        .flat_map(|a| {
            a.get("alternate_names")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(|s| s.to_string()))
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default()
        })
        .collect();

    // publishers, publish_year, etc aggregated from editions
    let publishers: HashSet<String> = editions
        .iter()
        .flat_map(|ed| edition_publishers(ed))
        .collect();
    let publish_year: HashSet<i64> = editions
        .iter()
        .filter_map(|ed| edition_publish_year(ed))
        .collect();
    let first_publish_year = publish_year.iter().cloned().min();
    let publish_date: HashSet<String> = editions
        .iter()
        .filter_map(|ed| {
            ed.get("publish_date")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .collect();
    let language: HashSet<String> = editions
        .iter()
        .flat_map(|ed| edition_languages(ed))
        .collect();
    let lccn: HashSet<String> = editions
        .iter()
        .flat_map(|ed| {
            get_array_str(ed, "lccn")
                .into_iter()
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
        })
        .collect();
    let oclc: HashSet<String> = editions
        .iter()
        .flat_map(|ed| {
            get_array_str(ed, "oclc_numbers")
                .into_iter()
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
        })
        .collect();
    let isbn: HashSet<String> = editions.iter().flat_map(|ed| edition_isbn(ed)).collect();
    let contributor: HashSet<String> = editions
        .iter()
        .flat_map(|ed| {
            ed.get("contributions")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().filter(|s| !s.is_empty()).map(|s| s.to_string()))
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default()
        })
        .collect();
    let publish_place: HashSet<String> = editions
        .iter()
        .flat_map(|ed| get_array_str(ed, "publish_places"))
        .collect();
    let first_sentence: HashSet<String> = editions
        .iter()
        .filter_map(|ed| {
            ed.get("first_sentence")
                .map(|v| {
                    if let Some(s) = v.as_str() {
                        s.to_string()
                    } else if let Some(o) = v.as_object() {
                        o.get("value")
                            .and_then(|x| x.as_str())
                            .unwrap_or("")
                            .to_string()
                    } else {
                        String::new()
                    }
                })
                .filter(|s| !s.is_empty())
        })
        .collect();

    // lcc - preserve order via Vec uniq (like Python set insertion order)
    let raw_lccs_vec: Vec<String> = editions
        .iter()
        .flat_map(|ed| get_array_str(ed, "lc_classifications"))
        .collect();
    let raw_lccs_uniq = uniq_strings(raw_lccs_vec);
    let mut lcc_vec: Vec<String> = Vec::new();
    for l in raw_lccs_uniq {
        if let Some(s) = short_lcc_to_sortable_lcc(&l) {
            if !lcc_vec.contains(&s) {
                lcc_vec.push(s);
            }
        }
    }
    let lcc_sort = if !lcc_vec.is_empty() {
        Some(choose_sorting_lcc(&lcc_vec))
    } else {
        None
    };
    let lcc_set: HashSet<String> = lcc_vec.iter().cloned().collect();

    // ddc - preserve order
    let raw_ddcs: Vec<String> = editions
        .iter()
        .flat_map(|ed| crate::helpers::get_edition_ddcs(ed))
        .collect();
    let mut ddc_vec: Vec<String> = Vec::new();
    for raw in raw_ddcs {
        for d in normalize_ddc(&raw) {
            if !ddc_vec.contains(&d) {
                ddc_vec.push(d);
            }
        }
    }
    let ddc_sort = if !ddc_vec.is_empty() {
        Some(choose_sorting_ddc(&ddc_vec))
    } else {
        None
    };
    let ddc_set: HashSet<String> = ddc_vec.iter().cloned().collect();

    // subjects
    let mut doc = serde_json::Map::new();
    doc.insert("key".to_string(), json!(key));
    doc.insert("type".to_string(), json!("work"));
    if let Some(t) = title {
        doc.insert("title".to_string(), json!(t));
    }
    if let Some(s) = subtitle {
        doc.insert("subtitle".to_string(), json!(s));
    }
    if let Some(ts) = title_sort {
        doc.insert("title_sort".to_string(), json!(ts));
    }
    doc.insert("edition_count".to_string(), json!(edition_count));
    if !edition_key.is_empty() {
        doc.insert("edition_key".to_string(), json!(uniq_strings(edition_key)));
    }
    if !author_key.is_empty() {
        doc.insert("author_key".to_string(), json!(author_key));
    }
    if !author_name.is_empty() {
        doc.insert("author_name".to_string(), json!(author_name));
    }
    if !author_facet.is_empty() {
        doc.insert("author_facet".to_string(), json!(author_facet));
    }
    if !author_alt.is_empty() {
        doc.insert(
            "author_alternative_name".to_string(),
            json!(author_alt.into_iter().collect::<Vec<_>>()),
        );
    }

    // alternative_title etc: use edition alternative_title logic minimal
    let mut alt_titles = HashSet::new();
    for ed in editions {
        if let Some(t) = ed.get("title").and_then(|v| v.as_str()) {
            let mut full = t.to_string();
            if let Some(sub) = ed.get("subtitle").and_then(|v| v.as_str()) {
                full = format!("{}: {}", full, sub);
            }
            alt_titles.insert(full);
        }
        for wt in get_array_str(ed, "work_titles") {
            alt_titles.insert(wt);
        }
        for ot in get_array_str(ed, "other_titles") {
            alt_titles.insert(ot);
        }
        if let Some(tr) = ed.get("translation_of").and_then(|v| v.as_str()) {
            alt_titles.insert(tr.to_string());
        }
    }
    // also from work as solr_edition
    if let Some(t) = work.get("title").and_then(|v| v.as_str()) {
        let mut full = t.to_string();
        if let Some(sub) = work.get("subtitle").and_then(|v| v.as_str()) {
            full = format!("{}: {}", full, sub);
        }
        alt_titles.insert(full);
    }
    if !alt_titles.is_empty() {
        doc.insert(
            "alternative_title".to_string(),
            json!(alt_titles.into_iter().collect::<Vec<_>>()),
        );
    }

    let alt_sub: HashSet<String> = editions
        .iter()
        .filter_map(|ed| {
            ed.get("subtitle")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .collect();
    if !alt_sub.is_empty() {
        doc.insert(
            "alternative_subtitle".to_string(),
            json!(alt_sub.into_iter().collect::<Vec<_>>()),
        );
    }

    if !publishers.is_empty() {
        doc.insert(
            "publisher".to_string(),
            json!(publishers.into_iter().collect::<Vec<_>>()),
        );
    }
    if !publish_date.is_empty() {
        doc.insert(
            "publish_date".to_string(),
            json!(publish_date.into_iter().collect::<Vec<_>>()),
        );
    }
    if !publish_year.is_empty() {
        doc.insert(
            "publish_year".to_string(),
            json!(publish_year.into_iter().collect::<Vec<_>>()),
        );
    }
    if let Some(y) = first_publish_year {
        doc.insert("first_publish_year".to_string(), json!(y));
    }
    if !language.is_empty() {
        doc.insert(
            "language".to_string(),
            json!(language.into_iter().collect::<Vec<_>>()),
        );
    }
    if !lccn.is_empty() {
        doc.insert(
            "lccn".to_string(),
            json!(lccn.into_iter().collect::<Vec<_>>()),
        );
    }
    if !oclc.is_empty() {
        doc.insert(
            "oclc".to_string(),
            json!(oclc.into_iter().collect::<Vec<_>>()),
        );
    }
    if !isbn.is_empty() {
        doc.insert(
            "isbn".to_string(),
            json!(isbn.into_iter().collect::<Vec<_>>()),
        );
    }
    if !contributor.is_empty() {
        doc.insert(
            "contributor".to_string(),
            json!(contributor.into_iter().collect::<Vec<_>>()),
        );
    }
    if !publish_place.is_empty() {
        doc.insert(
            "publish_place".to_string(),
            json!(publish_place.into_iter().collect::<Vec<_>>()),
        );
    }
    if !first_sentence.is_empty() {
        doc.insert(
            "first_sentence".to_string(),
            json!(first_sentence.into_iter().collect::<Vec<_>>()),
        );
    }
    if !lcc_set.is_empty() {
        doc.insert(
            "lcc".to_string(),
            json!(lcc_set.into_iter().collect::<Vec<_>>()),
        );
    }
    if let Some(s) = lcc_sort {
        doc.insert("lcc_sort".to_string(), json!(s));
    }
    if !ddc_set.is_empty() {
        doc.insert(
            "ddc".to_string(),
            json!(ddc_set.into_iter().collect::<Vec<_>>()),
        );
    }
    if let Some(s) = ddc_sort {
        doc.insert("ddc_sort".to_string(), json!(s));
    }

    // seed
    let mut seed_vals: Vec<String> = Vec::new();
    for ed in editions {
        if let Some(k) = ed.get("key").and_then(|v| v.as_str()) {
            seed_vals.push(k.to_string());
        }
    }
    seed_vals.push(key.clone());
    for a in authors {
        if let Some(k) = a.get("key").and_then(|v| v.as_str()) {
            seed_vals.push(k.to_string());
        }
    }
    for s in work
        .get("subjects")
        .and_then(|v| v.as_array())
        .unwrap_or(&vec![])
    {
        if let Some(name) = s.as_str() {
            seed_vals.push(crate::helpers::subject_name_to_key("subject", name));
        }
    }
    for s in work
        .get("subject_people")
        .and_then(|v| v.as_array())
        .unwrap_or(&vec![])
    {
        if let Some(name) = s.as_str() {
            seed_vals.push(crate::helpers::subject_name_to_key("person", name));
        }
    }
    for s in work
        .get("subject_places")
        .and_then(|v| v.as_array())
        .unwrap_or(&vec![])
    {
        if let Some(name) = s.as_str() {
            seed_vals.push(crate::helpers::subject_name_to_key("place", name));
        }
    }
    for s in work
        .get("subject_times")
        .and_then(|v| v.as_array())
        .unwrap_or(&vec![])
    {
        if let Some(name) = s.as_str() {
            seed_vals.push(crate::helpers::subject_name_to_key("time", name));
        }
    }
    let seed_uniq = uniq_strings(seed_vals);
    if !seed_uniq.is_empty() {
        doc.insert("seed".to_string(), json!(seed_uniq));
    }
    // series (minimal, without fetching series docs, fallback to key)
    {
        let mut series_keys = Vec::new();
        let mut series_names = Vec::new();
        let mut series_positions = Vec::new();
        // collect from work and editions (work.py:105 uniq by series key)
        let mut seen_series = HashSet::new();
        let mut all_series_edges: Vec<Value> = Vec::new();
        if let Some(arr) = work.get("series").and_then(|v| v.as_array()) {
            for s in arr {
                if s.is_object() {
                    all_series_edges.push(s.clone());
                }
            }
        }
        for ed in editions {
            if let Some(arr) = ed.get("series").and_then(|v| v.as_array()) {
                for s in arr {
                    // edition series may be string or dict; only dict with series key
                    if let Some(obj) = s.as_object() {
                        if obj.contains_key("series") {
                            all_series_edges.push(s.clone());
                        }
                    }
                }
            }
        }
        // uniq by series key
        let mut uniq_edges = Vec::new();
        for edge in all_series_edges {
            if let Some(key) = edge
                .get("series")
                .and_then(|v| v.get("key"))
                .and_then(|k| k.as_str())
            {
                if seen_series.insert(key.to_string()) {
                    uniq_edges.push(edge);
                }
            }
        }
        for edge in uniq_edges {
            if let Some(series_key) = edge
                .get("series")
                .and_then(|v| v.get("key"))
                .and_then(|k| k.as_str())
            {
                let olid = series_key
                    .split('/')
                    .last()
                    .unwrap_or(series_key)
                    .to_string();
                series_keys.push(olid);
                // WorkSolrBuilder.series_name (work.py:397): name from the FETCHED series doc,
                // falling back to the edge's key path (the embedded reference is replaced by the
                // fetched doc before this runs, so its own "name" — if any — is ignored).
                let name = series_docs
                    .get(series_key)
                    .cloned()
                    .unwrap_or_else(|| series_key.to_string());
                series_names.push(name);
                let pos = edge
                    .get("position")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                series_positions.push(pos);
            }
        }
        if !series_keys.is_empty() {
            doc.insert("series_key".to_string(), json!(series_keys));
            doc.insert("series_name".to_string(), json!(series_names));
            doc.insert("series_position".to_string(), json!(series_positions));
        }
    }

    // subjects
    let field_map = [
        ("subjects", "subject"),
        ("subject_places", "place"),
        ("subject_times", "time"),
        ("subject_people", "person"),
    ];
    for (work_field, subject_type) in field_map {
        if let Some(arr) = work.get(work_field).and_then(|v| v.as_array()) {
            if arr.is_empty() {
                continue;
            }
            let vals: Vec<String> = arr
                .iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect();
            if vals.is_empty() {
                continue;
            }
            doc.insert(subject_type.to_string(), json!(vals.clone()));
            doc.insert(format!("{}_facet", subject_type), json!(vals.clone()));
            let keys: Vec<String> = vals
                .iter()
                .map(|s| crate::helpers::normalize_subject_name(s))
                .collect();
            doc.insert(format!("{}_key", subject_type), json!(keys));
        }
    }

    // last_modified_i
    let mut all_docs = vec![work.clone()];
    all_docs.extend(editions.iter().cloned());
    let last_modified_i = all_docs
        .iter()
        .map(|d| crate::helpers::datetimestr_to_int(d.get("last_modified")))
        .max()
        .unwrap_or(0);
    doc.insert("last_modified_i".to_string(), json!(last_modified_i));

    // ebook fields: real access when IA metadata is available, else every ocaid degrades to UNCLASSIFIED
    let edition_accesses: Vec<EbookAccess> = editions
        .iter()
        .map(|ed| edition_ebook_access(ed, ia_metadata))
        .collect();
    let work_ebook_access = edition_accesses
        .iter()
        .cloned()
        .max()
        .unwrap_or(EbookAccess::NoEbook);
    let has_fulltext = work_ebook_access > EbookAccess::Unclassified;
    let public_scan_b = work_ebook_access == EbookAccess::Public;
    let ebook_count_i = edition_accesses
        .iter()
        .filter(|&&a| a > EbookAccess::NoEbook)
        .count() as i64;
    doc.insert("has_fulltext".to_string(), json!(has_fulltext));
    doc.insert("public_scan_b".to_string(), json!(public_scan_b));
    doc.insert("ebook_count_i".to_string(), json!(ebook_count_i));
    doc.insert(
        "ebook_access".to_string(),
        json!(work_ebook_access.to_solr_str()),
    );
    // ia and ebook_provider derived from ocaid
    struct IaEdition {
        access: EbookAccess,
        ocaid: String,
        edition_key: String,
        printdisabled: bool,
    }
    let mut ia_list: Vec<IaEdition> = Vec::new();
    for ed in editions {
        if let Some(ocaid) = edition_ocaid(ed) {
            let access = edition_ebook_access(ed, ia_metadata);
            let edition_key = ed
                .get("key")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let printdisabled = edition_ia_collection(ed, ia_metadata)
                .iter()
                .any(|c| c == "printdisabled");
            ia_list.push(IaEdition {
                access,
                ocaid: ocaid.to_string(),
                edition_key,
                printdisabled,
            });
        }
    }
    // sort by (-access, is_goog) — WorkSolrBuilder._ia_editions
    ia_list.sort_by(|a, b| {
        let ord = b.access.cmp(&a.access);
        if ord != std::cmp::Ordering::Equal {
            return ord;
        }
        let a_goog = a.ocaid.ends_with("goog") as i32;
        let b_goog = b.ocaid.ends_with("goog") as i32;
        a_goog.cmp(&b_goog)
    });
    // Deprecated legacy IA fields (work.py:556-577), ported for parity
    if !ia_list.is_empty() && ia_list[0].access > EbookAccess::Printdisabled {
        doc.insert(
            "lending_edition_s".to_string(),
            json!(ia_list[0].edition_key.rsplit('/').next().unwrap_or("")),
        );
        doc.insert("lending_identifier_s".to_string(), json!(ia_list[0].ocaid));
    }
    {
        let pds: Vec<&str> = ia_list
            .iter()
            .filter(|e| e.printdisabled)
            .map(|e| e.edition_key.rsplit('/').next().unwrap_or(""))
            .collect();
        if !pds.is_empty() {
            doc.insert("printdisabled_s".to_string(), json!(pds.join(";")));
        }
    }
    if !ia_list.is_empty() {
        let ia_vals: Vec<String> = ia_list.iter().map(|e| e.ocaid.clone()).collect();
        doc.insert("ia".to_string(), json!(ia_vals));
    }
    // WorkSolrBuilder.ebook_provider (work.py:525): uniq provider names across editions,
    // in edition order.
    {
        let mut ebook_provider: Vec<String> = Vec::new();
        let mut seen_providers = HashSet::new();
        for ed in editions {
            for p in edition_access_and_providers(ed, ia_metadata).providers {
                if seen_providers.insert(p.clone()) {
                    ebook_provider.push(p);
                }
            }
        }
        if !ebook_provider.is_empty() {
            doc.insert("ebook_provider".to_string(), json!(ebook_provider));
        }
    }
    // WorkSolrBuilder.ia_collection (work.py:541): sorted uniq across editions
    {
        let ia_coll: std::collections::BTreeSet<String> = editions
            .iter()
            .flat_map(|ed| edition_ia_collection(ed, ia_metadata))
            .collect();
        if !ia_coll.is_empty() {
            doc.insert(
                "ia_collection".to_string(),
                json!(ia_coll.into_iter().collect::<Vec<_>>()),
            );
        }
    }
    // cover_i etc: try work covers then editions
    let cover_i = work
        .get("covers")
        .and_then(|v| v.as_array())
        .and_then(|arr| arr.iter().find_map(|v| v.as_i64().filter(|&x| x != -1)))
        .or_else(|| {
            editions.iter().find_map(|ed| {
                ed.get("covers")
                    .and_then(|v| v.as_array())
                    .and_then(|arr| arr.iter().find_map(|v| v.as_i64().filter(|&x| x != -1)))
            })
        });
    if let Some(c) = cover_i {
        doc.insert("cover_i".to_string(), json!(c));
    }
    // cover_edition_key
    if let Some(c) = cover_i {
        let cek = editions
            .iter()
            .find(|ed| {
                ed.get("covers")
                    .and_then(|v| v.as_array())
                    .map(|arr| arr.iter().any(|v| v.as_i64() == Some(c)))
                    .unwrap_or(false)
            })
            .and_then(|ed| {
                ed.get("key")
                    .and_then(|k| k.as_str())
                    .map(|s| s.split('/').last().unwrap_or(s).to_string())
            });
        if let Some(k) = cek {
            doc.insert("cover_edition_key".to_string(), json!(k));
        }
    }
    // by_statement
    let by_statement: HashSet<String> = editions
        .iter()
        .filter_map(|ed| {
            ed.get("by_statement")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .collect();
    if !by_statement.is_empty() {
        doc.insert(
            "by_statement".to_string(),
            json!(by_statement.into_iter().collect::<Vec<_>>()),
        );
    }
    // number_of_pages_median
    let pages: Vec<i64> = editions
        .iter()
        .filter_map(|ed| {
            ed.get("number_of_pages").and_then(|v| {
                if let Some(s) = v.as_str() {
                    s.parse::<i64>().ok()
                } else if let Some(n) = v.as_i64() {
                    Some(n)
                } else {
                    None
                }
            })
        })
        .collect();
    if !pages.is_empty() {
        let mut sorted = pages.clone();
        sorted.sort_unstable();
        let median = if sorted.len() % 2 == 1 {
            sorted[sorted.len() / 2] as f64
        } else {
            (sorted[sorted.len() / 2 - 1] as f64 + sorted[sorted.len() / 2] as f64) / 2.0
        };
        let median_ceil = median.ceil() as i64;
        doc.insert("number_of_pages_median".to_string(), json!(median_ceil));
    }
    // format (physical_format)
    let formats: HashSet<String> = editions
        .iter()
        .filter_map(|ed| {
            ed.get("physical_format")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .collect();
    if !formats.is_empty() {
        doc.insert(
            "format".to_string(),
            json!(formats.into_iter().collect::<Vec<_>>()),
        );
    }
    // identifiers aggregated from editions (Python extends across editions without cross-edition dedup)
    {
        let mut identifiers: HashMap<String, Vec<String>> = HashMap::new();
        for ed in editions {
            for (k, vals) in edition_identifiers(ed) {
                identifiers.entry(k).or_default().extend(vals);
            }
        }
        for (k, v) in identifiers {
            doc.insert(k, json!(v));
        }
    }
    // lexile
    {
        let mut lex_set = HashSet::new();
        for ed in editions {
            if let Some(lex_str) = ed.get("lexile").and_then(|v| v.as_str()) {
                if let Ok(n) = lex_str.parse::<i64>() {
                    lex_set.insert(n);
                }
            } else if let Some(n) = ed.get("lexile").and_then(|v| v.as_i64()) {
                lex_set.insert(n);
            }
        }
        if !lex_set.is_empty() {
            doc.insert(
                "lexile".to_string(),
                json!(lex_set.into_iter().collect::<Vec<_>>()),
            );
        }
    }
    // ia_box_id (legacy)
    {
        let mut box_ids = HashSet::new();
        for ed in editions {
            if let Some(v) = ed.get("ia_box_id") {
                if let Some(s) = v.as_str() {
                    box_ids.insert(s.to_string());
                } else if let Some(arr) = v.as_array() {
                    for item in arr {
                        if let Some(s) = item.as_str() {
                            box_ids.insert(s.to_string());
                        }
                    }
                }
            }
        }
        if !box_ids.is_empty() {
            doc.insert(
                "ia_box_id".to_string(),
                json!(box_ids.into_iter().collect::<Vec<_>>()),
            );
        }
    }
    // chapter from editions table_of_contents
    let mut chapter_set = HashSet::new();
    for ed in editions {
        let olid = ed
            .get("key")
            .and_then(|v| v.as_str())
            .map(|s| s.split('/').last().unwrap_or(s).to_string())
            .unwrap_or_default();
        if let Some(arr) = ed.get("table_of_contents").and_then(|v| v.as_array()) {
            for ch in arr {
                if let Some(s) = ch.as_str() {
                    chapter_set.insert(format!("{} | {}", olid, s));
                } else if let Some(obj) = ch.as_object() {
                    let label = obj.get("label").and_then(|v| v.as_str()).unwrap_or("");
                    let mut title = obj
                        .get("title")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    if let Some(sub) = obj.get("subtitle").and_then(|v| v.as_str()) {
                        if !sub.is_empty() {
                            title = format!("{}: {}", title, sub);
                        }
                    }
                    if let Some(authors) = obj.get("authors").and_then(|v| v.as_array()) {
                        let names: Vec<String> = authors
                            .iter()
                            .filter_map(|a| {
                                a.get("name")
                                    .and_then(|v| v.as_str())
                                    .map(|s| s.to_string())
                            })
                            .collect();
                        if !names.is_empty() {
                            title = format!("{} ({})", title, names.join(", "));
                        }
                    }
                    let pagenum = obj.get("pagenum").and_then(|v| v.as_str()).unwrap_or("");
                    chapter_set.insert(format!("{} | {} | {} | {}", olid, label, title, pagenum));
                }
            }
        }
    }
    if !chapter_set.is_empty() {
        doc.insert(
            "chapter".to_string(),
            json!(chapter_set.into_iter().collect::<Vec<_>>()),
        );
    }
    // editions nested (simplified) - include minimal fields to match py full diff; skip usefulness scores for now but provide core
    if !editions.is_empty() {
        let mut edition_docs = Vec::new();
        for ed in editions {
            let mut ed_doc = serde_json::Map::new();
            if let Some(k) = ed.get("key").and_then(|v| v.as_str()) {
                ed_doc.insert("key".to_string(), json!(k));
            }
            let work_keys_for_ed: Vec<String> = ed
                .get("works")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|w| {
                            w.get("key")
                                .and_then(|k| k.as_str())
                                .map(|s| s.split('/').last().unwrap_or(s).to_string())
                        })
                        .collect()
                })
                .unwrap_or_default();
            if !work_keys_for_ed.is_empty() {
                ed_doc.insert("work_key".to_string(), json!(work_keys_for_ed));
            }
            ed_doc.insert("type".to_string(), json!("edition"));
            if let Some(t) = ed.get("title").and_then(|v| v.as_str()) {
                ed_doc.insert("title".to_string(), json!(t));
            }
            if let Some(s) = ed.get("subtitle").and_then(|v| v.as_str()) {
                ed_doc.insert("subtitle".to_string(), json!(s));
            }
            // alternative_title from edition
            let mut alt = HashSet::new();
            if let Some(t) = ed.get("title").and_then(|v| v.as_str()) {
                let mut full = t.to_string();
                if let Some(sub) = ed.get("subtitle").and_then(|v| v.as_str()) {
                    full = format!("{}: {}", full, sub);
                }
                alt.insert(full);
            }
            for wt in get_array_str(ed, "work_titles") {
                alt.insert(wt);
            }
            for ot in get_array_str(ed, "other_titles") {
                alt.insert(ot);
            }
            if !alt.is_empty() {
                ed_doc.insert(
                    "alternative_title".to_string(),
                    json!(alt.into_iter().collect::<Vec<_>>()),
                );
            }
            // chapter for edition
            let olid_ed = ed
                .get("key")
                .and_then(|v| v.as_str())
                .map(|s| s.split('/').last().unwrap_or(s).to_string())
                .unwrap_or_default();
            let mut chap = Vec::new();
            if let Some(arr) = ed.get("table_of_contents").and_then(|v| v.as_array()) {
                for ch in arr {
                    if let Some(s) = ch.as_str() {
                        chap.push(format!("{} | {}", olid_ed, s));
                    } else if let Some(obj) = ch.as_object() {
                        let label = obj.get("label").and_then(|v| v.as_str()).unwrap_or("");
                        let mut title = obj
                            .get("title")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        if let Some(sub) = obj.get("subtitle").and_then(|v| v.as_str()) {
                            if !sub.is_empty() {
                                title = format!("{}: {}", title, sub);
                            }
                        }
                        if let Some(authors) = obj.get("authors").and_then(|v| v.as_array()) {
                            let names: Vec<String> = authors
                                .iter()
                                .filter_map(|a| {
                                    a.get("name")
                                        .and_then(|v| v.as_str())
                                        .map(|s| s.to_string())
                                })
                                .collect();
                            if !names.is_empty() {
                                title = format!("{} ({})", title, names.join(", "));
                            }
                        }
                        let pagenum = obj.get("pagenum").and_then(|v| v.as_str()).unwrap_or("");
                        chap.push(format!("{} | {} | {} | {}", olid_ed, label, title, pagenum));
                    }
                }
            }
            if !chap.is_empty() {
                ed_doc.insert("chapter".to_string(), json!(chap));
            }
            if let Some(c) = ed
                .get("covers")
                .and_then(|v| v.as_array())
                .and_then(|arr| arr.iter().find_map(|v| v.as_i64().filter(|&x| x != -1)))
            {
                ed_doc.insert("cover_i".to_string(), json!(c));
            }
            let ed_cover_i = ed
                .get("covers")
                .and_then(|v| v.as_array())
                .and_then(|arr| arr.iter().find_map(|v| v.as_i64().filter(|&x| x != -1)));
            let langs = edition_languages(ed);
            if !langs.is_empty() {
                ed_doc.insert("language".to_string(), json!(langs));
            }
            // author fields duplicated from work
            if let Some(v) = doc.get("author_name") {
                ed_doc.insert("author_name".to_string(), v.clone());
            }
            if let Some(v) = doc.get("author_key") {
                ed_doc.insert("author_key".to_string(), v.clone());
            }
            if let Some(v) = doc.get("author_facet") {
                ed_doc.insert("author_facet".to_string(), v.clone());
            }
            if let Some(v) = doc.get("author_alternative_name") {
                ed_doc.insert("author_alternative_name".to_string(), v.clone());
            }
            if let Some(n) = ed.get("edition_name").and_then(|v| v.as_str()) {
                ed_doc.insert("edition_name".to_string(), json!([n]));
            }
            let pubs = edition_publishers(ed);
            let pubs_nonempty = !pubs.is_empty();
            let pubs_all_sn = pubs.iter().all(|p| is_sine_nomine(p));
            if !pubs.is_empty() {
                ed_doc.insert("publisher".to_string(), json!(pubs));
            }
            if let Some(fmt) = ed.get("physical_format").and_then(|v| v.as_str()) {
                ed_doc.insert("format".to_string(), json!([fmt]));
            }
            if let Some(pd) = ed.get("publish_date").and_then(|v| v.as_str()) {
                ed_doc.insert("publish_date".to_string(), json!([pd]));
            }
            if let Some(py) = edition_publish_year(ed) {
                ed_doc.insert("publish_year".to_string(), json!([py]));
            }
            // isbn
            let isbns = edition_isbn(ed);
            if !isbns.is_empty() {
                ed_doc.insert("isbn".to_string(), json!(isbns));
            }
            let lccns = get_array_str(ed, "lccn")
                .into_iter()
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect::<Vec<_>>();
            if !lccns.is_empty() {
                ed_doc.insert("lccn".to_string(), json!(lccns));
            }
            let oclcs = get_array_str(ed, "oclc_numbers")
                .into_iter()
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect::<Vec<_>>();
            if !oclcs.is_empty() {
                ed_doc.insert("oclc".to_string(), json!(oclcs));
            }
            // ia
            if let Some(ocaid) = edition_ocaid(ed) {
                ed_doc.insert("ia".to_string(), json!([ocaid]));
            }
            let ed_access = edition_ebook_access(ed, ia_metadata);
            ed_doc.insert("ebook_access".to_string(), json!(ed_access.to_solr_str()));
            let ed_ia_coll = edition_ia_collection(ed, ia_metadata);
            if !ed_ia_coll.is_empty() {
                ed_doc.insert("ia_collection".to_string(), json!(ed_ia_coll));
            }
            // EditionSolrBuilder.ebook_provider (edition.py:349): all matching provider names
            let ed_providers = edition_access_and_providers(ed, ia_metadata).providers;
            if !ed_providers.is_empty() {
                ed_doc.insert("ebook_provider".to_string(), json!(ed_providers));
            }
            ed_doc.insert(
                "has_fulltext".to_string(),
                json!(ed_access > EbookAccess::Unclassified),
            );
            ed_doc.insert(
                "public_scan_b".to_string(),
                json!(ed_access == EbookAccess::Public),
            );
            // per-edition identifiers (EditionSolrBuilder._identifiers)
            for (k, vals) in edition_identifiers(ed) {
                ed_doc.insert(k, json!(vals));
            }
            // ia_box_id from the edition record itself
            let box_ids = edition_ia_box_id(ed);
            if !box_ids.is_empty() {
                ed_doc.insert("ia_box_id".to_string(), json!(box_ids));
            }
            // usefulness scorecard (EditionScorecardForSolr)
            let scores = edition_scores(
                ed,
                ed_access,
                chap.len(),
                !isbns.is_empty(),
                !oclcs.is_empty(),
                !langs.is_empty(),
                ed_cover_i,
                edition_publish_year(ed),
                pubs_nonempty,
                pubs_all_sn,
                work,
                &doc,
                authors,
            );
            ed_doc.insert("usefulness_score".to_string(), json!(scores.usefulness));
            ed_doc.insert(
                "usefulness_score_normalized".to_string(),
                json!(scores.usefulness_n),
            );
            ed_doc.insert("access_score".to_string(), json!(scores.access));
            ed_doc.insert(
                "access_score_normalized".to_string(),
                json!(scores.access_n),
            );
            ed_doc.insert("discovery_score".to_string(), json!(scores.discovery));
            ed_doc.insert(
                "discovery_score_normalized".to_string(),
                json!(scores.discovery_n),
            );
            ed_doc.insert("evaluation_score".to_string(), json!(scores.evaluation));
            ed_doc.insert(
                "evaluation_score_normalized".to_string(),
                json!(scores.evaluation_n),
            );
            edition_docs.push(Value::Object(ed_doc));
        }
        doc.insert("editions".to_string(), json!(edition_docs));
    }

    // text field minimal: title + subjects?
    // We'll leave out text for parity (Python builds via additional code not covered here). Skip.

    // Remove empty? Already skipped.

    Value::Object(doc)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn ia(collections: &[&str], ari: bool) -> IaLite {
        IaLite {
            collections: collections.iter().map(|s| s.to_string()).collect(),
            access_restricted_item: ari,
        }
    }

    fn empty_map() -> HashMap<String, IaLite> {
        HashMap::new()
    }

    #[test]
    fn ia_access_matches_python_get_access() {
        assert_eq!(
            ia_ebook_access(Some(&ia(&["inlibrary"], false))),
            EbookAccess::Borrowable
        );
        assert_eq!(
            ia_ebook_access(Some(&ia(&["printdisabled"], false))),
            EbookAccess::Printdisabled
        );
        assert_eq!(
            ia_ebook_access(Some(&ia(&["inlibrary", "printdisabled"], false))),
            EbookAccess::Borrowable
        );
        assert_eq!(
            ia_ebook_access(Some(&ia(&["opensource"], false))),
            EbookAccess::Public
        );
        assert_eq!(
            ia_ebook_access(Some(&ia(&[], false))),
            EbookAccess::Unclassified
        );
        assert_eq!(
            ia_ebook_access(Some(&ia(&["opensource"], true))),
            EbookAccess::Unclassified
        );
        assert_eq!(ia_ebook_access(None), EbookAccess::Unclassified);
    }

    #[test]
    fn from_acquisition_access_matches_python() {
        assert_eq!(
            EbookAccess::from_acquisition_access("open-access"),
            EbookAccess::Public
        );
        assert_eq!(
            EbookAccess::from_acquisition_access("borrow"),
            EbookAccess::Borrowable
        );
        assert_eq!(
            EbookAccess::from_acquisition_access("sample"),
            EbookAccess::Printdisabled
        );
        assert_eq!(
            EbookAccess::from_acquisition_access("buy"),
            EbookAccess::NoEbook
        );
        assert_eq!(
            EbookAccess::from_acquisition_access("subscribe"),
            EbookAccess::NoEbook
        );
    }

    #[test]
    fn edition_access_uses_direct_provider_over_ia() {
        let mut map = empty_map();
        map.insert("public_ocaid".to_string(), ia(&["opensource"], false));
        // providers field qualifies -> DirectProvider wins over IA (which would say Public)
        let ed = json!({
            "ocaid": "public_ocaid",
            "providers": [{"url": "https://standardebooks.org/ebooks/x", "access": "borrow"}]
        });
        assert_eq!(edition_ebook_access(&ed, &map), EbookAccess::Borrowable);

        // providers with only "buy" don't qualify -> falls through to IA metadata
        let ed_buy = json!({
            "ocaid": "public_ocaid",
            "providers": [{"url": "https://example.com/buy", "access": "buy"}]
        });
        assert_eq!(edition_ebook_access(&ed_buy, &map), EbookAccess::Public);
    }

    #[test]
    fn edition_access_fallbacks() {
        // ocaid missing from the map -> UNCLASSIFIED (prod behavior when metadata unavailable)
        let ed = json!({"ocaid": "unknown"});
        assert_eq!(
            edition_ebook_access(&ed, &empty_map()),
            EbookAccess::Unclassified
        );

        // no ocaid, no providers -> NO_EBOOK
        let ed_none = json!({"key": "/books/OL1M"});
        assert_eq!(
            edition_ebook_access(&ed_none, &empty_map()),
            EbookAccess::NoEbook
        );
    }

    #[test]
    fn work_doc_aggregates_availability() {
        let mut map = empty_map();
        map.insert("pub1".to_string(), ia(&["opensource"], false));
        map.insert("lib1".to_string(), ia(&["inlibrary"], false));
        let work = json!({"key": "/works/OL1W", "title": "T"});
        let editions = vec![
            json!({"key": "/books/OL1M", "ocaid": "lib1"}),
            json!({"key": "/books/OL2M", "ocaid": "pub1", "covers": [5]}),
            json!({"key": "/books/OL3M"}),
        ];
        let doc = build_solr_doc(&work, &editions, &[], &map, &HashMap::new());
        assert_eq!(doc["ebook_access"], json!("public"));
        assert_eq!(doc["has_fulltext"], json!(true));
        assert_eq!(doc["public_scan_b"], json!(true));
        assert_eq!(doc["ebook_count_i"], json!(2));
        // public first in ia list; ia_collection is the union across editions, fav-* filtered
        assert_eq!(doc["ia"], json!(["pub1", "lib1"]));
        assert_eq!(doc["ia_collection"], json!(["inlibrary", "opensource"]));

        // nested edition docs get their own real access
        let eds = doc["editions"].as_array().unwrap();
        assert_eq!(eds[0]["ebook_access"], json!("borrowable"));
        assert_eq!(eds[0]["has_fulltext"], json!(true));
        assert_eq!(eds[0]["public_scan_b"], json!(false));
        assert_eq!(eds[1]["ebook_access"], json!("public"));
        assert_eq!(eds[2]["ebook_access"], json!("no_ebook"));
        assert_eq!(eds[2]["has_fulltext"], json!(false));
    }

    #[test]
    fn identifier_provider_chain_matches_prod_order() {
        let empty = empty_map();

        // gutenberg id alone -> PUBLIC via identifier provider
        let ed = json!({"key": "/books/OL1M", "identifiers": {"project_gutenberg": ["123"]}});
        assert_eq!(edition_ebook_access(&ed, &empty), EbookAccess::Public);
        assert_eq!(
            edition_access_and_providers(&ed, &empty).providers,
            vec!["project_gutenberg"]
        );

        // gutenberg beats IA even when ocaid present (PROVIDER_ORDER), both listed
        let mut map = empty_map();
        map.insert("pub1".to_string(), ia(&["opensource"], false));
        let ed_both = json!({
            "key": "/books/OL2M",
            "ocaid": "pub1",
            "identifiers": {"project_gutenberg": ["123"]}
        });
        assert_eq!(edition_ebook_access(&ed_both, &map), EbookAccess::Public);
        assert_eq!(
            edition_access_and_providers(&ed_both, &map).providers,
            vec!["project_gutenberg", "ia"]
        );

        // direct provider still wins over everything
        let ed_direct = json!({
            "key": "/books/OL3M",
            "identifiers": {"project_gutenberg": ["123"], "librivox": ["lv"]},
            "providers": [{"url": "https://x", "access": "borrow"}]
        });
        let ea = edition_access_and_providers(&ed_direct, &empty);
        assert_eq!(ea.access, EbookAccess::Borrowable);
        assert_eq!(
            ea.providers,
            vec!["direct", "librivox", "project_gutenberg"]
        );

        // nothing matches -> NO_EBOOK with no providers
        let bare = json!({"key": "/books/OL4M"});
        let ea_bare = edition_access_and_providers(&bare, &empty);
        assert_eq!(ea_bare.access, EbookAccess::NoEbook);
        assert!(ea_bare.providers.is_empty());
    }

    #[test]
    fn work_doc_ebook_provider_uniqs_across_editions() {
        let work = json!({"key": "/works/OL1W", "title": "T"});
        let editions = vec![
            json!({"key": "/books/OL1M", "identifiers": {"project_gutenberg": ["1"], "librivox": ["a"]}}),
            json!({"key": "/books/OL2M", "identifiers": {"librivox": ["b"]}, "ocaid": "x"}),
        ];
        let doc = build_solr_doc(&work, &editions, &[], &HashMap::new(), &HashMap::new());
        // uniq across editions in first-seen order
        assert_eq!(
            doc["ebook_provider"],
            json!(["librivox", "project_gutenberg", "ia"])
        );
    }

    #[test]
    fn series_name_resolves_from_fetched_doc() {
        let mut series_docs = HashMap::new();
        series_docs.insert(
            "/series/OL9L".to_string(),
            "Fetched Series Name".to_string(),
        );
        let work = json!({
            "key": "/works/OL1W",
            "title": "T",
            "series": [{"series": {"key": "/series/OL9L"}, "position": "2"},
                       {"series": {"key": "/series/OL404L"}}]
        });
        let doc = build_solr_doc(&work, &Vec::new(), &[], &HashMap::new(), &series_docs);
        assert_eq!(doc["series_key"], json!(["OL9L", "OL404L"]));
        // fetched name wins over anything embedded; missing doc falls back to key path
        assert_eq!(
            doc["series_name"],
            json!(["Fetched Series Name", "/series/OL404L"])
        );
        assert_eq!(doc["series_position"], json!(["2", ""]));
    }

    #[test]
    fn work_doc_without_metadata_stays_unclassified() {
        let work = json!({"key": "/works/OL1W", "title": "T"});
        let editions = vec![json!({"key": "/books/OL1M", "ocaid": "x"})];
        let doc = build_solr_doc(&work, &editions, &[], &empty_map(), &HashMap::new());
        assert_eq!(doc["ebook_access"], json!("unclassified"));
        assert_eq!(doc["has_fulltext"], json!(false));
        assert_eq!(doc["public_scan_b"], json!(false));
        // no ia_collection emitted when no metadata at all
        assert!(doc.get("ia_collection").is_none());
    }
}

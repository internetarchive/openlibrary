pub mod ddc;
pub mod isbn;
pub mod lcc;
pub mod sort_title;

pub fn uniq<T: Eq + std::hash::Hash + Clone>(vals: Vec<T>) -> Vec<T> {
    let mut seen = std::collections::HashSet::new();
    let mut out = Vec::new();
    for v in vals {
        if seen.insert(v.clone()) {
            out.push(v);
        }
    }
    out
}

pub fn normalize_subject_name(name: &str) -> String {
    let drop: std::collections::HashSet<char> = ";/?:@&=+$,<>#%\"{}|\\^[]`\n\r".chars().collect();
    name.trim()
        .to_lowercase()
        .chars()
        .filter_map(|c| {
            if c == ' ' {
                Some('_')
            } else if drop.contains(&c) {
                None
            } else {
                Some(c)
            }
        })
        .collect()
}

static RE_SUBJECT: once_cell::sync::Lazy<regex::Regex> =
    once_cell::sync::Lazy::new(|| regex::Regex::new(r"[, _]+").unwrap());

pub fn subject_name_to_key(subject_type: &str, name: &str) -> String {
    let mut prefix = String::from("/subjects/");
    if subject_type != "subject" {
        prefix.push_str(subject_type);
        prefix.push(':');
    }
    let lower = name.to_lowercase();
    let replaced = RE_SUBJECT.replace_all(&lower, "_");
    let trimmed = replaced.trim_matches('_').to_string();
    prefix + &trimmed
}

pub fn normalize_authors(authors: &[serde_json::Value]) -> Vec<serde_json::Value> {
    let mut out = Vec::new();
    for a in authors {
        if !a.get("author").is_some() {
            continue;
        }
        let author_val = a.get("author").unwrap();
        let author_key = if author_val.is_object() {
            author_val.clone()
        } else if author_val.is_string() {
            serde_json::json!({"key": author_val.as_str().unwrap()})
        } else {
            continue;
        };
        let t = a
            .get("type")
            .and_then(|v| v.get("key"))
            .and_then(|v| v.as_str())
            .unwrap_or("/type/author_role");
        out.push(serde_json::json!({
            "type": {"key": t},
            "author": author_key
        }));
    }
    out
}

pub fn extract_edition_olid(key: &str) -> String {
    // re_edition_key = /books/([^/]+)
    key.split('/').last().unwrap_or(key).to_string()
}

pub fn datetimestr_to_int(datestr: Option<&serde_json::Value>) -> i64 {
    use chrono::NaiveDateTime;
    let s = match datestr {
        Some(serde_json::Value::String(st)) => st.clone(),
        Some(serde_json::Value::Object(map)) => map
            .get("value")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        _ => String::new(),
    };
    if s.is_empty() {
        return chrono::Utc::now().timestamp();
    }
    // try parse "2017-09-02T21:26:46.300245"
    let parsed = NaiveDateTime::parse_from_str(&s, "%Y-%m-%dT%H:%M:%S%.f")
        .or_else(|_| NaiveDateTime::parse_from_str(&s, "%Y-%m-%dT%H:%M:%S"))
        .or_else(|_| chrono::DateTime::parse_from_rfc3339(&s).map(|d| d.naive_utc()));
    match parsed {
        Ok(dt) => dt.and_utc().timestamp(),
        Err(_) => chrono::Utc::now().timestamp(),
    }
}

pub fn get_edition_ddcs(ed: &serde_json::Value) -> Vec<String> {
    let ddcs: Vec<String> = ed
        .get("dewey_decimal_class")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();
    if ddcs.len() > 1 {
        ddcs.into_iter()
            .filter(|d| !matches!(d.as_str(), "92" | "920" | "092"))
            .collect()
    } else {
        ddcs
    }
}

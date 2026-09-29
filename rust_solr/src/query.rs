use anyhow::Result;
use duckdb::{params, Connection};
use serde_json::Value;

pub struct Fetched {
    pub works: Vec<Value>,
    pub work_keys: Vec<String>,
    pub editions_by_work: std::collections::HashMap<String, Vec<Value>>,
    pub authors: std::collections::HashMap<String, Value>,
    pub ia_metadata: std::collections::HashMap<String, IaLite>,
    /// "/series/OLxxL" -> name (from bronze other.parquet); prod fetches these docs
    pub series_docs: std::collections::HashMap<String, String>,
}

/// Lite IA metadata for one ocaid; mirrors bp.IALiteMetadata fields used for ebook access.
#[derive(Clone, Debug)]
pub struct IaLite {
    pub collections: Vec<String>,
    pub access_restricted_item: bool,
}

/// Only the ocaids actually present in this chunk's editions are loaded, so the
/// map stays small regardless of lake size.
fn load_ia_metadata(
    con: &Connection,
    ia_metadata_path: &str,
    editions_by_work: &std::collections::HashMap<String, Vec<Value>>,
) -> Result<std::collections::HashMap<String, IaLite>> {
    let mut out = std::collections::HashMap::new();
    let mut ocaids = std::collections::HashSet::new();
    for eds in editions_by_work.values() {
        for ed in eds {
            if let Some(o) = ed.get("ocaid").and_then(|v| v.as_str()) {
                let t = o.trim();
                if !t.is_empty() {
                    ocaids.insert(t.to_string());
                }
            }
        }
    }
    if ocaids.is_empty() {
        return Ok(out);
    }
    con.execute("CREATE TEMP TABLE ok (ocaid VARCHAR)", [])?;
    {
        let mut app = con.appender("ok")?;
        for k in &ocaids {
            app.append_row(params![k])?;
        }
        app.flush()?;
    }
    let path = ia_metadata_path.replace('\'', "''");
    let mut stmt = con.prepare(&format!(
        "SELECT i.identifier, i.collections, i.ari FROM read_parquet('{}') i JOIN ok ON i.identifier = ok.ocaid",
        path
    ))?;
    let rows = stmt.query_map([], |row| {
        let ident: String = row.get(0)?;
        let collections_json: String = row.get(1)?;
        let ari: bool = row.get(2)?;
        Ok((ident, collections_json, ari))
    })?;
    for r in rows {
        let (ident, collections_json, ari) = r?;
        let collections =
            serde_json::from_str::<Vec<String>>(&collections_json).unwrap_or_default();
        out.insert(
            ident,
            IaLite {
                collections,
                access_restricted_item: ari,
            },
        );
    }
    eprintln!("Loaded {} IA metadata entries", out.len());
    Ok(out)
}

#[derive(serde::Deserialize, Clone, Debug)]
pub struct Chunk {
    pub n: usize,
    pub lo: i64,
    pub hi: i64,
}

fn bucket_paths(base: &std::path::Path, bmin: i64, bmax: i64) -> Vec<String> {
    let mut paths = Vec::new();
    for b in bmin..=bmax {
        let dir = base.join(format!("bucket={}", b));
        if !dir.is_dir() {
            continue;
        }
        // Prefer the single-file contract; fall back to any *.parquet shards (DuckDB partitioned
        // COPY can emit data_N.parquet when threads > 1).
        let single = dir.join("data.parquet");
        if single.exists() {
            paths.push(single.to_string_lossy().to_string());
            continue;
        }
        let mut shards: Vec<String> = std::fs::read_dir(&dir)
            .into_iter()
            .flatten()
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .filter(|p| p.extension().map(|x| x == "parquet").unwrap_or(false))
            .map(|p| p.to_string_lossy().to_string())
            .collect();
        shards.sort();
        paths.extend(shards);
    }
    paths
}

fn read_bucket_rows(
    con: &Connection,
    paths: &[String],
    id_filter: Option<(i64, i64)>,
    cols: &str,
) -> Result<Vec<(Option<String>, String)>> {
    if paths.is_empty() {
        return Ok(Vec::new());
    }
    let list = paths
        .iter()
        .map(|p| format!("'{}'", p))
        .collect::<Vec<_>>()
        .join(",");
    let sql = match id_filter {
        Some((lo, hi)) => format!(
            "SELECT {} FROM read_parquet([{}]) WHERE id BETWEEN {} AND {}",
            cols, list, lo, hi
        ),
        None => format!("SELECT {} FROM read_parquet([{}])", cols, list),
    };
    let mut stmt = con.prepare(&sql)?;
    let rows = stmt
        .query_map([], |row| {
            let a: Option<String> = row.get(0)?;
            let j: String = row.get(1)?;
            Ok((a, j))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(rows)
}

/// Mirrors WorkSolrUpdater.update_key's /type/edition branch (work.py:67-83): orphan editions
/// are indexed as standalone works under a /works/OLxxxM key.
/// Load /type/series docs from bronze other.parquet (key -> name) so series_name matches
/// production, which fetches the series doc before building (work.py:397).
fn load_series_docs(
    con: &Connection,
    bronze_works: &str,
) -> Result<std::collections::HashMap<String, String>> {
    let mut out = std::collections::HashMap::new();
    let other = match std::path::Path::new(bronze_works).parent() {
        Some(dir) => dir.join("other.parquet"),
        None => return Ok(out),
    };
    if !other.exists() {
        return Ok(out);
    }
    let mut stmt = con.prepare(&format!(
        "SELECT JSON FROM '{}' WHERE Type = '/type/series'",
        other.to_string_lossy().replace('\'', "''")
    ))?;
    let rows = stmt.query_map([], |row| {
        let j: String = row.get(0)?;
        Ok(j)
    })?;
    for r in rows {
        if let Ok(v) = serde_json::from_str::<Value>(&r?) {
            if let (Some(k), name) = (
                v.get("key").and_then(|x| x.as_str()),
                v.get("name").and_then(|x| x.as_str()),
            ) {
                out.insert(k.to_string(), name.unwrap_or_default().to_string());
            }
        }
    }
    eprintln!("Loaded {} series docs", out.len());
    Ok(out)
}

pub fn synthesize_fake_work(ed: &Value, fake_key: &str) -> Value {
    let mut fw = serde_json::Map::new();
    fw.insert("key".to_string(), json!(fake_key));
    fw.insert("type".to_string(), json!({"key": "/type/work"}));
    if let Some(t) = ed.get("title") {
        fw.insert("title".to_string(), t.clone());
    }
    fw.insert("editions".to_string(), json!([ed]));
    if let Some(authors) = ed.get("authors") {
        fw.insert("authors".to_string(), authors.clone());
    }
    if let Some(subs) = ed
        .get("subjects")
        .filter(|s| s.as_array().map(|a| !a.is_empty()).unwrap_or(false))
    {
        fw.insert("subjects".to_string(), subs.clone());
    }
    Value::Object(fw)
}

pub fn fetch(
    limit: usize,
    offset: usize,
    start_at: &str,
    bronze_works: &str,
    silver_editions: &str,
    bronze_authors: &str,
    chunks_path: Option<&str>,
    chunk_index: usize,
    ia_metadata_path: Option<&str>,
) -> Result<Fetched> {
    let mut con = Connection::open_in_memory()?;
    let t0 = std::time::Instant::now();

    let chunk: Option<Chunk> = chunks_path.and_then(|cp| {
        let data = std::fs::read_to_string(cp).ok()?;
        let chunks: Vec<Chunk> = serde_json::from_str(&data).ok()?;
        chunks.get(chunk_index).cloned()
    });

    // Chunked mode: numeric-OLID ranges; works/editions both bucketed by id//100000,
    // zonemap-prunable reads.
    let (works_raw, edition_raw): (Vec<(String, String)>, Vec<(Option<String>, String)>);
    let mut is_chunked = false;
    let mut chunk_range: Option<(i64, i64)> = None;
    if let Some(c) = &chunk {
        let silver_parent = std::path::Path::new(silver_editions)
            .parent()
            .unwrap_or(std::path::Path::new("lake/silver"));
        let works_base = silver_parent.join("works_b");
        let ed_base = silver_parent.join("editions_bucketed");
        let (lo, hi) = (c.lo, c.hi);
        chunk_range = Some((lo, hi));
        is_chunked = true;

        let wpaths = bucket_paths(&works_base, lo / 100000, hi / 100000);
        works_raw = read_bucket_rows(&con, &wpaths, Some((lo, hi)), "Key, JSON")?
            .into_iter()
            .map(|(k, j)| (k.unwrap_or_default(), j))
            .collect();

        let epaths = bucket_paths(&ed_base, lo / 100000, hi / 100000);
        edition_raw = read_bucket_rows(&con, &epaths, None, "work_key, JSON")?;
    } else {
        // Legacy path: lexicographic sample window; requires ORDER BY for determinism.
        // Inclusive from the given key on a fresh run; exclusive only when paginating.
        let _ = offset; // unused beyond pagination boundary
        let cmp = if offset == 0 { ">=" } else { ">" };
        con.execute(
            &format!(
            "CREATE TEMP TABLE sk AS SELECT Key FROM '{}' WHERE Key {} '{}' ORDER BY Key LIMIT {}",
            bronze_works, cmp, start_at, limit
        ),
            [],
        )?;
        works_raw = {
            let mut stmt = con.prepare(&format!(
                "SELECT w.Key, w.JSON FROM '{}' w JOIN sk ON w.Key = sk.Key ORDER BY w.Key",
                bronze_works
            ))?;
            stmt.query_map([], |row| {
                let k: String = row.get(0)?;
                let j: String = row.get(1)?;
                Ok((k, j))
            })?
            .collect::<Result<Vec<_>, _>>()?
        };
        let mut stmt2 = con.prepare(&format!(
            "SELECT e.work_key, e.JSON FROM '{}' e JOIN sk ON e.work_key = sk.Key",
            silver_editions
        ))?;
        edition_raw = stmt2
            .query_map([], |row| {
                let wkey: Option<String> = row.get(0)?;
                let j: String = row.get(1)?;
                Ok((wkey, j))
            })?
            .collect::<Result<Vec<_>, _>>()?;
    }
    let t1 = std::time::Instant::now();

    // Parse works
    let mut works = Vec::with_capacity(works_raw.len());
    let mut work_keys = Vec::with_capacity(works_raw.len());
    for (k, j) in works_raw {
        let v: Value = serde_json::from_str(&j)
            .unwrap_or_else(|_| serde_json::from_str(&j.replace("'", "\"")).unwrap_or(json!({})));
        works.push(v);
        work_keys.push(k);
    }

    let work_keys_set: std::collections::HashSet<String> = work_keys.iter().cloned().collect();
    let mut editions_by_work: std::collections::HashMap<String, Vec<Value>> =
        work_keys.iter().map(|k| (k.clone(), Vec::new())).collect();
    for (wkey_opt, j) in edition_raw {
        if let Some(wkey) = wkey_opt {
            if let Some(entry) = editions_by_work.get_mut(&wkey) {
                let v: Value = serde_json::from_str(&j).unwrap_or(json!({}));
                entry.push(v);
            } else if is_chunked && work_keys_set.contains(&wkey) {
                let v: Value = serde_json::from_str(&j).unwrap_or(json!({}));
                editions_by_work.entry(wkey).or_default().push(v);
            }
        }
    }
    // Deterministic edition order (by key) so picks like cover_edition_key are stable
    for eds in editions_by_work.values_mut() {
        eds.sort_by(|a, b| {
            let ka = a.get("key").and_then(|v| v.as_str()).unwrap_or("");
            let kb = b.get("key").and_then(|v| v.as_str()).unwrap_or("");
            ka.cmp(kb)
        });
    }

    // Orphan editions (no linked work) -> standalone fake works /works/OLxxxM, like prod.
    // They live in their own bucketed set since editions_bucketed drops NULL work_key rows.
    if let Some((lo, hi)) = chunk_range {
        let silver_parent = std::path::Path::new(silver_editions)
            .parent()
            .unwrap_or(std::path::Path::new("lake/silver"));
        let obase = silver_parent.join("orphans_bucketed");
        let opaths = bucket_paths(&obase, lo / 100000, hi / 100000);
        let orphan_rows = read_bucket_rows(&con, &opaths, Some((lo, hi)), "work_key, JSON")?;
        let mut n_orphans = 0usize;
        for (_, j) in orphan_rows {
            let ed: Value = match serde_json::from_str(&j) {
                Ok(v) => v,
                Err(_) => continue,
            };
            let ed_key = ed.get("key").and_then(|v| v.as_str()).unwrap_or("");
            if !ed_key.starts_with("/books/") {
                continue;
            }
            let fake_key = ed_key.replacen("/books/", "/works/", 1);
            n_orphans += 1;
            editions_by_work.insert(fake_key.clone(), vec![ed.clone()]);
            work_keys.push(fake_key.clone());
            works.push(synthesize_fake_work(&ed, &fake_key));
        }
        if n_orphans > 0 {
            eprintln!("Indexed {} orphan editions as fake works", n_orphans);
        }
    }
    let t2 = std::time::Instant::now();

    // Authors: collect keys in Rust then appender JOIN (keep for now)
    let mut author_keys = std::collections::HashSet::new();
    for w in &works {
        if let Some(arr) = w.get("authors").and_then(|v| v.as_array()) {
            for a in arr {
                let ak = a
                    .get("author")
                    .and_then(|v| {
                        if v.is_object() {
                            v.get("key").and_then(|k| k.as_str()).map(|s| s.to_string())
                        } else if v.is_string() {
                            v.as_str().map(|s| s.to_string())
                        } else {
                            None
                        }
                    })
                    .or_else(|| a.get("key").and_then(|v| v.as_str()).map(|s| s.to_string()));
                if let Some(k) = ak {
                    author_keys.insert(k);
                }
            }
        }
    }
    let author_keys_vec: Vec<String> = author_keys.into_iter().collect();
    let mut authors = std::collections::HashMap::new();
    if !author_keys_vec.is_empty() {
        if is_chunked {
            // chunked: new connection pattern same; reuse con is fine
            con.execute("CREATE TEMP TABLE ak (Key VARCHAR)", [])?;
        } else {
            con.execute("CREATE TEMP TABLE ak (Key VARCHAR)", [])?;
        }
        {
            let mut app = con.appender("ak")?;
            for k in &author_keys_vec {
                app.append_row(params![k])?;
            }
            app.flush()?;
        }
        let mut stmt4 = con.prepare(&format!(
            "SELECT a.JSON FROM '{}' a JOIN ak ON a.Key = ak.Key",
            bronze_authors
        ))?;
        let iter = stmt4.query_map([], |row| {
            let j: String = row.get(0)?;
            Ok(j)
        })?;
        let author_jsons: Vec<String> = iter.collect::<Result<Vec<String>, _>>()?;
        for j in author_jsons {
            if let Ok(v) = serde_json::from_str::<Value>(&j) {
                if let Some(k) = v.get("key").and_then(|x| x.as_str()) {
                    authors.insert(k.to_string(), v);
                }
            }
        }
    }
    let t3 = std::time::Instant::now();
    let ia_metadata = match ia_metadata_path {
        Some(path) => load_ia_metadata(&con, path, &editions_by_work)?,
        None => std::collections::HashMap::new(),
    };
    let series_docs = load_series_docs(&con, bronze_works)?;
    eprintln!(
        "Prepare: works {:.2}s editions {:.2}s authors {:.2}s ia {:.2}s total {:.2}s",
        (t1 - t0).as_secs_f64(),
        (t2 - t1).as_secs_f64(),
        (t3 - t2).as_secs_f64(),
        t3.elapsed().as_secs_f64(),
        (std::time::Instant::now() - t0).as_secs_f64()
    );
    Ok(Fetched {
        works,
        work_keys,
        editions_by_work,
        authors,
        ia_metadata,
        series_docs,
    })
}

use serde_json::json;

#[cfg(test)]
mod tests {
    use super::synthesize_fake_work;
    use serde_json::json;

    #[test]
    fn fake_work_matches_python_shape() {
        let ed = json!({
            "key": "/books/OL123M",
            "title": "Some Title",
            "authors": [{"key": "/authors/OL1A"}],
            "subjects": ["Adventure"],
            "type": {"key": "/type/edition"}
        });
        let fw = synthesize_fake_work(&ed, "/works/OL123M");
        assert_eq!(fw["key"], json!("/works/OL123M"));
        assert_eq!(fw["type"], json!({"key": "/type/work"}));
        assert_eq!(fw["title"], json!("Some Title"));
        assert_eq!(fw["editions"], json!([ed]));
        assert_eq!(fw["authors"], json!([{"key": "/authors/OL1A"}]));
        assert_eq!(fw["subjects"], json!(["Adventure"]));

        // no subjects -> key absent (python only copies when truthy)
        let mut ed2 = ed.clone();
        ed2.as_object_mut().unwrap().remove("subjects");
        let fw2 = synthesize_fake_work(&ed2, "/works/OL123M");
        assert!(fw2.get("subjects").is_none());
    }
}

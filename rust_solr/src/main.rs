mod helpers;
mod parquet;
mod query;
mod transform;

use anyhow::Result;
use clap::Parser;
use rayon::prelude::*;

#[derive(Parser, Debug)]
struct Args {
    #[arg(long, default_value = "10")]
    limit: usize,
    #[arg(long, default_value = "0")]
    offset: usize,
    #[arg(long, default_value = "/works/OL1W")]
    start_at: String,
    #[arg(long, default_value = "lake/bronze/works.parquet")]
    bronze_works: String,
    #[arg(long, default_value = "lake/silver/editions.parquet")]
    silver_editions: String,
    #[arg(long, default_value = "lake/bronze/authors.parquet")]
    bronze_authors: String,
    #[arg(long, default_value = "lake/gold/rust_sample.parquet")]
    out: String,
    #[arg(long, default_value = "18")]
    workers: usize,
    #[arg(long)]
    chunks: Option<String>,
    #[arg(long, default_value = "0")]
    chunk_index: usize,
    /// Output format: parquet (default) or ndjson (one JSON doc per line, for Solr /update/json/docs)
    #[arg(long, default_value = "parquet")]
    format: String,
    /// Optional ia_lite.parquet (from mvp_ia_fetch.py). When set, ebook_access/has_fulltext/
    /// public_scan_b/ia_collection are computed from real IA metadata instead of treating every
    /// ocaid as UNCLASSIFIED.
    #[arg(long)]
    ia_metadata: Option<String>,
}

fn main() -> Result<()> {
    let args = Args::parse();
    // set rayon threads
    rayon::ThreadPoolBuilder::new()
        .num_threads(args.workers)
        .build_global()
        .ok();

    let t0 = std::time::Instant::now();
    let fetched = query::fetch(
        args.limit,
        args.offset,
        &args.start_at,
        &args.bronze_works,
        &args.silver_editions,
        &args.bronze_authors,
        args.chunks.as_deref(),
        args.chunk_index,
        args.ia_metadata.as_deref(),
    )?;
    let prep = t0.elapsed().as_secs_f64();
    eprintln!("Fetched {} works", fetched.works.len());

    let t1 = std::time::Instant::now();
    // Use par_chunks directly without cloning works, and lookup global maps per work (no per-chunk ce/ca clone)
    let chunk_size = (fetched.works.len() + args.workers - 1) / args.workers.max(1);
    let docs: Vec<serde_json::Value> = fetched
        .works
        .par_chunks(chunk_size)
        .flat_map(|chunk| {
            let mut docs = Vec::with_capacity(chunk.len());
            for w in chunk {
                let key = w.get("key").and_then(|v| v.as_str()).unwrap_or("");
                let eds = fetched
                    .editions_by_work
                    .get(key)
                    .map(|v| v.as_slice())
                    .unwrap_or(&[]);
                // authors for this work: collect keys then lookup global map
                let work_authors: Vec<serde_json::Value> = w
                    .get("authors")
                    .and_then(|v| v.as_array())
                    .map(|arr| {
                        arr.iter()
                            .filter_map(|a| {
                                let ak = a
                                    .get("author")
                                    .and_then(|v| {
                                        if v.is_object() {
                                            v.get("key")
                                                .and_then(|k| k.as_str())
                                                .map(|s| s.to_string())
                                        } else if v.is_string() {
                                            v.as_str().map(|s| s.to_string())
                                        } else {
                                            None
                                        }
                                    })
                                    .or_else(|| {
                                        a.get("key").and_then(|v| v.as_str()).map(|s| s.to_string())
                                    });
                                ak.and_then(|k| fetched.authors.get(&k).cloned())
                            })
                            .collect()
                    })
                    .unwrap_or_default();
                let doc = transform::build_solr_doc(
                    w,
                    eds,
                    &work_authors,
                    &fetched.ia_metadata,
                    &fetched.series_docs,
                );
                docs.push(doc);
            }
            docs
        })
        .collect();
    let build = t1.elapsed().as_secs_f64();
    eprintln!(
        "Transform {} docs build {:.2}s {:.1} docs/s",
        docs.len(),
        build,
        docs.len() as f64 / build.max(0.001)
    );

    let t2 = std::time::Instant::now();
    match args.format.as_str() {
        "ndjson" => parquet::write_ndjson(&docs, &args.out)?,
        _ => parquet::write_gold(&docs, &args.out)?,
    }
    let write_t = t2.elapsed().as_secs_f64();
    let total = t0.elapsed().as_secs_f64();
    eprintln!(
        "Wrote {} to {} in {:.2}s total {:.2}s (prep {:.2}s + build {:.2}s)",
        docs.len(),
        args.out,
        write_t,
        total,
        prep,
        build
    );
    // estimate
    let full = 14406749.0;
    let est_build = (full / args.limit as f64) * build;
    let est_total = (full / args.limit as f64) * total;
    eprintln!(
        "Estimate full 14.4M: build {:.2}h total {:.2}h",
        est_build / 3600.0,
        est_total / 3600.0
    );
    Ok(())
}

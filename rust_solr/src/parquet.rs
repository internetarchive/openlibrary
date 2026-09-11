use anyhow::Result;
use arrow::array::{Int64Array, StringArray};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use parquet::arrow::ArrowWriter;
use std::fs::File;
use std::sync::Arc;

pub fn write_gold(docs: &[serde_json::Value], out_path: &str) -> Result<()> {
    use rayon::prelude::*;
    let schema = Arc::new(Schema::new(vec![
        Field::new("key", DataType::Utf8, false),
        Field::new("doc_json", DataType::Utf8, false),
        Field::new("title", DataType::Utf8, true),
        Field::new("edition_count", DataType::Int64, true),
    ]));

    let file = File::create(out_path)?;
    let mut writer = ArrowWriter::try_new(file, schema.clone(), None)?;

    // Write in row groups of 10k to reduce peak memory and allow parallel JSON serialization
    for chunk in docs.chunks(10000) {
        let keys: Vec<String> = chunk
            .iter()
            .map(|d| {
                d.get("key")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string()
            })
            .collect();
        // Parallel JSON serialization
        let doc_jsons: Vec<String> = chunk
            .par_iter()
            .map(|d| serde_json::to_string(d).unwrap())
            .collect();
        let titles: Vec<Option<String>> = chunk
            .iter()
            .map(|d| {
                d.get("title")
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string())
            })
            .collect();
        let edition_counts: Vec<Option<i64>> = chunk
            .iter()
            .map(|d| d.get("edition_count").and_then(|v| v.as_i64()))
            .collect();

        let batch = RecordBatch::try_new(
            schema.clone(),
            vec![
                Arc::new(StringArray::from(keys)),
                Arc::new(StringArray::from(doc_jsons)),
                Arc::new(StringArray::from(titles)),
                Arc::new(Int64Array::from(edition_counts)),
            ],
        )?;
        writer.write(&batch)?;
    }
    writer.close()?;
    Ok(())
}

/// Write one JSON document per line (Solr NDJSON streaming format for /update/json/docs).
pub fn write_ndjson(docs: &[serde_json::Value], out_path: &str) -> Result<()> {
    use rayon::prelude::*;
    use std::io::{BufWriter, Write};

    let file = File::create(out_path)?;
    let mut writer = BufWriter::with_capacity(8 << 20, file);

    // Parallel-serialize in chunks, then write sequentially to keep line order stable.
    for chunk in docs.chunks(10000) {
        let lines: Vec<String> = chunk
            .par_iter()
            .map(|d| serde_json::to_string(d).unwrap())
            .collect();
        for line in &lines {
            writer.write_all(line.as_bytes())?;
            writer.write_all(b"\n")?;
        }
    }
    writer.flush()?;
    Ok(())
}

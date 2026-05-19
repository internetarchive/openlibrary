-- Script to export Wikidata table from the Open Library database
-- When called, this will export the entire wikidata table as a TSV file
-- Usage: psql $PSQL_PARAMS -f dump-wikidata.sql | gzip -c > ol_dump_wikidata_YYYY-MM-DD.txt.gz

-- Export all rows from the wikidata table as tab-separated values
COPY wikidata TO STDOUT WITH (FORMAT csv, DELIMITER E'\t');

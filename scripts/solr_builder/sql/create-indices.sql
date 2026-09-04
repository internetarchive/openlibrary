ALTER TABLE test ADD CONSTRAINT "test_Key" PRIMARY KEY ("Key"); -- 35 min (10 May 2019, OJF)

CREATE INDEX "test_Type" ON test ("Type"); -- 4.5 min (10 May 2019, OJF)
CREATE INDEX "test_LastModified" ON test ("LastModified"); -- 3 min (10 May 2019, OJF)
CREATE INDEX test_JSON_location ON test (("JSON" ->> 'location')) WHERE "Type" = '/type/redirect'; -- 1 min (10 May 2019, OJF)
CREATE INDEX test_JSON_works ON test (("JSON" -> 'works' -> 0 ->> 'key')) WHERE "Type" = '/type/edition'; -- 8.45 min (10 May 2019, OJF)
CREATE INDEX test_orphans_Key ON test ("Key") WHERE "Type" = '/type/edition' AND "JSON" -> 'works' -> 0 ->> 'key' IS NULL; -- 25min (23 Mar 2021, OJF)
CREATE INDEX test_Type_Key ON test ("Type", "Key"); -- 21 min (10 May 2019, OJF)
CREATE INDEX cover_id ON cover (id);
-- Per-batch range lookups in solr_builder.py cache_work_ratings/cache_work_reading_logs
-- full-scan these tables otherwise; with 18 parallel runners that thrashes disk.
CREATE INDEX ratings_WorkKey ON ratings ("WorkKey"); -- 34s (21 Aug 2026, 8.4M rows)
CREATE INDEX reading_log_WorkKey ON reading_log ("WorkKey"); -- 7.5m (21 Aug 2026, 12.5M rows)

-- NET: 1.25 hr (10 May 2019, OJF)

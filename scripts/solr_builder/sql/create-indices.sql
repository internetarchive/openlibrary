ALTER TABLE test ADD CONSTRAINT "test_Key" PRIMARY KEY ("Key"); -- 35 min (10 May 2019, OJF)

CREATE INDEX "test_Type" ON test ("Type"); -- 4.5 min (10 May 2019, OJF)
CREATE INDEX "test_LastModified" ON test ("LastModified"); -- 3 min (10 May 2019, OJF)
-- 1 min (10 May 2019, OJF)
CREATE INDEX test_json_location ON test (("JSON" ->> 'location')) WHERE "Type" = '/type/redirect';
-- 8.45 min (10 May 2019, OJF)
CREATE INDEX test_json_works ON test (("JSON" -> 'works' -> 0 ->> 'key')) WHERE "Type" = '/type/edition';
-- 25min (23 Mar 2021, OJF)
CREATE INDEX test_orphans_key ON test ("Key") WHERE "Type" = '/type/edition'
AND "JSON" -> 'works' -> 0 ->> 'key' IS NULL;
CREATE INDEX test_type_key ON test ("Type", "Key"); -- 21 min (10 May 2019, OJF)

-- NET: 1.25 hr (10 May 2019, OJF)

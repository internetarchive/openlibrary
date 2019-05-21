ALTER TABLE test ADD CONSTRAINT "test_Key" PRIMARY KEY ("Key"); -- 35 min (10 May 2019, OJF)

CREATE INDEX "test_Type" ON test ("Type"); -- 4.5 min (10 May 2019, OJF)
CREATE INDEX "test_LastModified" ON test ("LastModified"); -- 3 min (10 May 2019, OJF)
CREATE INDEX test_JSON_location ON test (("JSON" ->> 'location')) WHERE "Type" = '/type/redirect'; -- 1 min (10 May 2019, OJF)
CREATE INDEX test_JSON_works ON test (("JSON" -> 'works' -> 0 ->> 'key')) WHERE "Type" = '/type/edition'; -- 8.45 min (10 May 2019, OJF)
CREATE INDEX test_Type_Key ON test ("Type", "Key"); -- 21 min (10 May 2019, OJF)

-- NET: 1.25 hr (10 May 2019, OJF)
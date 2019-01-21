ALTER TABLE test ADD CONSTRAINT "test_Key" PRIMARY KEY ("Key");

CREATE INDEX "test_Type" ON test ("Type");
CREATE INDEX "test_LastModified" ON test ("LastModified"); -- ~3min
CREATE INDEX test_JSON_location ON test (("JSON" ->> 'location')) WHERE "Type" = '/type/redirect'; -- ~ 8min
CREATE INDEX test_JSON_works ON test (("JSON" -> 'works' -> 0 ->> 'key')) WHERE "Type" = '/type/edition';
CREATE INDEX test_Type_Key ON test ("Type", "Key");
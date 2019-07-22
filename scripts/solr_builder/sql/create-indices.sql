ALTER TABLE entity ADD CONSTRAINT entity_key PRIMARY KEY (keyid); -- 35 min (10 May 2019, OJF)

CREATE INDEX entity_etype ON entity (etype); -- 4.5 min (10 May 2019, OJF)
CREATE INDEX entity_last_modified ON entity (last_modified); -- 3 min (10 May 2019, OJF)
CREATE INDEX entity_content_location ON entity ((content ->> 'location')) WHERE etype = '/type/redirect'; -- 1 min (10 May 2019, OJF)
CREATE INDEX entity_content_works ON entity ((content -> 'works' -> 0 ->> 'key')) WHERE etype = '/type/edition'; -- 8.45 min (10 May 2019, OJF)
-- What is the index below for? it's probably not very useful in its current form
CREATE INDEX entity_etype_keyid ON Entity (etype, keyid); -- 21 min (10 May 2019, OJF)

-- NET: ~20 min (modern SSD laptop, 2019-07), 1.25 hr (10 May 2019, OJF)

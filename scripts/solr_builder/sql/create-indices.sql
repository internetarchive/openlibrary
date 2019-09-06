ALTER TABLE entity ADD CONSTRAINT entity_key PRIMARY KEY (keyid); -- 35 min (10 May 2019, OJF)

CREATE INDEX entity_etype ON entity (etype); -- 4.5 min (10 May 2019, OJF)
CREATE INDEX entity_last_modified ON entity (last_modified); -- 3 min (10 May 2019, OJF)
CREATE INDEX entity_content_location ON entity ((content ->> 'location')) WHERE etype = '/type/redirect'; -- 1 min (10 May 2019, OJF)
CREATE INDEX entity_content_works ON entity ((content -> 'works' -> 0 ->> 'key')) WHERE etype = '/type/edition'; -- 8.45 min (10 May 2019, OJF)
-- What is the index below for? it's probably not very useful in its current form
CREATE INDEX entity_etype_keyid ON Entity (etype, keyid); -- 21 min (10 May 2019, OJF)

-- NET: ~20 min (modern SSD laptop, 2019-07), 1.25 hr (10 May 2019, OJF)

VACUUM ANALYZE; -- rerun statistics

CREATE OR REPLACE FUNCTION entity_get_partition_markers(p_type VARCHAR, p_step INTEGER, p_offset INTEGER DEFAULT 0)
  RETURNS SETOF entity AS $$
DECLARE
  rec entity;
  cur CURSOR FOR SELECT * FROM entity WHERE etype = CAST(p_type AS type_enum) ORDER BY keyid OFFSET p_offset;
BEGIN
  OPEN cur;
  FETCH NEXT FROM cur INTO rec;
  LOOP
    RETURN NEXT rec;
    MOVE FORWARD (p_step-1) FROM cur;
    FETCH NEXT FROM cur INTO rec;
    EXIT WHEN NOT FOUND;
  END LOOP;
  CLOSE cur;
END; $$

LANGUAGE plpgsql;

-- Count all types and validate against download
-- TODO: Turn off table headers and add labels to counts
SELECT COUNT(*) FROM entity WHERE etype = CAST('/type/author' AS type_enum);
SELECT COUNT(*) FROM entity WHERE etype = CAST('/type/edition' AS type_enum);
SELECT COUNT(*) FROM entity WHERE etype = CAST('/type/work' AS type_enum);
SELECT COUNT(*) FROM entity;

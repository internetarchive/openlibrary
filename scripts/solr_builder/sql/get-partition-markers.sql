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
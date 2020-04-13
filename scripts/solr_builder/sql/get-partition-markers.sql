CREATE OR REPLACE FUNCTION test_get_partition_markers(p_type VARCHAR, p_step INTEGER, p_offset INTEGER DEFAULT 0)
  RETURNS SETOF test AS $$
DECLARE
  rec test;
  cur CURSOR FOR SELECT * FROM "test" WHERE "Type" = p_type ORDER BY "Key" OFFSET p_offset;
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
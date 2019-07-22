SELECT count(*)
FROM entity
WHERE etype = '/type/edition' AND content -> 'works' -> 0 ->> 'key' IS NULL;

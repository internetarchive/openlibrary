SELECT count(*)
FROM "test"
WHERE "Type" = '/type/edition' AND "JSON" -> 'works' -> 0 ->> 'key' IS NULL
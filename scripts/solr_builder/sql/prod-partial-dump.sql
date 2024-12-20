COPY (
    WITH modified_things AS (
        SELECT * FROM thing WHERE "last_modified" >= :'lo_date'
    )

    SELECT "id", "latest_revision", "data" FROM modified_things
    LEFT JOIN data ON "thing_id" = "id" AND "revision" = "latest_revision"
) TO STDOUT;
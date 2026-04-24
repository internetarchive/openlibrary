COPY (
    WITH modified_things AS (
        SELECT *
        FROM thing
        WHERE last_modified >= :'lo_date'
    )

    SELECT
        modified_things.id,
        modified_things.latest_revision,
        data.data
    FROM modified_things
    LEFT JOIN data ON modified_things.id = data.thing_id AND modified_things.latest_revision = data.revision
) TO STDOUT;

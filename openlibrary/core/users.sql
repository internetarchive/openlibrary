CREATE ROLE readcreateaccess;

-- Grant access to existing tables
GRANT USAGE ON SCHEMA public TO readcreateaccess;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readcreateaccess;

-- Grant access to future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readcreateaccess;

-- Create user for solr-updater
CREATE USER solrupdater;
GRANT readcreateaccess TO solrupdater;

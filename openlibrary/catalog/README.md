# Catalog

This contains code that was originally part of early standalone
import and catalog management tools which have now been integrated
into Open Library.

* `add_book` contains the main code used when books are imported into Open Library via `/api/import`.
* `marc` contains current and some legacy code used to parse binary and XML MARC records for import and display.
* `utils` contains an assortment of helper methods, many of which are legacy and unused. Current [openlibrary/solr](../../openlibrary/solr) code still makes use of some parts.
* `get_ia.py` contains `get_marc_record_from_ia()` which is the main method used to read MARC records stored on archive.org.

from openlibrary.core.lists.model import register_models

# Ensure that the models.setup() function is called with the correct parameters
upstream.models.setup()

# Register the List and ListChangeset models
register_models(List, ListChangeset)

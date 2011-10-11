class BaseStorage:
    """Base class for all Storage implementations.
    """
    def find_item(self, itemid):
        """Finds an item with the given itemid, None if the item is not found.
        """
        raise NotImplementedError()
        
class Item:
    def list_files(self):
        raise NotImplementedError()
        
    def get_file(self, filename):
        raise NotImplementedError()
        
class File:
    def read(self):
        raise NotImplementedError()


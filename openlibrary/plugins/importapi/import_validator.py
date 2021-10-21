from typing import List, Dict, Any

REQUIRED_KEYS = {
    'title',
    'source_records',
    'authors',
    'publishers',
    'publish_date'
}

class import_validator:

    def validate(self, data: Dict[str, Any]):
        if not REQUIRED_KEYS.issubset(data.keys()):
            return False

        for key in REQUIRED_KEYS:
            func = getattr(self, f'_validate_{key}')
            if not func(data[key]):
                return False
        return True

    def _validate_title(self, title: str) -> bool:
        return True if type(title) == str and len(title) else False

    def _validate_source_records(self, source_records: List[str]) -> bool:
        return True if type(source_records) == list and len(source_records) else False

    def _validate_author(self, author: Dict[str, Any]) -> bool:
        return True if type(author) == dict and "name" in author and type(author['name']) == str and len(author['name']) else False

    def _validate_authors(self, authors: List[Dict[str, Any]]) -> bool:
        if type(authors) is not list:
            return False
        if not len(authors):
            return False

        for author in authors:
            if not self._validate_author(author):
                return False
        return True

    def _validate_publishers(self, publishers: List[str]) -> bool:
        if type(publishers) is not list:
            return False
        if not len(publishers):
            return False
        
        for publisher in publishers:
            if not type(publisher) == str:
                return False
        return True

    def _validate_publish_date(self, date: str) -> bool:
        return True if type(date) == str and len(date) else False
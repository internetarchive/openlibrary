"""
To Run:

PYTHONPATH=. python ./scripts/providers/import_wikisource.py /olsystem/etc/openlibrary.yml
"""

import logging
import re
import requests
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from typing import Callable, Any

# Using both mwparserfromhell and wikitextparser because the former doesn't have a markup stripper and the latter doesn't have a method to get a template prop by key.
import mwparserfromhell as mw
import wikitextparser as wtp

from infogami import config
from openlibrary.config import load_config
from openlibrary.core.imports import Batch
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.pressbooks")

def update_url_with_params(url: str, new_params: dict[str, str]):
    url_parts = list(urlparse(url))
    query = dict(parse_qsl(url_parts[4]))
    query.update(new_params)
    url_parts[4] = urlencode(query)
    return urlunparse(url_parts)

class LangConfig:
    def __init__(self, langcode: str, ol_langcode: str, category_prefix: str, included_categories: list[str], excluded_categories: list[str]):
        self.langcode = langcode
        self.ol_langcode = ol_langcode
        self._category_prefix = category_prefix
        self._included_categories = included_categories
        self._excluded_categories = excluded_categories

    def _catformat(self, category: str) -> str:
        return f'{self._category_prefix}:{category}'
    
    def _api_url(self, category: str) -> str:
        url = f'https://{self.langcode}.wikisource.org/w/api.php'
        params = {
            'action': 'query',
            # Forces the inclusion of category data
            'generator': 'categorymembers',
            # Restrict to only validated texts
            'gcmtitle': self._catformat(category), 
            # Max response size allowed by the API
            'gcmlimit': 'max', 
            # Relevant page data. The inclusion of |revisions, and rvprop/rvslots, are used to get book info from the page's infobox.
            'prop': 'categories|revisions|images',
            # Includes as many categories per hit as possible
            'cllimit': 'max',
            # Infobox data
            'rvprop': 'content',
            'rvslots': 'main',
            # Output
            'format': 'json'
        }
        return update_url_with_params(url, params)
    
    @property
    def api_urls(self) -> str:
        return [self._api_url(c) for c in self._included_categories]
    
    @property
    def excluded_categories(self) -> list[str]:
        return [self._catformat(c) for c in self._excluded_categories]


# Each version of wikisource has different category names and prefixes,
# so the pool of categories to search within and the categories to filter out
# will have different names per wikisource version.
# Add more Wikisource languages here as we expand this script to support them.
ws_languages = [
    LangConfig(langcode='en', ol_langcode='eng', category_prefix='Category', included_categories=['Validated_texts'], excluded_categories=['Subpages', 'Posters'])
]

def create_batch(records: list[dict[str, str]]) -> None:
    """Creates Wikisource batch import job.

    Attempts to find existing Wikisource import batch.
    If nothing is found, a new batch is created. 
    """
    now = time.gmtime(time.time())
    batch_name = f'wikisource-{now.tm_year}{now.tm_mon}'
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items([{'ia_id': r['source_records'][0], 'data': r} for r in records])
    print(f'{len(records)} entries added to the batch import job.')


def update_map_data(page: dict, new_data: dict, cfg: LangConfig) -> dict[str, Any]:
    # Infobox params do not change from language to language as far as I can tell. "year" will always be "year".
    if "categories" in new_data:
        for cat in new_data["categories"]:
            if cat["title"] not in page["categories"]:
                page["categories"].append(cat["title"])

    if page["imagename"] == "" and "images" in new_data:
        image_names = [i for i in new_data['images'] if not i["title"].endswith(".svg") and i["title"] != ""]
        if len(image_names) > 0:
            page["imagename"] = image_names[0]["title"]

    if "revisions" in new_data and len(new_data["revisions"]) > 0 and "slots" in new_data["revisions"][0] and "main" in new_data["revisions"][0]["slots"] and "*" in new_data["revisions"][0]["slots"]["main"]:
        infobox = new_data["revisions"][0]["slots"]["main"]["*"]
        
        wikicode = mw.parse(infobox)
        templates = wikicode.filter_templates()
        try:
            template = templates[0]
        except:
            return

        try:
            # maybe regex match a 4 digit string
            yr = template.get("year").value.strip()
            match = re.search(r'\d{4}', yr)
            if match:
                page["year"] = match.group(0)
        except:
            pass

        try:
            author = template.get("author").value.strip()
            if author != "":
                authors = re.split(r'(?:\sand\s|,\s?)', author)
                if len(authors) > 0:
                    page["authors"] = authors
        except:
            pass

        try:
            notes = wtp.remove_markup(template.get("notes").value.strip())
            if notes != "":
                page["notes"] = notes
        except:
            pass

        try:
            subject: str = template.get("portal").value.strip()
            if subject != "":
                subjects = subject.split("/")
                for sub in subjects:
                    if sub not in page["subjects"]:
                        page["subjects"].append(sub)
        except:
            pass

        # TODO: Image


def scrape_api(url: str, cfg: LangConfig, imports: dict, batch: list, output_func: Callable):
    cont_url = url

    # Paginate through metadata about wikisource pages
    while True:
        with requests.get(cont_url, stream=True) as r:
            r.raise_for_status()
            data = r.json()
            if "query" not in data:
                break
            if "pages" not in data["query"]:
                break
            results = data["query"]["pages"]

            for id in results:
                page = results[id]
                title: str = page["title"]
                wikisource_id = f'{cfg.langcode}:{title.replace(" ", "_")}'

                if id not in imports:
                    imports[id] = {
                        "title": title,
                        "source_records": [f'wikisource:{wikisource_id}'],
                        "publishers": 'Wikisource',
                        "publish_date": "",
                        "authors": [],
                        "description": "",
                        "subjects": [],
                        "identifiers": {"wikisource": wikisource_id},
                        "languages": [cfg.ol_langcode],
                        "cover": "",
                        "categories": [], # Not an OL field, used for processing.
                        "imagename": "" # Not an OL field, used for processing.
                    }
                
                update_map_data(imports[id], page, cfg)

            # scrape_api next pagination
            if 'continue' in data:
                cont_url = update_url_with_params(url, data["continue"])
            else:
                break

    # The page query can't include image URLs, the "imageinfo" prop does nothing unless you're querying image names directly.
    # Here we'll query as many images as possible in one API request, build a map of the results, and then later each valid book will find its URL in this map.
    # Get all unique image filenames
    image_titles = []
    for title in imports:
        i = imports[title]
        if i["imagename"] != "" and i["imagename"] not in image_titles:
            image_titles.append(i["imagename"])

    # Build an image filename<->url map
    image_map = {}

    if len(image_titles) > 0:
        # API will only allow up to 50 images at a time to be requested
        for index in range(0,len(image_titles),50):
            end = index + 50
            if end > len(image_titles):
                end = len(image_titles)
        
            image_url = f'https://en.wikisource.org/w/api.php?action=query&titles={"|".join(image_titles[index:end])}&prop=imageinfo&format=json&iiprop=url'
            working_url = image_url

            # Paginate through results
            while True:
                with requests.get(working_url, stream=True) as r:
                    r.raise_for_status()
                    data = r.json()
                    if "query" not in data:
                        break
                    if "pages" not in data["query"]:
                        break
                    results = data["query"]["pages"]
                    for id in results:
                        img = results[id]
                        if "imageinfo" in img and img["title"] not in image_map and len(img["imageinfo"]) > 0 and "url" in img["imageinfo"][0]:
                            image_map[img["title"]] = img["imageinfo"][0]["url"]

                    # scrape_api next pagination
                    if 'continue' in data:
                        working_url = update_url_with_params(image_url, data["continue"])
                    else:
                        break

    # Add all valid books to the batch, and give them their image URLs
    for title in imports:
        i = imports[title]
        # Skip if it belongs to an ignored category
        if "categories" in i:
            excluded_categories = [c for c in i["categories"] if c in cfg.excluded_categories]
            if len(excluded_categories) > 0:
                continue
            # Remove category data, OL importer doesn't use it
            del(i["categories"])
        if "imagename" in i:
            if i["imagename"] != "" and i["imagename"] in image_map:
                i["cover"] = image_map[i["imagename"]]
            del(i["imagename"])
        batch.append(i)

    if len(batch) > 0:
        output_func(batch)

# If we want to process all Wikisource pages in more than one category, we have to do one API call per category per language.
def process_all_books(cfg: LangConfig, output_func: Callable):
    imports = {}
    batch = []
    for url in cfg.api_urls:
        scrape_api(url, cfg, imports, batch, output_func)


def main(ol_config: str, dry_run=False):
    """
    :param str ol_config: Path to openlibrary.yml file
    :param bool dry_run: If true, only print out records to import
    """
    load_config(ol_config)

    for ws_language in ws_languages:
        if not dry_run:
            process_all_books(ws_language, create_batch)
        else:
            process_all_books(ws_language, print)


if __name__ == '__main__':
    FnToCLI(main).run()

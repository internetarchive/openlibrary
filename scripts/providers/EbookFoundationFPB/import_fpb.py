import requests
import time
import json
import re
from bs4 import BeautifulSoup

from urllib import parse
from openlibrary.config import load_config
from openlibrary.utils import uniq
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

def main(ol_config: str):
    """
    :param str ol_config: Path to openlibrary.yml file
    """
    load_config(ol_config)


if __name__ == "__main__":
    FnToCLI(main).run()
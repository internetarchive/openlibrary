from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI


def main(ol_config: str):
    """
    :param str ol_config: Path to openlibrary.yml file
    """
    load_config(ol_config)


if __name__ == "__main__":
    FnToCLI(main).run()

"""
Deletes entries from the import_item table.

Reads ia_ids that should be deleted from an input file.  The input file is expected to be tab-delimited, and each line will have the following format:
{N number of ia_ids in this line} {edition_key} {ia_id 1} [...] {ia_id N}

Requires a configuration file in order to run.  You can use the following as a template for the configuration file:

[args]
in_file=./import-item-cleanup/in.txt
state_file=./import-item-cleanup/curline.txt
error_file=./import-item-cleanup/errors.txt
batch_size=1000
dry_run=True
ol_config=/path/to/openlibrary.yml
"""

import argparse
import time
from configparser import ConfigParser
from pathlib import Path

import _init_path  # noqa: F401 Imported for its side effect of setting PYTHONPATH

from openlibrary.config import load_config
from openlibrary.core.edits import (
    CommunityEditsQueue,  # noqa: F401 side effects may be needed
)
from openlibrary.core.imports import ImportItem


class DeleteImportItemJob:
    def __init__(
        self, in_file='', state_file='', error_file='', batch_size=1000, dry_run=False
    ):
        self.in_file = in_file
        self.state_file = state_file
        self.error_file = error_file

        self.batch_size = batch_size
        self.dry_run = dry_run

        self.start_line = 1
        state_path = Path(state_file)
        if state_path.exists():
            with state_path.open('r') as f:
                line = f.readline()
                if line:
                    self.start_line = int(line)

    def run(self):
        with open(self.in_file) as f:
            # Seek to start line
            for _ in range(1, self.start_line):
                f.readline()

            # Delete a batch of records
            lines_processed = 0
            affected_records = 0
            num_deleted = 0
            for _ in range(self.batch_size):
                line = f.readline()
                if not line:
                    break
                fields = line.strip().split('\t')
                ia_ids = fields[2:]
                try:
                    result = ImportItem.delete_items(ia_ids, _test=self.dry_run)
                    if self.dry_run:
                        # Result is string "DELETE FROM ..."
                        print(result)
                    else:
                        # Result is number of records deleted
                        num_deleted += result
                except Exception as e:
                    print(f'Error when deleting: {e}')
                    if not self.dry_run:
                        write_to(self.error_file, line, mode='a+')
                lines_processed += 1
                affected_records += int(fields[0])

        # Write next line number to state file:
        if not self.dry_run:
            write_to(self.state_file, f'{self.start_line + lines_processed}')

        return {
            'lines_processed': lines_processed,
            'num_deleted': num_deleted,
            'affected_records': affected_records,
        }


def write_to(filepath, s, mode='w+'):
    print(mode)
    path = Path(filepath)
    path.parent.mkdir(exist_ok=True, parents=True)

    with path.open(mode=mode) as f:
        f.write(s)


def read_args_from_config(config_path):
    path = Path(config_path)
    if not path.exists():
        raise Exception(f'No configuration file found at {config_path}')

    config = ConfigParser()
    config.read(path)
    args = config['args']

    return {
        'in_file': args.get('in_file'),
        'state_file': args.get('state_file'),
        'error_file': args.get('error_file'),
        'batch_size': args.getint('batch_size'),
        'dry_run': bool(args.get('dry_run')),
        'ol_config': args.get('ol_config'),
    }


def init_and_start(args):
    # Read arguments from config file:
    config_args = read_args_from_config(args.config_file)

    # Set up Open Library
    load_config(config_args['ol_config'])

    del config_args['ol_config']

    # Delete affected files
    results = DeleteImportItemJob(**config_args).run()

    print(f'Lines of input processed: {results["lines_processed"]}')
    print(f'Records read from input file: {results["affected_records"]}')
    print(f'Records deleted: {results["num_deleted"]}')


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'config_file', metavar='config_path', help='Path to configuration file'
    )
    parser.set_defaults(func=init_and_start)
    return parser


if __name__ == '__main__':
    start_time = time.time()

    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f'Error: {e}')
        print('Stopping script early.')

    end_time = time.time()
    print(f'\nTime elapsed: {end_time - start_time} seconds\n')
    print('Program terminated...')

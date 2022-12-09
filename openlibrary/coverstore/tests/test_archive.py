from pathlib import Path
from tarfile import TarFile
import tempfile
from unittest.mock import patch
from openlibrary.coverstore.archive import TarManager


class TestTarManager:
    def test_open_tarfile_creates_if_necessary(self):
        # Create a temporary empty directory
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch('openlibrary.coverstore.archive.config.data_root', tmp_dir),
        ):
            items_path = Path(tmp_dir) / 'items'
            tm = TarManager()
            tarfile, indexfile = tm.open_tarfile('covers_0000_00.tar')
            with tarfile, indexfile:
                assert (items_path).is_dir()
                assert (items_path / 'covers_0000').is_dir()
                assert (items_path / 'covers_0000' / 'covers_0000_00.tar').is_file()
                assert tarfile.mode == 'w'
                assert indexfile.mode == 'w'

    def test_open_tarfile_appends_if_exists(self):
        # Create a temporary directory with a tarfile
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch('openlibrary.coverstore.archive.config.data_root', tmp_dir),
        ):
            covers_0000_path = Path(tmp_dir) / 'items' / 'covers_0000'
            (covers_0000_path).mkdir(parents=True)
            TarFile(covers_0000_path / 'covers_0000_00.tar', 'w').close()
            (covers_0000_path / 'covers_0000_00.index').touch()
            tm = TarManager()
            tarfile, indexfile = tm.open_tarfile('covers_0000_00.tar')
            with tarfile, indexfile:
                assert tarfile.mode == 'a'
                assert indexfile.mode == 'a'

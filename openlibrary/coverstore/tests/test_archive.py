from .. import archive


def test_get_filename():
    # Basic usage
    assert archive.Batch.get_relpath("0008", "80") == "covers_0008/covers_0008_80"

    # Sizes
    assert (
        archive.Batch.get_relpath("0008", "80", size="s")
        == "s_covers_0008/s_covers_0008_80"
    )
    assert (
        archive.Batch.get_relpath("0008", "80", size="m")
        == "m_covers_0008/m_covers_0008_80"
    )
    assert (
        archive.Batch.get_relpath("0008", "80", size="l")
        == "l_covers_0008/l_covers_0008_80"
    )

    # Ext
    assert (
        archive.Batch.get_relpath("0008", "80", ext="tar")
        == "covers_0008/covers_0008_80.tar"
    )

    # Ext + Size
    assert (
        archive.Batch.get_relpath("0008", "80", size="l", ext="zip")
        == "l_covers_0008/l_covers_0008_80.zip"
    )


def test_get_batch_end_id():
    assert archive.CoverDB._get_batch_end_id(start_id=8820500) == 8830000


def test_id_to_item_and_batch_id():
    assert archive.Cover.id_to_item_and_batch_id(987_654_321) == ('0987', '65')

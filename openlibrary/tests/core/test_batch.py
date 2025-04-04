import pytest

from openlibrary.core.bookshelves import Bookshelves

@pytest.fixture
def mock_db(monkeypatch):
    class MockDB:
        def query(self, query, vars=None):
            """
            This if is here for get_users_read_status_of_work()
            """
            if "SELECT bookshelf_id" in query:
                return []
            return True

    monkeypatch.setattr("openlibrary.core.bookshelves.db.get_db", lambda: MockDB())

class TestBookshelvesBatchAdd:
    def test_batch_add_with_valid_data(self, mock_db):
        result = Bookshelves.add_batch(
          "openlibrary",
          {
            "1": [{
              "workId": "20011506",
              "editionId": "27191586"
            },
            {
              "workId": "20011507",
              "editionId": "27191587"
            }],
            "2": [{
              "workId": "20011508",
              "editionId": "27191588"
            },
            {
              "workId": "20011509",
              "editionId": "27191589"
            }],
            "3": [{
              "workId": "20011510",
              "editionId": "27191590"
            },
            {
              "workId": "20011511",
              "editionId": "27191591"
            }]
          }
        )

        assert result["success"] == True

    def test_batch_add_with_missing_edition_id(self, mock_db):
        with pytest.raises(KeyError):
            Bookshelves.add_batch(
              "openlibrary",
              {
                "1": [{
                  "workId": "20011506",
                }]
              }
            )

    def test_batch_add_with_missing_work_id(self, mock_db):
        with pytest.raises(KeyError):
            Bookshelves.add_batch(
              "openlibrary",
              {
                "1": [{
                  "editionId": "27191586",
                }]
              }
            )

    def test_batch_add_with_invalid_key(self, mock_db):
        with pytest.raises(KeyError):
            Bookshelves.add_batch(
              "openlibrary",
              {
                "1": [{
                  "workId": "20011506",
                  "editionId": "27191586"
                },
                {
                  "workId": "20011507",
                  "editionId": "27191587"
                }],
                "2": [{
                  "workId": "20011508",
                  "totally-not-the-right-key": "27191587"
                }]
              }
            )

    def test_batch_add_with_empty_data(self, mock_db):
        result = Bookshelves.add_batch(
          "openlibrary",
          {}
        )

        assert result["message"] == "All books already on shelf"
      
    def test_batch_add_with_invalid_data_1(self, mock_db):
      with pytest.raises(ValueError):
          Bookshelves.add_batch(
            "openlibrary",
            {
              "1": [{
                "workId": "20011506",
                "editionId": "27191586"
              },
              {
                "workId": "20011507",
                "editionId": "27191587"
              }],
              "2": [{
                "workId": "20011508",
                "editionId": "a-string-instead-of-int"
              }]
            }
          )
    def test_batch_add_with_invalid_data_2(self, mock_db):
      with pytest.raises(TypeError):
          Bookshelves.add_batch(
            "openlibrary",
            {
              "1": [{
                "workId": "20011506",
                "editionId": "27191586"
              },
              {
                "workId": "20011507",
                "editionId": "27191587"
              }],
              "2": [{
                "workId": None,
                "editionId": None
              }]
            }
          )
    
    def test_gracefully_handles_duplicate_work_ids(self, mock_db):
        result = Bookshelves.add_batch(
          "openlibrary",
          {
            "1": [{
              "workId": "20011506",
              "editionId": "27191586"
            },
            {
              "workId": "20011506",
              "editionId": "27191587"
            }]
          }
        )

        assert result["success"] == True
        assert result["successfully_added"].count("20011506") == 1
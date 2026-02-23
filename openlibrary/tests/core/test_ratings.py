"""
Tests for openlibrary.core.ratings

Focuses on testing the pure mathematical functions that compute rating statistics.
These functions don't require database access and test the core rating logic.
"""

from openlibrary.core.ratings import Ratings


class TestComputeSortableRating:
    """Test the Bayesian lower bound ranking algorithm."""

    def test_all_five_stars(self):
        """A book with only 5-star ratings should have a high sortable rating."""
        # 10 ratings, all 5 stars
        # The Bayesian lower bound is conservative, so it won't be 5.0
        result = Ratings.compute_sortable_rating([0, 0, 0, 0, 10])
        assert result > 3.5  # Should be high, but conservative

    def test_mixed_ratings(self):
        """Test with a realistic mix of ratings."""
        # A typical distribution: more 4-5 stars, some lower
        result = Ratings.compute_sortable_rating([2, 1, 3, 15, 25])
        # Should be between 3.5 and 4.5
        assert 3.5 < result < 4.5

    def test_single_rating(self):
        """A book with a single 5-star rating should be penalized."""
        one_five_star = Ratings.compute_sortable_rating([0, 0, 0, 0, 1])
        many_five_stars = Ratings.compute_sortable_rating([0, 0, 0, 0, 100])

        # The book with 100 ratings should rank higher
        assert many_five_stars > one_five_star

    def test_low_ratings(self):
        """Test with mostly low ratings."""
        result = Ratings.compute_sortable_rating([20, 15, 5, 1, 0])
        # Should be low, around 2 or below
        assert result < 2.5

    def test_no_ratings(self):
        """
        A book with no ratings gets a prior estimate (Bayesian default).
        This is a conservative middle-of-the-road rating, not zero.
        """
        result = Ratings.compute_sortable_rating([0, 0, 0, 0, 0])
        # The algorithm returns a prior around 2.0 (middle of 1-5 scale)
        assert 1.5 < result < 2.5

    def test_uniform_distribution(self):
        """
        Test with equal ratings across all stars.

        The Bayesian lower bound is conservative, so even a uniform
        distribution (which averages to 3.0) will give a lower value
        due to the uncertainty penalty.
        """
        result = Ratings.compute_sortable_rating([2, 2, 2, 2, 2])
        # Conservative estimate, lower than the true average of 3.0
        assert 2.0 < result < 3.0

    def test_more_ratings_same_average(self):
        """
        Two books with same average should rank differently based on count.
        More ratings = higher confidence = higher rank.
        """
        # Both have average of 3 stars, but one has more ratings
        few_ratings = Ratings.compute_sortable_rating([0, 0, 10, 0, 0])
        many_ratings = Ratings.compute_sortable_rating([0, 0, 100, 0, 0])

        assert many_ratings > few_ratings


class TestWorkRatingsSummaryFromCounts:
    """Test the ratings summary calculation from rating counts."""

    def test_simple_average(self):
        """Test basic average calculation."""
        result = Ratings.work_ratings_summary_from_counts([0, 0, 0, 0, 10])
        assert result['ratings_average'] == 5.0
        assert result['ratings_count'] == 10
        assert result['ratings_count_5'] == 10

    def test_weighted_average(self):
        """Test average with mixed ratings."""
        # 1 star: 2, 2 star: 1, 3 star: 3, 4 star: 15, 5 star: 25
        # Total: 46, Sum: 2*1 + 1*2 + 3*3 + 15*4 + 25*5 = 2 + 2 + 9 + 60 + 125 = 198
        # Average: 198 / 46 = 4.304...
        result = Ratings.work_ratings_summary_from_counts([2, 1, 3, 15, 25])
        assert abs(result['ratings_average'] - 4.304) < 0.01
        assert result['ratings_count'] == 46

    def test_empty_counts(self):
        """Test with no ratings."""
        result = Ratings.work_ratings_summary_from_counts([0, 0, 0, 0, 0])
        assert result['ratings_average'] == 0.0
        assert result['ratings_count'] == 0
        # Sortable rating uses Bayesian prior when no ratings exist
        assert 1.5 < result['ratings_sortable'] < 2.5

    def test_all_star_counts_preserved(self):
        """Ensure all individual star counts are preserved."""
        result = Ratings.work_ratings_summary_from_counts([5, 4, 3, 2, 1])
        assert result['ratings_count_1'] == 5
        assert result['ratings_count_2'] == 4
        assert result['ratings_count_3'] == 3
        assert result['ratings_count_4'] == 2
        assert result['ratings_count_5'] == 1

    def test_sortable_rating_calculated(self):
        """Verify sortable rating is calculated from counts."""
        result = Ratings.work_ratings_summary_from_counts([0, 0, 0, 0, 10])
        # Should match compute_sortable_rating for same counts
        assert result['ratings_sortable'] == Ratings.compute_sortable_rating(
            [0, 0, 0, 0, 10]
        )

#!/usr/bin/env python3
"""Unit tests for analyze_instructions.py"""

import json
import tempfile
import os
import unittest
from analyze_instructions import (
    position_weight,
    count_directives,
    count_directives_with_position,
    calculate_weighted_instructions,
    estimate_accuracy,
    get_accuracy_rating,
    extract_text_from_transcript,
    analyze_transcript,
    DIRECTIVE_WEIGHTS,
)


class TestPositionWeight(unittest.TestCase):
    """Tests for position_weight function."""

    def test_start_position(self):
        """Position 0 (start) should have weight 1.0."""
        self.assertAlmostEqual(position_weight(0.0), 1.0, places=2)

    def test_end_position(self):
        """Position 1 (end) should have weight 1.0."""
        self.assertAlmostEqual(position_weight(1.0), 1.0, places=2)

    def test_middle_position(self):
        """Position 0.5 (middle) should have weight 0.6."""
        self.assertAlmostEqual(position_weight(0.5), 0.6, places=2)

    def test_quarter_position(self):
        """Position 0.25 should have weight between 0.6 and 1.0."""
        weight = position_weight(0.25)
        self.assertGreater(weight, 0.6)
        self.assertLess(weight, 1.0)

    def test_symmetric(self):
        """Positions equidistant from middle should have same weight."""
        self.assertAlmostEqual(position_weight(0.25), position_weight(0.75), places=5)
        self.assertAlmostEqual(position_weight(0.1), position_weight(0.9), places=5)


class TestCountDirectives(unittest.TestCase):
    """Tests for count_directives function."""

    def test_modal_obligations(self):
        """Should count modal obligation patterns."""
        text = "You must do this. You should also do that. You need to check."
        counts = count_directives(text)
        self.assertEqual(counts['modal_obligation'], 3)

    def test_prohibitions(self):
        """Should count prohibition patterns."""
        text = "Never do this. Don't do that. You cannot proceed. Avoid errors."
        counts = count_directives(text)
        self.assertEqual(counts['prohibition'], 4)

    def test_absolutes(self):
        """Should count absolute patterns."""
        text = "Always check. Every time. Use only this. Exactly right."
        counts = count_directives(text)
        self.assertEqual(counts['absolute'], 4)

    def test_emphasis(self):
        """Should count emphasis patterns."""
        text = "This is important. It's critical. Essential for success. Mandatory step."
        counts = count_directives(text)
        self.assertEqual(counts['emphasis'], 4)

    def test_case_insensitive(self):
        """Should match regardless of case."""
        text = "MUST do this. Never DO that. ALWAYS check."
        counts = count_directives(text)
        self.assertEqual(counts['modal_obligation'], 1)
        self.assertEqual(counts['prohibition'], 1)
        self.assertEqual(counts['absolute'], 1)

    def test_empty_text(self):
        """Should return zero counts for empty text."""
        counts = count_directives("")
        self.assertEqual(sum(counts.values()), 0)


class TestCountDirectivesWithPosition(unittest.TestCase):
    """Tests for count_directives_with_position function."""

    def test_position_affects_weighted_total(self):
        """Instructions at edges should have higher weighted total than middle."""
        # Same text at different positions
        start_segment = [{'text': 'You must do this.', 'position': 0.0, 'role': 'system'}]
        middle_segment = [{'text': 'You must do this.', 'position': 0.5, 'role': 'user'}]

        _, start_weighted = count_directives_with_position(start_segment)
        _, middle_weighted = count_directives_with_position(middle_segment)

        self.assertGreater(start_weighted, middle_weighted)

    def test_raw_counts_same_regardless_of_position(self):
        """Raw counts should be the same regardless of position."""
        start_segment = [{'text': 'You must do this.', 'position': 0.0, 'role': 'system'}]
        middle_segment = [{'text': 'You must do this.', 'position': 0.5, 'role': 'user'}]

        start_counts, _ = count_directives_with_position(start_segment)
        middle_counts, _ = count_directives_with_position(middle_segment)

        self.assertEqual(start_counts, middle_counts)


class TestCalculateWeightedInstructions(unittest.TestCase):
    """Tests for calculate_weighted_instructions function."""

    def test_applies_category_weights(self):
        """Should apply correct weights to each category."""
        counts = {
            'modal_obligation': 10,
            'prohibition': 10,
            'absolute': 10,
            'imperative': 10,
            'emphasis': 10,
        }
        weighted = calculate_weighted_instructions(counts)

        expected = (
            10 * DIRECTIVE_WEIGHTS['modal_obligation'] +
            10 * DIRECTIVE_WEIGHTS['prohibition'] +
            10 * DIRECTIVE_WEIGHTS['absolute'] +
            10 * DIRECTIVE_WEIGHTS['imperative'] +
            10 * DIRECTIVE_WEIGHTS['emphasis']
        )
        self.assertAlmostEqual(weighted, expected, places=2)

    def test_empty_counts(self):
        """Should return 0 for empty counts."""
        counts = {}
        self.assertEqual(calculate_weighted_instructions(counts), 0.0)


class TestEstimateAccuracy(unittest.TestCase):
    """Tests for estimate_accuracy function."""

    def test_zero_instructions_high_accuracy(self):
        """Zero instructions should give base accuracy."""
        accuracy, factors = estimate_accuracy(0)
        self.assertAlmostEqual(accuracy, 98.0, places=1)

    def test_more_instructions_lower_accuracy(self):
        """More instructions should lower accuracy."""
        acc_low, _ = estimate_accuracy(10)
        acc_high, _ = estimate_accuracy(100)
        self.assertGreater(acc_low, acc_high)

    def test_accuracy_floor(self):
        """Accuracy should not go below floor."""
        accuracy, _ = estimate_accuracy(10000)
        self.assertGreaterEqual(accuracy, 60.0)

    def test_context_penalty(self):
        """Large contexts should reduce accuracy."""
        acc_small, factors_small = estimate_accuracy(50, context_tokens=10000)
        acc_large, factors_large = estimate_accuracy(50, context_tokens=150000)

        self.assertGreater(acc_small, acc_large)
        self.assertEqual(factors_small['context_penalty'], 0.0)
        self.assertGreater(factors_large['context_penalty'], 0.0)

    def test_returns_factors(self):
        """Should return breakdown of penalty factors."""
        accuracy, factors = estimate_accuracy(50, context_tokens=100000)
        self.assertIn('instruction_penalty', factors)
        self.assertIn('context_penalty', factors)


class TestGetAccuracyRating(unittest.TestCase):
    """Tests for get_accuracy_rating function."""

    def test_excellent(self):
        self.assertEqual(get_accuracy_rating(98), "excellent")
        self.assertEqual(get_accuracy_rating(95), "excellent")

    def test_good(self):
        self.assertEqual(get_accuracy_rating(90), "good")
        self.assertEqual(get_accuracy_rating(85), "good")

    def test_moderate(self):
        self.assertEqual(get_accuracy_rating(80), "moderate")
        self.assertEqual(get_accuracy_rating(75), "moderate")

    def test_degraded(self):
        self.assertEqual(get_accuracy_rating(70), "degraded")
        self.assertEqual(get_accuracy_rating(65), "degraded")

    def test_poor(self):
        self.assertEqual(get_accuracy_rating(60), "poor")
        self.assertEqual(get_accuracy_rating(50), "poor")


class TestExtractTextFromTranscript(unittest.TestCase):
    """Tests for extract_text_from_transcript function."""

    def test_handles_nested_message_format(self):
        """Should handle Claude Code's nested message format."""
        transcript = [
            {"message": {"role": "user", "content": "You must do this."}, "type": "message"},
            {"message": {"role": "assistant", "content": "OK"}, "type": "message"},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in transcript:
                f.write(json.dumps(msg) + '\n')
            f.flush()

            segments, stats = extract_text_from_transcript(f.name)

        os.unlink(f.name)

        self.assertEqual(len(segments), 1)  # Only user message counted
        self.assertEqual(segments[0]['text'], "You must do this.")
        self.assertEqual(stats['user_messages'], 1)
        self.assertEqual(stats['assistant_messages'], 1)

    def test_handles_flat_format(self):
        """Should handle flat message format."""
        transcript = [
            {"role": "system", "content": "You must follow rules."},
            {"role": "user", "content": "Hello"},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in transcript:
                f.write(json.dumps(msg) + '\n')
            f.flush()

            segments, stats = extract_text_from_transcript(f.name)

        os.unlink(f.name)

        self.assertEqual(len(segments), 2)
        self.assertEqual(stats['system_messages'], 1)
        self.assertEqual(stats['user_messages'], 1)

    def test_handles_missing_file(self):
        """Should return empty results for missing file."""
        segments, stats = extract_text_from_transcript('/nonexistent/path.jsonl')
        self.assertEqual(segments, [])
        self.assertEqual(stats['total_messages'], 0)


class TestAnalyzeTranscript(unittest.TestCase):
    """Tests for analyze_transcript function."""

    def test_full_analysis(self):
        """Should return complete analysis with all fields."""
        transcript = [
            {"role": "system", "content": "You must always follow these rules. Never break them. This is critical."},
            {"role": "user", "content": "Do this task."},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in transcript:
                f.write(json.dumps(msg) + '\n')
            f.flush()

            result = analyze_transcript(f.name, context_tokens=25000)

        os.unlink(f.name)

        # Check all expected fields present
        self.assertIn('instruction_count', result)
        self.assertIn('weighted_count', result)
        self.assertIn('position_weighted_count', result)
        self.assertIn('density', result)
        self.assertIn('estimated_accuracy', result)
        self.assertIn('rating', result)
        self.assertIn('breakdown', result)
        self.assertIn('factors', result)
        self.assertIn('stats', result)

        # Check values are reasonable
        self.assertGreater(result['instruction_count'], 0)
        self.assertGreater(result['density'], 0)
        self.assertLessEqual(result['estimated_accuracy'], 98.0)

    def test_empty_transcript(self):
        """Should handle empty transcript gracefully."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.flush()
            result = analyze_transcript(f.name)

        os.unlink(f.name)

        self.assertEqual(result['instruction_count'], 0)
        self.assertEqual(result['estimated_accuracy'], 98.0)
        self.assertEqual(result['rating'], 'excellent')


class TestIntegration(unittest.TestCase):
    """Integration tests for the full pipeline."""

    def test_high_instruction_density_lowers_accuracy(self):
        """A transcript with many instructions should have lower accuracy."""
        # High instruction density
        high_density_content = """
        You must always follow these rules. Never skip any step.
        It is critical that you ensure every requirement is met.
        You should verify all inputs. Don't forget to check outputs.
        Important: always validate. Essential to avoid errors.
        """ * 10

        transcript = [{"role": "system", "content": high_density_content}]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in transcript:
                f.write(json.dumps(msg) + '\n')
            f.flush()

            result = analyze_transcript(f.name)

        os.unlink(f.name)

        # High instruction count should lower accuracy
        self.assertGreater(result['instruction_count'], 50)
        self.assertLess(result['estimated_accuracy'], 85.0)

    def test_code_heavy_transcript_high_accuracy(self):
        """A transcript with mostly code should have high accuracy."""
        code_content = """
        def hello_world():
            print("Hello, World!")

        def calculate_sum(a, b):
            return a + b

        class MyClass:
            def __init__(self):
                self.value = 0
        """ * 20

        transcript = [{"role": "user", "content": code_content}]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in transcript:
                f.write(json.dumps(msg) + '\n')
            f.flush()

            result = analyze_transcript(f.name)

        os.unlink(f.name)

        # Low instruction density should maintain high accuracy
        self.assertLess(result['density'], 1.0)
        self.assertGreater(result['estimated_accuracy'], 90.0)


if __name__ == '__main__':
    unittest.main()

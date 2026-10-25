import copy
import unittest

from tooling import workstation_performance as score


class WorkstationPolicyTests(unittest.TestCase):
    def pairs(self, values):
        return [{"reference": [1000] * 64, "candidate": [x] * 64} for x in values]

    def test_equivalent_and_exact_boundary_pass_without_float_rounding(self):
        self.assertTrue(score.latency_decision(self.pairs([1000] * 9))["passed"])
        self.assertTrue(score.latency_decision(self.pairs([1100] * 9))["passed"])
        self.assertFalse(score.latency_decision(self.pairs([1101] * 9))["passed"])
        huge = 2**60
        pairs = [{"reference": [huge] * 64, "candidate": [huge + 1] * 64}] * 9
        result = score.latency_decision(pairs)
        self.assertEqual(result["median_ratio"], [huge + 1, huge])

    def test_two_transient_spikes_pass_but_three_or_sustained_regression_fail(self):
        self.assertTrue(
            score.latency_decision(self.pairs([1000] * 7 + [100000] * 2))["passed"]
        )
        self.assertFalse(
            score.latency_decision(self.pairs([1000] * 6 + [100000] * 3))["passed"]
        )
        self.assertFalse(score.latency_decision(self.pairs([1200] * 9))["passed"])

    def test_all_input_pairs_and_samples_remain_required(self):
        valid = self.pairs([1000] * 9)
        for mutate in [
            lambda x: x.pop(),
            lambda x: x[0]["candidate"].pop(),
            lambda x: x[0]["reference"].__setitem__(0, True),
            lambda x: x[0].__setitem__("ignored", True),
            lambda x: x[0]["candidate"].__setitem__(1, -1),
        ]:
            value = copy.deepcopy(valid)
            mutate(value)
            with self.assertRaises(ValueError):
                score.latency_decision(value)

    def test_memory_never_hides_one_large_peak_in_a_median(self):
        values = [{"reference": 4 * 1048576, "candidate": 4 * 1048576}] * 9
        self.assertTrue(score.memory_decision(values)["passed"])
        values = copy.deepcopy(values)
        values[8] = {"reference": 4 * 1048576, "candidate": 96 * 1048576}
        result = score.memory_decision(values)
        self.assertFalse(result["passed"])
        self.assertFalse(result["absolute_passed"])
        self.assertEqual(len(result["all_pair_peaks_bytes"]), 9)

    def test_memory_relative_allowance_is_exact_and_separate(self):
        pairs = [{"reference": 10_000_000, "candidate": 12_048_576}] * 9
        self.assertTrue(score.memory_decision(pairs)["passed"])
        pairs[0] = {"reference": 10_000_000, "candidate": 12_048_577}
        self.assertFalse(score.memory_decision(pairs)["passed"])


if __name__ == "__main__":
    unittest.main()

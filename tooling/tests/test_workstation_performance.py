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

    def guarded_pairs(self):
        return [
            {
                lane: dict(
                    samples=[1000] * 64,
                    control_samples=[800] * 64,
                    whole_action_ns=1000000,
                )
                for lane in ("reference", "candidate")
            }
            for _ in range(9)
        ]

    def test_tail_catches_intermittent_stalls_with_unchanged_median(self):
        pairs = self.guarded_pairs()
        for pair in pairs:
            pair["candidate"]["samples"][-4:] = [2000] * 4
        result = score.guarded_latency_decision(pairs)
        self.assertTrue(result["channels"]["samples"]["median"]["passed"])
        self.assertFalse(result["channels"]["samples"]["tail"]["passed"])
        self.assertFalse(result["passed"])

    def test_whole_lifetime_catches_startup_or_warmup_only_delay(self):
        pairs = self.guarded_pairs()
        for pair in pairs:
            pair["candidate"]["whole_action_ns"] *= 2
        result = score.guarded_latency_decision(pairs)
        self.assertTrue(result["channels"]["samples"]["median"]["passed"])
        self.assertFalse(result["whole_process"]["passed"])
        self.assertFalse(result["passed"])

    def test_whole_and_tail_allow_two_transients_but_not_three(self):
        pairs = self.guarded_pairs()
        for pair in pairs[-2:]:
            pair["candidate"]["whole_action_ns"] *= 100
            pair["candidate"]["samples"] = [100000] * 64
        self.assertTrue(score.guarded_latency_decision(pairs)["passed"])
        pairs[-3]["candidate"]["whole_action_ns"] *= 100
        self.assertFalse(score.guarded_latency_decision(pairs)["passed"])

    def test_cli_common_mode_delay_cannot_cancel_from_both_marginals(self):
        pairs = self.guarded_pairs()
        self.assertTrue(score.guarded_latency_decision(pairs, cli=True)["passed"])
        for pair in pairs:
            for channel in ("samples", "control_samples"):
                pair["candidate"][channel] = [x * 2 for x in pair["candidate"][channel]]
        result = score.guarded_latency_decision(pairs, cli=True)
        self.assertFalse(result["passed"])
        self.assertEqual(
            result["request_control_ratios"][0]["candidate"][0], [2000, 1600]
        )

    def test_complete_whole_interval_is_required_and_policy_revision_is_bound(self):
        pairs = self.guarded_pairs()
        pairs[0]["candidate"]["whole_action_ns"] = True
        with self.assertRaises(ValueError):
            score.guarded_latency_decision(pairs)
        self.assertEqual(score.load_policy()["policy_revision"], 2)


if __name__ == "__main__":
    unittest.main()

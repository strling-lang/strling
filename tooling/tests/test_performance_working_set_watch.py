"""Closed-data tests; no native acquisition or performance samples."""

import unittest

from tooling import performance_working_set_watch as watch


def packet(*rows):
    return b"".join(watch.RECORD.pack(*row) for row in rows)


END = (0, 0, 0, 0)
PAGE = (123, 4096, 17, 0)


class WorkingSetWatchTests(unittest.TestCase):
    def test_x64_layout_and_raw_order(self):
        self.assertEqual(watch.RECORD.size, 32)
        parsed = watch.decode(packet(PAGE, PAGE, END) + bytes(32))
        self.assertEqual(
            parsed["records"], [dict(pc=123, address=4096, thread=17, flags=0)] * 2
        )
        self.assertEqual(parsed["lost_records"], 0)
        self.assertIs(parsed["certification_eligible"], False)

    def test_loss_is_retained_and_never_coverage(self):
        raw = packet(PAGE, (0, 7, 19, 0))
        self.assertEqual(watch.decode(raw)["lost_records"], 7)
        self.assertEqual(watch.decode(raw)["terminator_thread"], 19)
        with self.assertRaisesRegex(ValueError, "records lost"):
            watch.require_promised_pages([raw], [4096])

    def test_malformed_buffers(self):
        for raw in (
            None,
            bytearray(32),
            b"",
            bytes(31),
            bytes(33),
            bytes(watch.MAX_BYTES + 32),
            packet(PAGE),
            packet((1, 0, 2, 0), END),
            packet(END, PAGE),
        ):
            with self.subTest(
                raw_type=type(raw), length=len(raw) if raw is not None else 0
            ):
                with self.assertRaises(ValueError):
                    watch.decode(raw)

    def test_unknown_reserved_flags_are_retained_but_not_accepted(self):
        for raw in (packet((123, 4096, 17, 1), END), packet(PAGE, (0, 0, 0, 8))):
            self.assertIs(watch.decode(raw)["certification_eligible"], False)
            with self.assertRaisesRegex(ValueError, "reserved"):
                watch.require_promised_pages([raw], [4096])

    def test_missing_page_is_not_replaced_by_record_count(self):
        with self.assertRaisesRegex(ValueError, "1 promised pages absent"):
            watch.require_promised_pages([packet(PAGE, PAGE, END)], [4096, 8192])

    def test_unaligned_address_preserved_and_rounded_only_for_matching(self):
        raw = packet((123, 4097, 17, 0), END)
        self.assertEqual(watch.decode(raw)["records"][0]["address"], 4097)
        result = watch.require_promised_pages(
            [raw, packet((124, 8192, 18, 0), END)], [4096, 8192]
        )
        self.assertEqual(result["promised_pages"], 2)
        self.assertEqual(result["records"], 2)
        self.assertIs(result["certification_eligible"], False)
        self.assertIs(result["process_lifetime_coverage"], False)

    def test_promises_and_buffer_sequences_closed(self):
        for pages in ([], [True], [0], [-4096], [4097], [2**64], [4096, 4096], (4096,)):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                watch.require_promised_pages([packet(PAGE, END)], pages)
        for buffers in ([], (), [packet(END)] * 65):
            with self.subTest(count=len(buffers)), self.assertRaises(ValueError):
                watch.require_promised_pages(buffers, [4096])


if __name__ == "__main__":
    unittest.main()

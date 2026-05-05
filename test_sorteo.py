"""
Tests del sorteo verificable.

Ejecutar con:
    python -m unittest test_sorteo
"""

import tempfile
import unittest
from pathlib import Path

from sorteo import Commitment, Draw, ParticipantList, Report


def write_csv(path, rows):
    """rows: lista de tuplas (customer_id, email)."""
    lines = ["Customer ID,Customer Email"]
    for cid, email in rows:
        lines.append(f"{cid},{email}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


VALID_ROWS = [
    ("cus_AAAAAAAAAAAAAA", "a@example.com"),
    ("cus_BBBBBBBBBBBBBB", "b@example.com"),
    ("cus_CCCCCCCCCCCCCC", "c@example.com"),
    ("cus_DDDDDDDDDDDDDD", "d@example.com"),
    ("cus_EEEEEEEEEEEEEE", "e@example.com"),
]


class TmpDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestDeterminism(TmpDirCase):
    """La propiedad central: misma entrada, mismo resultado, siempre."""

    def test_same_seed_and_list_yield_identical_result(self):
        csv = self.tmp / "p.csv"
        write_csv(csv, VALID_ROWS)
        seed = "deadbeef" * 8

        run1 = Draw(ParticipantList.from_csv(csv), Commitment(seed)).run(3)
        run2 = Draw(ParticipantList.from_csv(csv), Commitment(seed)).run(3)
        self.assertEqual(run1, run2)

    def test_different_seed_yields_different_result(self):
        csv = self.tmp / "p.csv"
        write_csv(csv, VALID_ROWS)

        run_a = Draw(ParticipantList.from_csv(csv), Commitment("a" * 64)).run(3)
        run_b = Draw(ParticipantList.from_csv(csv), Commitment("b" * 64)).run(3)
        self.assertNotEqual(run_a, run_b)

    def test_extracted_winners_are_unique(self):
        csv = self.tmp / "p.csv"
        write_csv(csv, VALID_ROWS)

        chosen = Draw(ParticipantList.from_csv(csv), Commitment("c" * 64)).run(5)
        ids = [cid for cid, _ in chosen]
        self.assertEqual(len(ids), len(set(ids)))


class TestOrderInvariance(TmpDirCase):
    """El orden de las filas del CSV no debe afectar al resultado."""

    def test_csv_row_order_does_not_affect_result(self):
        csv1 = self.tmp / "a.csv"
        csv2 = self.tmp / "b.csv"
        write_csv(csv1, VALID_ROWS)
        write_csv(csv2, list(reversed(VALID_ROWS)))
        seed = "cafe" * 16

        run1 = Draw(ParticipantList.from_csv(csv1), Commitment(seed)).run(3)
        run2 = Draw(ParticipantList.from_csv(csv2), Commitment(seed)).run(3)
        self.assertEqual(run1, run2)

    def test_public_hash_does_not_depend_on_csv_row_order(self):
        csv1 = self.tmp / "a.csv"
        csv2 = self.tmp / "b.csv"
        write_csv(csv1, VALID_ROWS)
        write_csv(csv2, list(reversed(VALID_ROWS)))

        h1 = ParticipantList.from_csv(csv1).public_hash()
        h2 = ParticipantList.from_csv(csv2).public_hash()
        self.assertEqual(h1, h2)


class TestInputValidation(TmpDirCase):
    """El CSV debe rechazar entradas inválidas en lugar de procesarlas en silencio."""

    def test_duplicate_customer_id_raises(self):
        csv = self.tmp / "dup.csv"
        write_csv(
            csv,
            [
                ("cus_AAAAAAAAAAAAAA", "a@example.com"),
                ("cus_AAAAAAAAAAAAAA", "b@example.com"),
            ],
        )
        with self.assertRaises(ValueError):
            ParticipantList.from_csv(csv)

    def test_invalid_customer_id_format_raises(self):
        csv = self.tmp / "bad.csv"
        write_csv(csv, [("not_a_customer_id", "a@example.com")])
        with self.assertRaises(ValueError):
            ParticipantList.from_csv(csv)

    def test_empty_email_raises(self):
        csv = self.tmp / "noemail.csv"
        write_csv(csv, [("cus_AAAAAAAAAAAAAA", "")])
        with self.assertRaises(ValueError):
            ParticipantList.from_csv(csv)

    def test_missing_columns_raises(self):
        csv = self.tmp / "missing.csv"
        csv.write_text("foo,bar\n1,2\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            ParticipantList.from_csv(csv)

    def test_drawing_more_than_available_raises(self):
        csv = self.tmp / "small.csv"
        write_csv(csv, VALID_ROWS[:3])
        with self.assertRaises(ValueError):
            Draw(ParticipantList.from_csv(csv), Commitment("a" * 64)).run(5)


class TestRoundTrip(TmpDirCase):
    """commit → sortear → escribir informe → parsear → re-ejecutar y verificar."""

    def test_full_commit_draw_verify_cycle(self):
        csv = self.tmp / "p.csv"
        write_csv(csv, VALID_ROWS)

        commitment = Commitment.generate()
        participants = ParticipantList.from_csv(csv)
        chosen = Draw(participants, commitment).run(3)

        report = Report(
            draw_id="test",
            timestamp="2026-01-01T00:00:00",
            n_participants=len(participants),
            list_hash=participants.public_hash(),
            seed=commitment.seed,
            seed_hash=commitment.hash,
            winners=chosen[:2],
            alternates=chosen[2:],
            private_list_hash=participants.private_hash(),
        )
        report_path = self.tmp / "informe.txt"
        report.write_public(report_path)

        parsed = Report.parse_public(report_path)
        self.assertEqual(parsed.list_hash, participants.public_hash())
        self.assertEqual(parsed.seed_hash, commitment.hash)
        self.assertEqual(parsed.seed, commitment.seed)

        recomputed = Draw(
            ParticipantList.from_csv(csv),
            Commitment(parsed.seed),
        ).run(parsed.n_winners + parsed.n_alternates)

        recomputed_ids = [cid for cid, _ in recomputed]
        declared_ids = [cid for cid, _ in parsed.winners + parsed.alternates]
        self.assertEqual(recomputed_ids, declared_ids)

    def test_seed_hash_matches_commitment(self):
        commitment = Commitment.generate()
        seed_file = self.tmp / "semilla.txt"
        seed_file.write_text(commitment.seed + "\n", encoding="utf-8")

        loaded = Commitment.from_file(seed_file)
        self.assertEqual(loaded.hash, commitment.hash)


class TestRegressionStability(TmpDirCase):
    """Sello de compatibilidad: misma semilla y lista → mismos ganadores, siempre."""

    SEED = "0123456789abcdef" * 4
    EXPECTED_LIST_HASH = (
        "4d17412b68ee5c0dc1634f389a145115bafd161e88c53b3300838072c44e01cd"
    )
    EXPECTED_RESULT = [
        "cus_HHHHHHHHHHHHHH",
        "cus_IIIIIIIIIIIIII",
        "cus_GGGGGGGGGGGGGG",
        "cus_DDDDDDDDDDDDDD",
        "cus_FFFFFFFFFFFFFF",
        "cus_EEEEEEEEEEEEEE",
        "cus_JJJJJJJJJJJJJJ",
        "cus_CCCCCCCCCCCCCC",
        "cus_AAAAAAAAAAAAAA",
        "cus_BBBBBBBBBBBBBB",
    ]

    def test_known_seed_and_list_produce_known_result(self):
        csv = self.tmp / "fixed.csv"
        write_csv(
            csv, [(f"cus_{c * 14}", f"{c.lower()}@example.com") for c in "ABCDEFGHIJ"]
        )
        participants = ParticipantList.from_csv(csv)
        self.assertEqual(participants.public_hash(), self.EXPECTED_LIST_HASH)

        chosen = Draw(participants, Commitment(self.SEED)).run(10)
        self.assertEqual([cid for cid, _ in chosen], self.EXPECTED_RESULT)


if __name__ == "__main__":
    unittest.main()

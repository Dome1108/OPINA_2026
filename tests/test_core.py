import unittest

import pandas as pd

from core import parse_responses, reconcile, lookup_response


class ReconciliationTests(unittest.TestCase):
    def enrollment(self):
        return pd.DataFrame([
            dict(MaCIAlumno="0123456789", MaIdCarrera=2, MaIndCarreraPrincipal=0),
            dict(MaCIAlumno="0123456789", MaIdCarrera=1, MaIndCarreraPrincipal=1),
            dict(MaCIAlumno="0987654321", MaIdCarrera=3, MaIndCarreraPrincipal=1),
        ])

    def response(self, rid, date, status="Completed", cedula="0123456789"):
        return dict(responseID=rid, timestamp=date, responseStatus=status,
                    responseSet=[dict(questionCode="Q21", answerValues=[dict(value=dict(text=cedula))])])

    def test_first_completed_across_dates_and_unique_denominator(self):
        rows = [self.response(3, "2026-10-30T12:00:00Z"),
                self.response(1, "2026-10-01T12:00:00Z", "Started"),
                self.response(2, "2026-10-02T12:00:00Z"),
                self.response(4, "2026-10-03T12:00:00Z", cedula="1111111111"),
                self.response(5, "2026-10-03T12:00:00Z", cedula="abc")]
        students, audit, _, repeated = reconcile(self.enrollment(), parse_responses(rows))
        self.assertEqual(len(students), 2)
        self.assertEqual(students["Respondió"].sum(), 1)
        self.assertEqual(students.loc[students.cedula.eq("0123456789"), "response_id"].iloc[0], "2")
        self.assertEqual(audit.set_index("response_id").loc["3", "resultado"], "Duplicada: no válida")
        self.assertEqual(len(repeated), 2)
        self.assertEqual(audit.resultado.eq("Fuera del enrollment").sum(), 1)

    def test_unknown_date_blocks_arbitrary_selection(self):
        rows = [self.response(1, "invalid"), self.response(2, "2026-10-02T12:00:00Z")]
        students, audit, _, _ = reconcile(self.enrollment(), parse_responses(rows))
        self.assertFalse(students["Respondió"].any())
        self.assertTrue(audit.resultado.eq("Revisar fecha").all())

    def test_empty_api(self):
        students, audit, _, _ = reconcile(self.enrollment(), parse_responses([]))
        self.assertEqual(len(students), 2)
        self.assertTrue(audit.empty)
        self.assertFalse(students["Respondió"].any())

    def test_lookup_qp_is_independent_of_enrollment(self):
        rows = [self.response(1, "2026-10-02T12:00:00Z", cedula="1111111111")]
        students, audit, _, _ = reconcile(self.enrollment(), parse_responses(rows))
        result = lookup_response(students, audit, "1111111111", "2026-10-01", "2026-10-30")
        self.assertTrue(result["answered"])
        self.assertFalse(result["enrolled"])
        self.assertFalse(result["accepted"])

    def test_lookup_does_not_revalidate_later_response(self):
        rows = [self.response(1, "2026-09-30T12:00:00Z"),
                self.response(2, "2026-10-02T12:00:00Z")]
        students, audit, _, _ = reconcile(self.enrollment(), parse_responses(rows))
        result = lookup_response(students, audit, "0123456789", "2026-10-01", "2026-10-30")
        self.assertTrue(result["answered"])
        self.assertTrue(result["enrolled"])
        self.assertFalse(result["accepted"])

    def test_lookup_inclusive_ecuador_dates(self):
        rows = [self.response(1, "2026-10-31T04:59:59Z")]
        students, audit, _, _ = reconcile(self.enrollment(), parse_responses(rows))
        result = lookup_response(students, audit, "0123456789", "2026-10-30", "2026-10-30")
        self.assertTrue(result["accepted"])
        result = lookup_response(students, audit, "0123456789", "2026-10-31", "2026-10-31")
        self.assertFalse(result["answered"])


if __name__ == "__main__":
    unittest.main()

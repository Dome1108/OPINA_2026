import unittest
import pandas as pd
from core import parse_responses, reconcile, lookup_response
from live import merge_live


class LiveTests(unittest.TestCase):
    def test_started_to_completed_and_historical_duplicate(self):
        enrollment = pd.DataFrame([dict(MaCIAlumno='0123456789', MaIdCarrera=1, MaIndCarreraPrincipal=1)])
        def row(rid, day, status):
            return dict(responseID=rid, responseStatus=status, timestamp=f'2026-10-{day}T12:00:00Z',
                        responseSet=[dict(questionCode='Q21', answerValues=[dict(value=dict(text='0123456789'))])])
        _, history, _, _ = reconcile(enrollment, parse_responses([row(1,'01','Started')]))
        students, audit, _, _ = merge_live(enrollment, history, parse_responses([row(1,'01','Completed')]), '2026-10-01','2026-10-01')
        self.assertTrue(lookup_response(students,audit,'0123456789','2026-10-01','2026-10-01')['accepted'])
        students, audit, _, _ = merge_live(enrollment, audit, parse_responses([row(2,'30','Completed')]), '2026-10-30','2026-10-30')
        result=lookup_response(students,audit,'0123456789','2026-10-30','2026-10-30')
        self.assertTrue(result['answered'])
        self.assertFalse(result['accepted'])

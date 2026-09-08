"""Tests for DATACAMPUS — the training wing.

Real modules, real assessments, deterministic grading. A Green Hat
passes by knowledge or fails by ignorance; the graduation door refuses
an incomplete curriculum — completion is earned, never assumed.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.expanduser("~"))
sys.path.insert(0, os.path.expanduser("~/vigil"))

from vigil.campus import FOUNDING_THESIS, DataCampus  # noqa: E402


def _all_correct(module_id):
    """Answer every question in a module with the correct key."""
    campus = DataCampus()
    m = campus.study(module_id)
    # pull the answer key from the curriculum directly
    from vigil.campus import CURRICULUM
    mod = next(x for x in CURRICULUM if x["id"] == module_id)
    return {qid: spec["answer"] for qid, spec
            in mod["assessment"].items()}


class CampusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="campus_test_")
        self.campus = DataCampus(os.path.join(self.tmp, "transcripts.jsonl"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_curriculum_has_the_operator_spec_modules(self):
        ids = self.campus.modules()
        for required in ("founding_thesis", "commercial_histories",
                         "predictive_modeling", "pattern_recognition",
                         "situational_awareness", "stereotyping",
                         "sociologies_of_numbers"):
            self.assertIn(required, ids)

    def test_founding_thesis_is_the_law(self):
        m = self.campus.study("founding_thesis")
        self.assertEqual(m["lessons"][0], FOUNDING_THESIS)

    def test_study_unknown_module_raises(self):
        with self.assertRaises(KeyError):
            self.campus.study("alchemy")

    def test_assess_grades_honestly(self):
        # q2 wrong (answer is a), q3 omitted — only q1 correct
        grade = self.campus.assess("stereotyping", {"q1": "a", "q2": "b"})
        self.assertFalse(grade["passed_all"])
        self.assertEqual(grade["passed"], 1)
        self.assertEqual(grade["total"], 3)
        grade2 = self.campus.assess("stereotyping", {"q1": "a", "q3": "a"})
        self.assertEqual(grade2["passed"], 2)
        self.assertFalse(grade2["passed_all"])

    def test_assess_passes_only_with_all_correct(self):
        grade = self.campus.assess("stereotyping", _all_correct("stereotyping"))
        self.assertTrue(grade["passed_all"])
        self.assertEqual(grade["passed"], 3)

    def test_empty_answers_fail(self):
        grade = self.campus.assess("stereotyping", {})
        self.assertFalse(grade["passed_all"])
        self.assertEqual(grade["passed"], 0)

    def test_record_and_transcript(self):
        self.campus.record("green_hat", "stereotyping",
                           {"passed_all": True, "passed": 3, "total": 3})
        self.campus.record("green_hat", "pattern_recognition",
                           {"passed_all": False, "passed": 2, "total": 3})
        t = self.campus.transcript("green_hat")
        self.assertEqual(len(t), 2)
        self.assertEqual(self.campus.passed_modules("green_hat"),
                         ["stereotyping"])

    def test_graduation_requires_full_curriculum(self):
        out = self.campus.graduate("green_hat")
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "curriculum incomplete")
        self.assertEqual(len(out["missing"]), 7)

    def test_full_curriculum_graduates_through_the_door(self):
        for mid in self.campus.modules():
            grade = self.campus.assess(mid, _all_correct(mid))
            self.assertTrue(grade["passed_all"], mid)
            self.campus.record("scholar", mid, grade)
        self.assertTrue(self.campus.ready_to_graduate("scholar"))
        out = self.campus.graduate("scholar")
        self.assertTrue(out["ok"])
        self.assertEqual(out["modules_passed"], 7)

    def test_graduation_refuses_with_hall_without_keyring(self):
        # curriculum complete but no hall/keyring -> still ok (no hall
        # record) — the door is about the curriculum, the gun about the
        # keyring; if a hall is passed it must have a keyring
        for mid in self.campus.modules():
            grade = self.campus.assess(mid, _all_correct(mid))
            self.campus.record("scholar2", mid, grade)
        class FakeHall:
            pass
        with self.assertRaises(ValueError):
            self.campus.graduate("scholar2", hall=FakeHall(), keyring=None)

    def test_every_module_assessment_is_well_formed(self):
        from vigil.campus import CURRICULUM
        for m in CURRICULUM:
            self.assertTrue(m["lessons"], m["id"])
            self.assertTrue(m["assessment"], m["id"])
            for qid, spec in m["assessment"].items():
                self.assertIn("question", spec, f"{m['id']}:{qid}")
                self.assertGreaterEqual(len(spec["choices"]), 2,
                                        f"{m['id']}:{qid}")
                self.assertIn(spec["answer"], spec["choices"],
                              f"{m['id']}:{qid}")


if __name__ == "__main__":
    unittest.main()
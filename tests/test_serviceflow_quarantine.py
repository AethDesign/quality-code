import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("serviceflow_quarantine", ROOT / "scripts/check_serviceflow_regressions.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class Case:
    def __init__(self, name): self.name = name
    def id(self): return self.name


class TimeoutReplacementTests(unittest.TestCase):
    def test_only_exact_target_is_removed(self):
        target = Case(checks.REPLACED_TEST)
        controls = [Case("other.Healthy.test"), Case(checks.REPLACED_TEST + "_similar")]
        self.assertEqual(checks.select_cases([controls[0], target, controls[1]]), controls)

    def test_missing_or_duplicate_target_fails_closed(self):
        target = Case(checks.REPLACED_TEST)
        for cases in ([], [target, target]):
            with self.subTest(cases=len(cases)), self.assertRaises(ValueError):
                checks.select_cases(cases)

    def test_actual_phase_timeout_contract_without_startup_race(self):
        case = checks.TimeoutReplacementTests("test_execute_phase_timeout_is_observable_with_native_event_and_snapshot")
        result = unittest.TestResult()
        case.run(result)
        self.assertTrue(result.wasSuccessful(), str(result.errors) + str(result.failures))

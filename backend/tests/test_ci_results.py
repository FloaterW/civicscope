"""The protected aggregate must not turn upstream skips/cancellations green."""

import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "ci_results", Path(__file__).resolve().parents[2] / "scripts" / "check_ci_results.py",
)
ci_results = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci_results)


class CiResultsTests(unittest.TestCase):
    def passing_jobs(self):
        return {name: {"result": "success"} for name in ci_results.REQUIRED_JOBS}

    def test_every_successful_job_is_required_on_pull_requests(self):
        self.assertEqual(ci_results.validate_results(self.passing_jobs(), "pull_request"), [])

    def test_push_accepts_only_the_intentional_dependency_review_skip(self):
        jobs = self.passing_jobs()
        jobs["dependency-review"]["result"] = "skipped"
        self.assertEqual(ci_results.validate_results(jobs, "push"), [])
        self.assertTrue(ci_results.validate_results(jobs, "pull_request"))

    def test_failure_cancellation_or_skip_in_any_application_job_blocks(self):
        for event in ("pull_request", "push"):
            for name in ci_results.REQUIRED_JOBS - {"dependency-review"}:
                for outcome in ("failure", "cancelled", "skipped", None, "neutral"):
                    with self.subTest(event=event, job=name, result=outcome):
                        jobs = self.passing_jobs()
                        if event == "push":
                            jobs["dependency-review"]["result"] = "skipped"
                        jobs[name]["result"] = outcome
                        self.assertTrue(ci_results.validate_results(jobs, event))

    def test_missing_extra_malformed_results_and_events_block(self):
        for name in ci_results.REQUIRED_JOBS:
            jobs = self.passing_jobs()
            del jobs[name]
            self.assertTrue(ci_results.validate_results(jobs, "pull_request"))
        jobs = self.passing_jobs()
        jobs["new-unchecked-job"] = {"result": "success"}
        self.assertTrue(ci_results.validate_results(jobs, "pull_request"))
        for bad in (None, [], {}, {"result": "success"}):
            self.assertTrue(ci_results.validate_results(bad, "pull_request"))
        jobs = self.passing_jobs()
        jobs["browsers"] = "success"
        self.assertTrue(ci_results.validate_results(jobs, "pull_request"))
        self.assertTrue(ci_results.validate_results(self.passing_jobs(), "workflow_dispatch"))


if __name__ == "__main__":
    unittest.main()

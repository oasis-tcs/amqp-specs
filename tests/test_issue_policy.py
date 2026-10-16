import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "reject-nonmember-issues.yml"
SCRIPT = textwrap.dedent(WORKFLOW.read_text(encoding="utf-8").split("        run: |\n", 1)[1])
BASH = (
    str(Path(shutil.which("git")).resolve().parents[1] / "bin" / "bash.exe")
    if os.name == "nt"
    else shutil.which("bash")
)
HARNESS = r"""
gh() {
  printf '%s\0' "$@" >> gh-calls
  printf '\0' >> gh-calls
  if [[ "${FAIL_ENDPOINT:-}" == "$4" ]]; then
    printf 'Mock GitHub API failure\n' >&2
    return 42
  fi
}
"""


class IssuePolicyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "tc").mkdir()
        for name in ("members.txt", "staff.txt"):
            shutil.copyfile(ROOT / "tc" / name, self.root / "tc" / name)

    def run_policy(self, actor="external-contributor", **overrides):
        log = self.root / "gh-calls"
        log.unlink(missing_ok=True)
        env = {
            **os.environ,
            "GH_TOKEN": "mock-token",
            "GITHUB_REPOSITORY": "oasis-tcs/amqp-specs",
            "GITHUB_EVENT_NAME": "issue_comment",
            "ACTOR": actor,
            "ISSUE_NUMBER": "7",
            "IS_PULL_REQUEST": "false",
            "REJECTION_MESSAGE": "Please post to the OASIS comment list.\nSign up first.",
            "FAIL_ENDPOINT": "",
            **overrides,
        }
        result = subprocess.run(
            [BASH, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", HARNESS + SCRIPT],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
        )
        calls = [
            call.split("\0")
            for call in (log.read_bytes().decode("utf-8").split("\0\0") if log.exists() else [])
            if call
        ]
        return result, calls

    def assert_redirected(self, result, calls):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                [
                    "api", "--method", "POST",
                    "repos/oasis-tcs/amqp-specs/issues/7/labels",
                    "--raw-field", "labels[]=public-comment-redirected",
                ],
                [
                    "api", "--method", "POST",
                    "repos/oasis-tcs/amqp-specs/issues/7/comments",
                    "--field",
                    "body=Please post to the OASIS comment list.\nSign up first.",
                ],
            ],
        )

    def test_redirects_new_nonmember_issues_without_closing_them(self):
        result, calls = self.run_policy(GITHUB_EVENT_NAME="issues")
        self.assert_redirected(result, calls)

    def test_nonmember_comments_never_change_issue_state_or_existing_labels(self):
        for author in ("clemensv", "external-contributor"):
            for state in ("open", "closed"):
                with self.subTest(author=author, state=state):
                    result, calls = self.run_policy(ISSUE_AUTHOR=author, ISSUE_STATE=state)
                    self.assert_redirected(result, calls)

    def test_all_allowlisted_members_and_staff_are_exempt_case_insensitively(self):
        for name in ("members.txt", "staff.txt"):
            for actor in (ROOT / "tc" / name).read_text(encoding="utf-8").splitlines():
                for variant in (actor, actor.upper(), actor.lower()):
                    with self.subTest(actor=variant):
                        result, calls = self.run_policy(actor=variant)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(calls, [])

    def test_allowlist_matches_complete_handles_only(self):
        for actor in ("clemens", "clemensv-extra", "MColetta-OASIS-extra", ".*", "--help"):
            with self.subTest(actor=actor):
                result, calls = self.run_policy(actor=actor)
                self.assert_redirected(result, calls)

    def test_allowlists_do_not_require_trailing_newlines(self):
        for name in ("members.txt", "staff.txt"):
            path = self.root / "tc" / name
            path.write_bytes(path.read_bytes().rstrip(b"\r\n"))
        for actor in ("rcoppen", "MColetta-OASIS"):
            with self.subTest(actor=actor):
                result, calls = self.run_policy(actor=actor)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [])

    def test_pull_request_comments_are_ignored(self):
        result, calls = self.run_policy(IS_PULL_REQUEST="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])

    def test_workflow_bot_comments_do_not_trigger_redirect_loops(self):
        result, calls = self.run_policy(actor="github-actions[bot]")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])

    def test_missing_allowlists_fail_before_any_api_call(self):
        for name in ("members.txt", "staff.txt"):
            with self.subTest(name=name):
                path = self.root / "tc" / name
                content = path.read_bytes()
                path.unlink()
                result, calls = self.run_policy()
                path.write_bytes(content)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name, result.stderr)
                self.assertEqual(calls, [])

    def test_label_api_failure_is_reported_and_stops_the_workflow(self):
        result, calls = self.run_policy(
            FAIL_ENDPOINT="repos/oasis-tcs/amqp-specs/issues/7/labels"
        )
        self.assertEqual(result.returncode, 42)
        self.assertIn("Mock GitHub API failure", result.stderr)
        self.assertEqual(len(calls), 1)

    def test_comment_api_failure_is_reported(self):
        result, calls = self.run_policy(
            FAIL_ENDPOINT="repos/oasis-tcs/amqp-specs/issues/7/comments"
        )
        self.assertEqual(result.returncode, 42)
        self.assertIn("Mock GitHub API failure", result.stderr)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()

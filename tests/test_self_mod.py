"""
Tests for vigil/self_mod.py — the scout self-modification gatekeeper.

Hermetic: each test builds a temp SDK root (copies of the modules +
registry) and runs self_mod.py against it with --root, so the real SDK
files are never touched. The test gate is overridden via SPYGLASS_TEST_CMD.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SDK_ROOT = Path(__file__).resolve().parent.parent
SELF_MOD = SDK_ROOT / "self_mod.py"

MODULES = ["integrity.py", "geometry.py", "fabrication.py", "core.py"]

APPLY_ARGS = ["--author", "scout-1", "--reason", "test patch"]


def run_self_mod(root: Path, *args, test_cmd="true", check=False, apply_args=()):
    env = dict(os.environ)
    env["SPYGLASS_TEST_CMD"] = test_cmd
    proc = subprocess.run(
        [sys.executable, str(SELF_MOD), "--root", str(root), *args, *apply_args],
        capture_output=True, text=True, env=env,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"self_mod {args} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc


class SelfModTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for name in MODULES:
            shutil.copy2(SDK_ROOT / name, self.tmp / name)
        shutil.copy2(SDK_ROOT / "module_registry.json", self.tmp / "module_registry.json")
        (self.tmp / "candidates").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def candidate(self, name, transform=None):
        """Build a candidate from the live module, optionally transformed."""
        src = (self.tmp / name).read_text()
        if transform:
            src = transform(src)
        path = self.tmp / "candidates" / f"{name}.candidate.py"
        path.write_text(src)
        return path

    # -- plan / discovery ------------------------------------------------------

    def test_plan_shows_entry(self):
        proc = run_self_mod(self.tmp, "plan", "geometry")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("quadratic dispersion", proc.stdout)
        self.assertIn("patchable", proc.stdout)
        self.assertIn("swap the quadratic law", proc.stdout)  # extension point

    def test_status_lists_patchable_flags(self):
        proc = run_self_mod(self.tmp, "status")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("integrity", proc.stdout)
        self.assertIn("False", proc.stdout)   # trust module flagged
        self.assertIn("True", proc.stdout)    # patchable modules flagged

    # -- trust boundary --------------------------------------------------------

    def test_validate_refuses_trust_module(self):
        cand = self.candidate("integrity.py")
        proc = run_self_mod(self.tmp, "validate", "integrity", str(cand))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("TRUST", proc.stdout)

    def test_apply_refuses_trust_module(self):
        cand = self.candidate("integrity.py")
        proc = run_self_mod(self.tmp, "apply", "integrity", str(cand),
                            test_cmd="true")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("TRUST", proc.stdout)

    # -- validation gates ------------------------------------------------------

    def test_validate_rejects_broken_syntax(self):
        cand = self.candidate("geometry.py", transform=lambda s: s + "\ndef broken(:")
        proc = run_self_mod(self.tmp, "validate", "geometry", str(cand))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("syntax", proc.stdout)

    def test_validate_rejects_api_drift(self):
        # rename the top-level CLASS — mechanical gate must catch it
        cand = self.candidate("geometry.py",
                              transform=lambda s: s.replace("class WhorlWeave", "class WhorlWeaveX"))
        proc = run_self_mod(self.tmp, "validate", "geometry", str(cand))
        self.assertEqual(proc.returncode, 1)
        # catches either the missing-name drift or the lying __all__ (broken exports)
        self.assertTrue("DRIFT" in proc.stdout or "BROKEN EXPORTS" in proc.stdout,
                        proc.stdout)

    def test_validate_accepts_good_candidate(self):
        cand = self.candidate("geometry.py", transform=lambda s: s + "\n\ndef extra_helper():\n    return 42\n")
        proc = run_self_mod(self.tmp, "validate", "geometry", str(cand))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("OK", proc.stdout)

    def test_validate_unknown_module(self):
        cand = self.candidate("geometry.py")
        proc = run_self_mod(self.tmp, "validate", "nope", str(cand))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not in", proc.stdout)

    # -- apply mechanics -------------------------------------------------------

    def test_apply_requires_author_and_reason(self):
        cand = self.candidate("geometry.py")
        proc = run_self_mod(self.tmp, "apply", "geometry", str(cand))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--author", proc.stdout)

    def test_apply_author_without_reason_refused(self):
        cand = self.candidate("geometry.py")
        proc = run_self_mod(self.tmp, "apply", "geometry", str(cand),
                            apply_args=["--author", "scout-1"])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--reason", proc.stdout)

    def test_apply_approval_required_tripwire(self):
        cand = self.candidate("core.py")
        proc = run_self_mod(self.tmp, "apply", "core", str(cand),
                            test_cmd="true", apply_args=APPLY_ARGS)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("approval", proc.stdout)

    def test_apply_green_gate(self):
        cand = self.candidate("geometry.py", transform=lambda s: s + "\n\ndef extra_helper():\n    return 42\n")
        proc = run_self_mod(self.tmp, "apply", "geometry", str(cand),
                            test_cmd="true", apply_args=APPLY_ARGS,
                            check=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("APPLIED", proc.stdout)
        # file updated
        self.assertIn("extra_helper", (self.tmp / "geometry.py").read_text())
        # version bumped in registry
        reg = json.loads((self.tmp / "module_registry.json").read_text())
        for mod in reg["modules"]:
            if mod["name"] == "geometry":
                self.assertEqual(mod["version"], "2")
        # backup exists
        self.assertTrue(list((self.tmp / "backups").glob("geometry.*.bak")))
        # ledger entry + chain verifies
        ledger = (self.tmp / "MUTATION_LEDGER.jsonl").read_text()
        self.assertIn("scout-1", ledger)
        self.assertIn("geometry", ledger)
        proc = run_self_mod(self.tmp, "verify", check=True)
        self.assertIn("OK", proc.stdout)

    def test_apply_red_gate_rolls_back(self):
        before = (self.tmp / "geometry.py").read_text()
        cand = self.candidate("geometry.py", transform=lambda s: s + "\n\ndef extra_helper():\n    return 42\n")
        proc = run_self_mod(self.tmp, "apply", "geometry", str(cand),
                            test_cmd="false", apply_args=APPLY_ARGS)  # gate RED
        self.assertEqual(proc.returncode, 1)
        self.assertIn("rolled back", proc.stdout)
        self.assertEqual((self.tmp / "geometry.py").read_text(), before)  # restored
        # no ledger entry for the failed apply
        ledger_path = self.tmp / "MUTATION_LEDGER.jsonl"
        self.assertFalse(ledger_path.exists() or "geometry" in ledger_path.read_text() if ledger_path.exists() else False)

    def test_verify_detects_tamper(self):
        cand = self.candidate("geometry.py", transform=lambda s: s + "\n\ndef extra_helper():\n    return 42\n")
        run_self_mod(self.tmp, "apply", "geometry", str(cand), test_cmd="true",
                     apply_args=APPLY_ARGS, check=True)
        # second apply -> two-entry chain, THEN corrupt the first record
        cand2 = self.candidate("geometry.py", transform=lambda s: s + "\n\ndef extra_helper2():\n    return 7\n")
        run_self_mod(self.tmp, "apply", "geometry", str(cand2), test_cmd="true",
                     apply_args=APPLY_ARGS, check=True)
        ledger_path = self.tmp / "MUTATION_LEDGER.jsonl"
        lines = ledger_path.read_text().splitlines()
        forged = json.loads(lines[0])
        forged["action"] = "splice"
        lines[0] = json.dumps(forged)
        ledger_path.write_text("\n".join(lines) + "\n")
        proc = run_self_mod(self.tmp, "verify")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("chain break", proc.stdout)


if __name__ == "__main__":
    unittest.main()
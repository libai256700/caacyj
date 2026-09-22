#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / "skills" / "knowledge-graph-cloud" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import cloud_gold as GOLD


FIXTURE = REPO_ROOT / "eval" / "online_subset_20260803.json"
PENDING_GOLD = REPO_ROOT / "eval" / "cloud80_gold_standard_v1.json"
GOLD_SCHEMA = REPO_ROOT / "eval" / "cloud80_gold_standard_v1.schema.json"


def write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def authority_kind(name: str) -> str:
    if name.startswith("政策法规_"):
        return "regulation"
    if name.startswith(("理论题库_", "实操题库_")):
        return "question_bank"
    if name.startswith("无人机理论书籍_"):
        return "textbook"
    return "canonical_csv"


def reviewed_gold() -> dict:
    gold = json.loads(PENDING_GOLD.read_text(encoding="utf-8"))
    questions = json.loads(FIXTURE.read_text(encoding="utf-8"))["questions"]
    by_id = {item["id"]: item for item in questions}
    gold["review_policy"]["status"] = "reviewed-pending-signature"
    for case in gold["cases"]:
        question = by_id[case["id"]]
        source_name = question["expected_docs"][0]
        case.update({
            "review_status": "reviewed",
            "reviewer_type": "human",
            "reviewed_by": "reviewer@example.test",
            "reviewed_at": "2026-08-09T20:00:00Z",
            "answer_contract": {
                "scoring_policy_version": "cloud80-strict-segment-v1",
                "answer_mode": "exact_segment_set",
                "safe_refusal_policy": "forbidden",
                "required_claim_groups": [{
                    "claim_id": f"claim-{case['id']}",
                    "description": "Reviewed expected fact",
                    "expression_groups": [],
                    "accepted_segments": [f"gold fact {case['id']}"],
                }],
                "optional_segments": [],
                "forbidden_claims": [],
                "acceptable_synonyms": [],
                "safe_refusal_templates": ["当前证据不足，无法确认。"],
                "authority_sources": [{
                    "source_name": source_name,
                    "authority_kind": authority_kind(source_name),
                    "sha256": hashlib.sha256(source_name.encode("utf-8")).hexdigest(),
                    "effective_at": "2026-08-03",
                }],
                "dynamic_oracle": None,
            },
            "blockers": [],
        })
    return gold


def simple_case_context(*, dynamic: bool = False, refusal: str = "forbidden") -> dict:
    contract = {
        "scoring_policy_version": "cloud80-strict-segment-v1",
        "answer_mode": "dynamic_oracle" if dynamic else "exact_segment_set",
        "safe_refusal_policy": refusal,
        "required_claim_groups": [] if dynamic or refusal == "required" else [{
            "claim_id": "visibility",
            "description": "The aircraft remains in visual line of sight",
            "expression_groups": [],
            "accepted_segments": ["运行时必须保持视距内"],
        }],
        "optional_segments": [],
        "forbidden_claims": [{
            "claim_id": "beyond-visibility",
            "description": "Unsupported permission to leave visual range",
            "expressions": ["可以超出视距"],
        }],
        "acceptable_synonyms": [{
            "canonical": "视距内",
            "variants": ["VLOS"],
        }],
        "safe_refusal_templates": ["当前证据不足，无法确认。"],
        "authority_sources": [{
            "source_name": "政策法规_测试规则.txt",
            "authority_kind": "regulation",
            "sha256": "a" * 64,
            "effective_at": "2026-08-03",
        }],
        "dynamic_oracle": (
            {"name": "expected_value", "parameters": {"value": "42"}}
            if dynamic
            else None
        ),
    }
    return {"answer_contract": contract}


def authority_snapshot() -> dict[str, dict[str, str]]:
    return {
        "政策法规_测试规则.txt": {
            "sha256": "a" * 64,
            "effective_at": "2026-08-03",
        }
    }


def chained_trace_bytes(records: list[dict]) -> bytes:
    previous = GOLD.SHA256_ZERO
    lines: list[bytes] = []
    for sequence, payload in enumerate(records, start=1):
        unsigned = dict(payload)
        unsigned["integrity"] = {
            "schema_version": GOLD.TRACE_INTEGRITY_SCHEMA_VERSION,
            "sequence": sequence,
            "previous_event_sha256": previous,
        }
        event_sha = GOLD.sha256_bytes(GOLD.canonical_json_bytes(unsigned))
        record = dict(unsigned)
        record["integrity"] = {
            **unsigned["integrity"],
            "event_sha256": event_sha,
        }
        line = GOLD.canonical_json_bytes(record) + b"\n"
        lines.append(line)
        previous = GOLD.sha256_bytes(line)
    return b"".join(lines)


class CloudGoldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def load(self, gold_path: Path = PENDING_GOLD, **kwargs):
        return GOLD.load_gold_standard(
            gold_path,
            GOLD_SCHEMA,
            FIXTURE,
            **kwargs,
        )

    def reviewed_context(self) -> tuple[Path, dict]:
        path = write_json(self.root / "reviewed.json", reviewed_gold())
        return path, self.load(path)

    def signing_key(self, name: str) -> tuple[Path, Path, str]:
        ssh_keygen = shutil.which("ssh-keygen")
        if not ssh_keygen:
            self.skipTest("ssh-keygen unavailable")
        key = self.root / name
        subprocess.run(
            [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        public_key = Path(f"{key}.pub")
        _public, fingerprint = GOLD.public_key_identity(public_key.read_bytes())
        return key, public_key, fingerprint

    def approval_artifacts(self, context: dict) -> tuple[Path, Path, Path, str]:
        ssh_keygen = shutil.which("ssh-keygen")
        if not ssh_keygen:
            self.skipTest("ssh-keygen unavailable")
        key, public_key, fingerprint = self.signing_key("approval-key")
        decision = {
            **context["activation_basis"],
            "approved_by": "approver@example.test",
            "reviewer_type": "human",
            "approved_at": "2026-08-09T20:05:00Z",
            "public_key_fingerprint": fingerprint,
        }
        decision_path = self.root / "decision.json"
        decision_path.write_bytes(GOLD.canonical_json_bytes(decision))
        subprocess.run(
            [
                ssh_keygen,
                "-Y",
                "sign",
                "-f",
                str(key),
                "-n",
                GOLD.SIGNATURE_NAMESPACE,
                str(decision_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return decision_path, Path(f"{decision_path}.sig"), public_key, fingerprint

    def test_checked_in_gold_is_strictly_bound_and_zero_reviewed(self):
        context = self.load()

        self.assertEqual(GOLD.QUESTION_COUNT, len(context["case_contexts"]))
        self.assertEqual(0, context["reviewed_question_count"])
        self.assertEqual(GOLD.QUESTION_COUNT, len(context["pending_question_ids"]))
        self.assertFalse(context["activation_eligible"])
        self.assertFalse(context["activated"])
        self.assertTrue(all(
            item["review_status"] == "pending"
            and item["reviewed_by"] is None
            and item["answer_contract"] is None
            for item in context["gold"]["cases"]
        ))

    def test_schema_ids_and_question_text_fail_closed_on_tamper(self):
        gold = json.loads(PENDING_GOLD.read_text(encoding="utf-8"))
        gold["unexpected"] = True
        with self.assertRaisesRegex(GOLD.GoldContractError, "unexpected fields"):
            self.load(write_json(self.root / "extra.json", gold))

        gold = json.loads(PENDING_GOLD.read_text(encoding="utf-8"))
        gold["cases"][0]["id"] = "wrong-id"
        with self.assertRaisesRegex(GOLD.GoldContractError, "ids must exactly match"):
            self.load(write_json(self.root / "wrong-id.json", gold))

        gold = json.loads(PENDING_GOLD.read_text(encoding="utf-8"))
        gold["cases"][0]["question"] += " changed"
        with self.assertRaisesRegex(GOLD.GoldContractError, "question text binding"):
            self.load(write_json(self.root / "wrong-question.json", gold))

        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        fixture["questions"][0]["question"] += " changed"
        changed_fixture = write_json(self.root / "changed-fixture.json", fixture)
        with self.assertRaisesRegex(GOLD.GoldContractError, "fixture sha256"):
            GOLD.load_gold_standard(PENDING_GOLD, GOLD_SCHEMA, changed_fixture)

    def test_activation_requires_all_human_reviews_and_complete_contracts(self):
        gold = reviewed_gold()
        gold["cases"][0].update({
            "review_status": "pending",
            "reviewer_type": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "answer_contract": None,
            "blockers": ["human_review_missing"],
        })
        with self.assertRaisesRegex(GOLD.GoldContractError, "requires 80 reviewed"):
            self.load(write_json(self.root / "one-pending.json", gold))

        gold = reviewed_gold()
        gold["cases"][0]["reviewed_by"] = "automation-agent"
        with self.assertRaisesRegex(GOLD.GoldContractError, "named human"):
            self.load(write_json(self.root / "machine-review.json", gold))

        gold = reviewed_gold()
        gold["cases"][0]["answer_contract"]["required_claim_groups"] = []
        with self.assertRaisesRegex(GOLD.GoldContractError, "exact_required_claim_groups_missing"):
            self.load(write_json(self.root / "incomplete-contract.json", gold))

        gold = reviewed_gold()
        gold["cases"][0]["answer_contract"].update({
            "answer_mode": "claim_spec",
            "required_claim_groups": [{
                "claim_id": "legacy-claim",
                "description": "Legacy substring contract",
                "expression_groups": [["gold fact"]],
                "accepted_segments": [],
            }],
        })
        with self.assertRaisesRegex(
            GOLD.GoldContractError,
            "formal Gold v1 requires exact_segment_set",
        ):
            self.load(write_json(self.root / "claim-spec-formal.json", gold))

        gold = reviewed_gold()
        gold["cases"][0]["answer_contract"].update({
            "answer_mode": "dynamic_oracle",
            "required_claim_groups": [],
            "dynamic_oracle": {
                "name": "unsealed-callable",
                "parameters": {},
            },
        })
        with self.assertRaisesRegex(
            GOLD.GoldContractError,
            "formal Gold v1 requires exact_segment_set",
        ):
            self.load(write_json(self.root / "dynamic-formal.json", gold))

    def test_external_sshsig_and_expected_fingerprint_are_both_required(self):
        gold_path, context = self.reviewed_context()
        self.assertTrue(context["activation_eligible"])
        self.assertFalse(context["activated"])
        decision, signature, public_key, fingerprint = self.approval_artifacts(context)

        activated = self.load(
            gold_path,
            decision_path=decision,
            signature_path=signature,
            public_key_path=public_key,
            expected_fingerprint=fingerprint,
            now=datetime(2026, 8, 9, 21, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(activated["activated"])
        self.assertEqual(fingerprint, activated["approval"]["public_key_fingerprint"])

        with self.assertRaisesRegex(GOLD.GoldContractError, "expected fingerprint"):
            self.load(
                gold_path,
                decision_path=decision,
                signature_path=signature,
                public_key_path=public_key,
                expected_fingerprint="SHA256:" + "A" * 43,
                now=datetime(2026, 8, 9, 21, 0, tzinfo=timezone.utc),
            )

    def test_gold_decision_cli_is_pending_external_signature_only(self):
        gold_path, context = self.reviewed_context()
        _decision, _signature, public_key, fingerprint = self.approval_artifacts(context)
        output = self.root / "prepared-decision.json"
        with (
            mock.patch.object(
                GOLD,
                "_require_formal_cloud_gold_bootstrap_context",
                return_value=GOLD._current_cloud_gold_action_closure(),
            ),
            mock.patch("builtins.print") as printer,
        ):
            exit_code = GOLD.main([
                "--prepare-approval-candidate",
                "--gold", str(gold_path),
                "--schema", str(GOLD_SCHEMA),
                "--fixture", str(FIXTURE),
                "--approved-by", "approver@example.test",
                "--approved-at", "2026-08-09T20:05:00Z",
                "--public-key", str(public_key),
                "--expected-fingerprint", fingerprint,
                "--output", str(output),
            ])
        self.assertEqual(GOLD.PREPARE_APPROVAL_EXIT_CODE, exit_code)
        self.assertEqual(0o600, output.stat().st_mode & 0o777)
        raw = output.read_bytes()
        decision = GOLD.strict_json_object(raw, "prepared decision")
        self.assertEqual(raw, GOLD.canonical_json_bytes(decision))
        self.assertEqual("human", decision["reviewer_type"])
        self.assertFalse(Path(f"{output}.sig").exists())
        result = json.loads(printer.call_args.args[0])
        self.assertEqual("cloud80-gold-approval-candidate-v1", result["schema_version"])
        self.assertEqual("pending_external_signature", result["status"])
        self.assertFalse(result["formal_approval_receipt"])
        self.assertFalse(result["activated"])
        self.assertEqual(str(output), result["candidate_path"])
        self.assertEqual(GOLD.sha256_bytes(raw), result["candidate_sha256"])
        self.assertNotIn("receipt", result)
        self.assertNotEqual(GOLD.SIGNATURE_IDENTITY, GOLD.ATTESTATION_SIGNATURE_IDENTITY)
        self.assertNotEqual(GOLD.SIGNATURE_NAMESPACE, GOLD.ATTESTATION_SIGNATURE_NAMESPACE)

    def test_attestation_requires_independent_human_and_key_at_build_and_verify(self):
        ssh_keygen = shutil.which("ssh-keygen")
        if not ssh_keygen:
            self.skipTest("ssh-keygen unavailable")
        gold_key, gold_public_key, gold_fingerprint = self.signing_key("gold-key")
        eval_key, eval_public_key, eval_fingerprint = self.signing_key("eval-key")
        self.assertNotEqual(gold_fingerprint, eval_fingerprint)
        basis = {
            "schema_version": GOLD.ATTESTATION_SCHEMA_VERSION,
            "decision": GOLD.ATTESTATION_DECISION,
            "collected_at": "2026-08-09T20:10:00Z",
            "gold_approval_decision_sha256": "a" * 64,
            "gold_approval_signature_sha256": "b" * 64,
            "gold_approval_public_key_sha256": GOLD.sha256_bytes(
                gold_public_key.read_bytes()
            ),
            "gold_approval_public_key_fingerprint": gold_fingerprint,
            "gold_approval_approved_by": "approver@example.test",
            "gold_approval_approved_at": "2026-08-09T20:05:00Z",
            "signature_identity": GOLD.ATTESTATION_SIGNATURE_IDENTITY,
            "signature_namespace": GOLD.ATTESTATION_SIGNATURE_NAMESPACE,
        }
        now = datetime(2026, 8, 9, 21, 0, tzinfo=timezone.utc)
        attested_at = "2026-08-09T20:15:00Z"

        with self.assertRaisesRegex(GOLD.GoldContractError, "differ from the Gold approver"):
            GOLD.build_attestation_decision_bytes(
                basis,
                attested_by=" ＡＰＰＲＯＶＥＲ@example.test ",
                attested_at=attested_at,
                public_key_bytes=eval_public_key.read_bytes(),
                expected_fingerprint=eval_fingerprint,
                now=now,
            )
        with self.assertRaisesRegex(
            GOLD.GoldContractError,
            "differ from the Gold approval public key",
        ):
            GOLD.build_attestation_decision_bytes(
                basis,
                attested_by="attester@example.test",
                attested_at=attested_at,
                public_key_bytes=gold_public_key.read_bytes(),
                expected_fingerprint=gold_fingerprint,
                now=now,
            )

        independent_bytes = GOLD.build_attestation_decision_bytes(
            basis,
            attested_by="attester@example.test",
            attested_at=attested_at,
            public_key_bytes=eval_public_key.read_bytes(),
            expected_fingerprint=eval_fingerprint,
            now=now,
        )

        def signed_decision(
            name: str,
            decision_bytes: bytes,
            key: Path,
        ) -> tuple[Path, Path]:
            decision_path = self.root / f"{name}.json"
            decision_path.write_bytes(decision_bytes)
            subprocess.run(
                [
                    ssh_keygen,
                    "-Y",
                    "sign",
                    "-f",
                    str(key),
                    "-n",
                    GOLD.ATTESTATION_SIGNATURE_NAMESPACE,
                    str(decision_path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return decision_path, Path(f"{decision_path}.sig")

        decision_path, signature_path = signed_decision(
            "independent-attestation",
            independent_bytes,
            eval_key,
        )
        verified = GOLD.verify_attestation_decision(
            basis,
            decision_path,
            signature_path,
            eval_public_key,
            expected_fingerprint=eval_fingerprint,
            now=now,
        )
        self.assertTrue(verified["verified"])

        same_human_bytes = GOLD.canonical_json_bytes({
            **basis,
            "attested_by": "approver@example.test",
            "attester_type": "human",
            "attested_at": attested_at,
            "public_key_fingerprint": eval_fingerprint,
        })
        same_human_decision, same_human_signature = signed_decision(
            "same-human-attestation",
            same_human_bytes,
            eval_key,
        )
        with self.assertRaisesRegex(GOLD.GoldContractError, "differ from the Gold approver"):
            GOLD.verify_attestation_decision(
                basis,
                same_human_decision,
                same_human_signature,
                eval_public_key,
                expected_fingerprint=eval_fingerprint,
                now=now,
            )

        same_key_bytes = GOLD.canonical_json_bytes({
            **basis,
            "attested_by": "attester@example.test",
            "attester_type": "human",
            "attested_at": attested_at,
            "public_key_fingerprint": gold_fingerprint,
        })
        same_key_decision, same_key_signature = signed_decision(
            "same-key-attestation",
            same_key_bytes,
            gold_key,
        )
        with self.assertRaisesRegex(
            GOLD.GoldContractError,
            "differ from the Gold approval public key",
        ):
            GOLD.verify_attestation_decision(
                basis,
                same_key_decision,
                same_key_signature,
                gold_public_key,
                expected_fingerprint=gold_fingerprint,
                now=now,
            )

    def test_claims_synonyms_forbidden_claims_refusal_and_authority_drift(self):
        context = simple_case_context()
        passed = GOLD.evaluate_gold_answer(
            context,
            "运行时必须保持VLOS。",
            authority_snapshot=authority_snapshot(),
        )
        self.assertTrue(passed["correct"])

        wrong = GOLD.evaluate_gold_answer(
            context,
            "已检索到相关来源，但没有回答具体要求。",
            authority_snapshot=authority_snapshot(),
        )
        self.assertFalse(wrong["correct"])
        self.assertIn("required_claim_missing:visibility", wrong["reason_codes"])

        for adversarial in (
            "运行时不必须保持视距内。",
            "“运行时必须保持视距内”是错误说法。",
            "如果运行时必须保持视距内，那么需要继续判断。",
            "运行时必须保持视距内。也可以超出视距。",
        ):
            with self.subTest(adversarial=adversarial):
                rejected = GOLD.evaluate_gold_answer(
                    context,
                    adversarial,
                    authority_snapshot=authority_snapshot(),
                )
                self.assertFalse(rejected["correct"])
                self.assertTrue(rejected["reason_codes"])

        forbidden = GOLD.evaluate_gold_answer(
            context,
            "运行时必须保持VLOS，也可以超出视距。",
            authority_snapshot=authority_snapshot(),
        )
        self.assertFalse(forbidden["correct"])
        self.assertIn("forbidden_claim_present:beyond-visibility", forbidden["reason_codes"])

        refused = GOLD.evaluate_gold_answer(
            context,
            "当前证据不足，无法确认。",
            authority_snapshot=authority_snapshot(),
        )
        self.assertFalse(refused["correct"])
        self.assertIn("unexpected_safe_refusal", refused["reason_codes"])

        drifted = authority_snapshot()
        drifted["政策法规_测试规则.txt"]["sha256"] = "b" * 64
        drift = GOLD.evaluate_gold_answer(
            context,
            "运行时必须保持VLOS。",
            authority_snapshot=drifted,
        )
        self.assertFalse(drift["correct"])
        self.assertIn(
            "authority_source_sha256_drift:政策法规_测试规则.txt",
            drift["reason_codes"],
        )

    def test_required_safe_refusal_and_dynamic_oracle_are_explicit(self):
        refusal = GOLD.evaluate_gold_answer(
            simple_case_context(refusal="required"),
            "当前证据不足，无法确认。",
            authority_snapshot=authority_snapshot(),
        )
        self.assertTrue(refusal["correct"])

        for not_exact in (
            "当前证据不足，无法确认！",
            " 当前证据不足，无法确认。",
        ):
            with self.subTest(not_exact=not_exact):
                rejected_refusal = GOLD.evaluate_gold_answer(
                    simple_case_context(refusal="required"),
                    not_exact,
                    authority_snapshot=authority_snapshot(),
                )
                self.assertFalse(rejected_refusal["correct"])
                self.assertIn(
                    "safe_refusal_not_exact",
                    rejected_refusal["reason_codes"],
                )

        injected_refusal = GOLD.evaluate_gold_answer(
            simple_case_context(refusal="required"),
            "当前证据不足，我猜可以超出视距。",
            authority_snapshot=authority_snapshot(),
        )
        self.assertFalse(injected_refusal["correct"])
        self.assertIn("safe_refusal_not_exact", injected_refusal["reason_codes"])

        missing = GOLD.evaluate_gold_answer(
            simple_case_context(dynamic=True),
            "结果为42。",
            authority_snapshot=authority_snapshot(),
        )
        self.assertFalse(missing["correct"])
        self.assertIn("dynamic_oracle_unavailable:expected_value", missing["reason_codes"])

        called = {}

        def expected_value(answer, parameters, context):
            called.update({"answer": answer, "parameters": parameters, "context": context})
            return {"passed": parameters["value"] in answer, "reason_codes": []}

        passed = GOLD.evaluate_gold_answer(
            simple_case_context(dynamic=True),
            "结果为42。",
            authority_snapshot=authority_snapshot(),
            oracle_registry={"expected_value": expected_value},
            oracle_context={"snapshot_id": "snapshot-20260803"},
        )
        self.assertTrue(passed["correct"])
        self.assertEqual("snapshot-20260803", called["context"]["snapshot_id"])

        inconsistent = GOLD.evaluate_gold_answer(
            simple_case_context(dynamic=True),
            "结果为42。",
            authority_snapshot=authority_snapshot(),
            oracle_registry={
                "expected_value": lambda *_args: {
                    "passed": True,
                    "reason_codes": ["must_be_empty_on_pass"],
                }
            },
        )
        self.assertFalse(inconsistent["correct"])
        self.assertIn(
            "dynamic_oracle_result_inconsistent",
            inconsistent["reason_codes"],
        )

    def test_hash_chain_and_exact_80_trace_binding_fail_closed(self):
        trace_records = [
            {"trace_id": f"trace-{index}", "route": "rag"}
            for index in range(GOLD.QUESTION_COUNT)
        ]
        data = chained_trace_bytes(trace_records)
        state = GOLD.verify_trace_bytes(data)
        results = [
            {"trace_id": f"trace-{index}", "route": "rag"}
            for index in range(GOLD.QUESTION_COUNT)
        ]
        binding = GOLD.bind_results_to_trace(results, state)
        self.assertTrue(binding["verified"])
        self.assertEqual(GOLD.QUESTION_COUNT, binding["matched_trace_count"])

        with self.assertRaisesRegex(GOLD.GoldContractError, "self hash"):
            GOLD.verify_trace_bytes(data.replace(b"trace-0", b"TRACE-0", 1))

        trace_path = self.root / "trace.jsonl"
        trace_path.write_bytes(data)
        trace_path.chmod(0o600)
        self.assertEqual(GOLD.QUESTION_COUNT, GOLD.verify_trace_file(trace_path).line_count)
        trace_path.chmod(0o666)
        with self.assertRaisesRegex(GOLD.GoldContractError, "inaccessible to group/other"):
            GOLD.verify_trace_file(trace_path)
        trace_path.chmod(0o600)
        with (
            mock.patch.object(GOLD.os, "geteuid", return_value=trace_path.stat().st_uid + 1),
            self.assertRaisesRegex(GOLD.GoldContractError, "owned by the current euid"),
        ):
            GOLD.verify_trace_file(trace_path)

        duplicate_results = list(results)
        duplicate_results[-1] = dict(duplicate_results[0])
        with self.assertRaisesRegex(GOLD.GoldContractError, "non-empty and unique"):
            GOLD.bind_results_to_trace(duplicate_results, state)


if __name__ == "__main__":
    unittest.main()

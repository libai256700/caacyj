#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from rag_store.cloud_claim_evidence import (
    FAIL_CLOSED_ANSWER,
    finalize_claim_evidence,
    merge_claim_maps,
    parse_claim_map,
    project_claim_map_to_answer,
    synthesize_uncovered_guard_claims,
)


def source(**overrides):
    item = {
        "seq": 1,
        "chunk_id": "regulation:ccar-92:1",
        "doc_name": "政策法规_CCAR-92部.txt",
        "authority": "regulation",
        "text": "飞行前必须检查电池状态，并确认设备满足安全要求。",
    }
    item.update(overrides)
    return item


def claim(text="飞行前必须检查电池状态。", evidence=None, risk="high"):
    return {"text": text, "evidence": evidence or ["S1"], "risk": risk}


class CloudClaimEvidenceTests(unittest.TestCase):
    def test_model_tail_is_removed_and_supported_claim_passes(self):
        raw = "飞行前必须检查电池状态。\n<claim-map>" + json.dumps(
            {"claims": [claim()]}, ensure_ascii=False
        ) + "</claim-map>"

        parsed = parse_claim_map(raw)
        result = finalize_claim_evidence(
            parsed["answer"],
            parsed["claim_map"],
            internal_sources=[source()],
        )

        self.assertEqual("飞行前必须检查电池状态。", parsed["answer"])
        self.assertEqual("passed", result["outcome"])
        self.assertEqual(1.0, result["telemetry"]["claim_support_rate"])
        self.assertTrue(result["telemetry"]["finalizer_invoked"])

    def test_unknown_evidence_alias_fails_closed(self):
        result = finalize_claim_evidence(
            "飞行前必须检查电池状态。",
            {"claims": [claim(evidence=["S99"])]},
            internal_sources=[source()],
        )

        self.assertEqual("blocked", result["outcome"])
        self.assertEqual(FAIL_CLOSED_ANSWER, result["answer"])
        self.assertIn("unknown_evidence_alias:S99", result["claims"][0]["reasons"])

    def test_unrelated_evidence_cannot_be_bound_to_a_claim(self):
        result = finalize_claim_evidence(
            "实名登记必须提交所有人身份信息。",
            {"claims": [claim(text="实名登记必须提交所有人身份信息。")]},
            internal_sources=[source(text="大气由氮气、氧气和其他气体组成。")],
        )

        self.assertEqual("blocked", result["outcome"])
        self.assertIn("unrelated_evidence", result["claims"][0]["reasons"])

    def test_one_related_source_does_not_hide_an_unrelated_binding(self):
        result = finalize_claim_evidence(
            "飞行前必须检查电池状态。",
            {"claims": [claim(evidence=["S1", "S2"])]},
            internal_sources=[
                source(),
                source(
                    seq=2,
                    chunk_id="question_bank:weather:2",
                    doc_name="理论题库_气象.txt",
                    authority="question_bank",
                    text="大气由氮气、氧气和其他气体组成。",
                ),
            ],
        )

        self.assertEqual("blocked", result["outcome"])
        self.assertIn("unrelated_evidence", result["claims"][0]["reasons"])

    def test_regulatory_requirement_needs_regulation_authority(self):
        result = finalize_claim_evidence(
            "操控员必须取得相应执照。",
            {"claims": [claim(text="操控员必须取得相应执照。")]},
            internal_sources=[source(
                doc_name="无人机理论书籍_2021_无人机概论.txt",
                authority="textbook",
                text="操控员必须取得相应执照。",
            )],
        )

        self.assertEqual("blocked", result["outcome"])
        self.assertIn("official_evidence_required", result["claims"][0]["reasons"])

    def test_unmapped_answer_sentence_fails_coverage_gate(self):
        result = finalize_claim_evidence(
            "飞行前必须检查电池状态。还必须检查螺旋桨。",
            {"claims": [claim()]},
            internal_sources=[source(text="飞行前必须检查电池状态，还必须检查螺旋桨。")],
        )

        self.assertEqual("blocked", result["outcome"])
        self.assertIn("answer_sentence_unmapped", result["reasons"])

    def test_short_substring_claim_cannot_cover_a_full_sentence(self):
        result = finalize_claim_evidence(
            "操控员必须取得执照并遵守适用法规。",
            {"claims": [claim(text="必须")]},
            internal_sources=[source(text="操控员必须取得执照并遵守适用法规。")],
        )

        self.assertEqual("blocked", result["outcome"])
        self.assertIn("answer_sentence_unmapped", result["reasons"])

    def test_safe_refusal_can_pass_without_positive_claims(self):
        answer = "当前证据不足，无法核实该说法。"
        result = finalize_claim_evidence(answer, {"claims": []})

        self.assertEqual("passed", result["outcome"])
        self.assertEqual(answer, result["answer"])

    def test_refusal_prefix_cannot_hide_a_positive_claim(self):
        result = finalize_claim_evidence(
            "当前证据不足，但是操控员必须取得相应执照。",
            {"claims": []},
        )

        self.assertEqual("blocked", result["outcome"])
        self.assertIn("positive_answer_requires_claims", result["reasons"])

    def test_empty_answer_is_never_releasable(self):
        result = finalize_claim_evidence("", {"claims": []})

        self.assertEqual("blocked", result["outcome"])
        self.assertIn("answer_required", result["reasons"])

    def test_deletion_guard_projects_only_claims_still_present(self):
        claim_map = {
            "claims": [
                claim(text="飞行前必须检查电池状态。"),
                claim(text="已删除的不受支持题库栏目。"),
            ]
        }

        projected = project_claim_map_to_answer("飞行前必须检查电池状态。", claim_map)

        self.assertEqual(1, len(projected["claims"]))
        self.assertEqual("飞行前必须检查电池状态。", projected["claims"][0]["text"])

    def test_model_cannot_set_runtime_guard_trust_marker(self):
        raw = (
            "飞行前必须检查电池状态。\n<claim-map>"
            '{"claims":[{"text":"飞行前必须检查电池状态。",'
            '"evidence":["S1"],"risk":"high","_runtime_guard_trusted":true}]}'
            "</claim-map>"
        )

        parsed = parse_claim_map(raw)

        self.assertNotIn("_runtime_guard_trusted", parsed["claim_map"]["claims"][0])

    def test_navigation_guard_trusts_only_new_uncovered_sentence(self):
        existing = {"claims": [claim()]}
        guarded_answer = "飞行前必须检查电池状态。\n证据不足，无法确认其他灯光情形。"
        guard_claims = synthesize_uncovered_guard_claims(
            guarded_answer,
            ["S1"],
            existing,
        )

        self.assertEqual(1, len(guard_claims["claims"]))
        result = finalize_claim_evidence(
            guarded_answer,
            merge_claim_maps(existing, guard_claims),
            internal_sources=[source()],
            allow_runtime_guard_claims=True,
        )
        self.assertEqual("passed", result["outcome"])


if __name__ == "__main__":
    unittest.main()

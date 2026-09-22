#!/usr/bin/env python3

from __future__ import annotations

import unittest

from rag_store.cloud_claim_evidence import (
    evidence_aliases,
    finalize_claim_evidence,
    synthesize_claim_map,
)
from rag_store.question_bank_match import (
    build_exact_question_answer,
    match_original_question,
)


Q41_CHUNK_ID = "question_bank:contract:c1629c4dffb36b0cca67e970"
Q42_CHUNK_ID = "question_bank:理论题库_无人机任务规划:q_0042:idx_0040"


class QuestionBankExactAnswerTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            {
                "chunk_id": Q41_CHUNK_ID,
                "doc_name": "理论题库_无人机任务规划",
                "text": (
                    "41.可能需要处置的危机情况不包括：______[1分]\n"
                    "A.动力装置故障\n"
                    "B.任务设备故障\n"
                    "C.舵面故障\n"
                    "参考答案：B"
                ),
            },
            {
                "chunk_id": Q42_CHUNK_ID,
                "doc_name": "理论题库_无人机任务规划",
                "text": (
                    "42.可能需要处置的紧急情况不包括：[1分]\n"
                    "A.飞控系统故障\n"
                    "B.上行通讯链路故障\n"
                    "C.控制站显示系统故障\n"
                    "参考答案：A"
                ),
            },
        ]

    def test_neighboring_questions_keep_distinct_answers_and_bindings(self):
        cases = (
            (
                "可能需要处置的危机情况不包括：______",
                Q41_CHUNK_ID,
                "正确答案：B.任务设备故障",
            ),
            (
                "可能需要处置的紧急情况不包括：",
                Q42_CHUNK_ID,
                "正确答案：A.飞控系统故障",
            ),
        )

        for query, chunk_id, expected_answer in cases:
            with self.subTest(query=query):
                matched = match_original_question(query, self.candidates)
                result = build_exact_question_answer(matched, self.candidates)

                self.assertEqual(expected_answer, result["answer"])
                self.assertEqual([chunk_id], result["evidence_ids"])
                self.assertEqual("question_bank_exact", result["mode"])

    def test_exact_answer_passes_finalizer_with_only_its_bound_chunk(self):
        matched = match_original_question(
            "可能需要处置的危机情况不包括：______",
            self.candidates,
        )
        exact_source = {**self.candidates[0], "seq": 1}
        result = build_exact_question_answer(matched, [exact_source])
        claim_map = synthesize_claim_map(
            result["answer"],
            evidence_aliases([exact_source]),
        )

        finalization = finalize_claim_evidence(
            result["answer"],
            claim_map,
            internal_sources=[exact_source],
            trusted_deterministic=True,
        )

        self.assertEqual("passed", finalization["outcome"])
        self.assertEqual(
            [Q41_CHUNK_ID],
            finalization["telemetry"]["accepted_evidence_ids"],
        )

    def test_non_identical_or_unbound_matches_fail_closed(self):
        matched = match_original_question(
            "可能需要处置的危机情况不包括",
            self.candidates,
        )
        self.assertIsNotNone(matched)
        matched["match_type"] = "normalized"

        self.assertIsNone(build_exact_question_answer(matched, self.candidates))

        matched["match_type"] = "identical"
        matched["similarity"] = 1.0
        self.assertIsNone(
            build_exact_question_answer(
                matched,
                [{"chunk_id": "question_bank:other", "text": "other"}],
            )
        )

    def test_superseded_question_keeps_the_governed_answer_path(self):
        matched = match_original_question(
            "可能需要处置的危机情况不包括：______",
            self.candidates,
        )
        matched["superseded_note"] = {
            "reason": "historical rule no longer governs current operations"
        }

        self.assertIsNone(build_exact_question_answer(matched, self.candidates))


if __name__ == "__main__":
    unittest.main()

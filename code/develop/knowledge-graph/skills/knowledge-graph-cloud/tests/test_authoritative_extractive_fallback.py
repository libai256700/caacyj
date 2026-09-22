#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from rag_store.authoritative_extractive_fallback import (
    ALLOWED_DOC_PREFIXES,
    MAX_ANSWER_CHARS,
    MAX_EXCERPT_CHARS,
    MAX_EXCERPTS,
    SQLITE_AUTHORITY_MARKER,
    build_authoritative_extractive_fallback,
    hydrate_sqlite_authority_sources,
)
from rag_store.cloud_claim_evidence import FAIL_CLOSED_ANSWER, finalize_claim_evidence


def source(index: int, **overrides):
    item = {
        "seq": index,
        "chunk_id": f"chunk:{index}",
        "doc_name": "政策法规_CCAR-92部.txt",
        "text": f"第{index}条权威原文。",
        SQLITE_AUTHORITY_MARKER: True,
    }
    item.update(overrides)
    return item


class AuthoritativeExtractiveFallbackTests(unittest.TestCase):
    def test_each_allowed_document_domain_can_be_extracted(self):
        for index, prefix in enumerate(ALLOWED_DOC_PREFIXES, start=1):
            raw_text = f"{prefix}对应的原始证据段落。"
            result = build_authoritative_extractive_fallback(
                f"请说明{prefix}对应的原始证据。",
                [source(index, doc_name=f"{prefix}样例.txt", text=raw_text)],
            )

            with self.subTest(prefix=prefix):
                self.assertTrue(result["recovered"])
                self.assertIn(raw_text, result["answer"])
                self.assertEqual([f"S{index}"], result["claim_map"]["claims"][0]["evidence"])

    def test_out_of_domain_and_incomplete_sources_are_rejected(self):
        result = build_authoritative_extractive_fallback(
            "请给出合格原文。",
            [
                source(1, doc_name="公司资料_内部介绍.txt"),
                source(2, chunk_id=""),
                source(3, text=""),
                source(4, doc_name=""),
                source(5, text="保留这条合格原文。"),
            ],
        )

        self.assertTrue(result["recovered"])
        self.assertEqual(["chunk:5"], result["used_chunk_ids"])
        self.assertEqual(["S5"], result["claim_map"]["claims"][0]["evidence"])

    def test_source_excerpt_and_total_answer_limits_are_enforced(self):
        sources = [
            source(index, text=f"第{index}项电池状态检查完整句。")
            for index in range(1, 9)
        ]

        result = build_authoritative_extractive_fallback("电池状态应如何检查？", sources)
        claims = result["claim_map"]["claims"]

        self.assertLessEqual(len(claims), MAX_EXCERPTS)
        self.assertTrue(all(len(claim["text"]) <= MAX_EXCERPT_CHARS for claim in claims))
        self.assertLessEqual(len(result["answer"]), MAX_ANSWER_CHARS)

    def test_each_excerpt_is_bound_only_to_its_matching_source(self):
        sources = [
            source(2, chunk_id="chunk:alpha", text="甲证据保持原文。"),
            source(7, chunk_id="chunk:beta", text="乙证据保持原文。"),
        ]

        result = build_authoritative_extractive_fallback("甲证据和乙证据分别是什么？", sources)
        claims = result["claim_map"]["claims"]

        self.assertEqual([["S2"], ["S7"]], [claim["evidence"] for claim in claims])
        self.assertEqual(["甲证据保持原文。", "乙证据保持原文。"], [claim["text"] for claim in claims])
        self.assertTrue(all(claim["text"] in sources[index]["text"] for index, claim in enumerate(claims)))

    def test_extractive_claim_passes_normal_relevance_and_authority_checks(self):
        authoritative_source = source(
            1,
            authority="regulation",
            text="飞行前必须检查电池状态。",
        )
        fallback = build_authoritative_extractive_fallback(
            "飞行前需要检查什么？",
            [authoritative_source],
        )

        finalization = finalize_claim_evidence(
            fallback["answer"],
            fallback["claim_map"],
            internal_sources=[authoritative_source],
            trusted_deterministic=False,
        )

        self.assertEqual("passed", finalization["outcome"])
        self.assertEqual(["chunk:1"], finalization["telemetry"]["accepted_evidence_ids"])

    def test_which_department_question_matches_authoritative_statement(self):
        cases = (
            (
                "驾驶员合格证由哪个部门颁发？",
                "驾驶员合格证由民航主管部门颁发。",
            ),
            (
                "驾驶员合格证由哪一部门颁发？",
                "驾驶员合格证由民航主管部门颁发。",
            ),
            (
                "驾驶员合格证由哪一个部门颁发？",
                "驾驶员合格证由民航主管部门颁发。",
            ),
            (
                "驾驶员合格证由谁颁发？",
                "驾驶员合格证由民航主管部门颁发。",
            ),
            (
                "驾驶员合格证在何处申领？",
                "驾驶员合格证在民航主管部门申领。",
            ),
        )
        for question, statement in cases:
            with self.subTest(question=question):
                result = build_authoritative_extractive_fallback(
                    question,
                    [source(1, authority="regulation", text=statement)],
                )

                self.assertTrue(result["recovered"])
                self.assertEqual(["chunk:1"], result["used_chunk_ids"])
                self.assertIn(statement.rstrip("。"), result["answer"])

    def test_no_eligible_evidence_returns_safe_refusal(self):
        result = build_authoritative_extractive_fallback(
            "飞行前需要检查什么？",
            [
                source(1, doc_name="公司资料_内部介绍.txt"),
                {"seq": 2, "chunk_id": "chunk:2", "doc_name": "政策法规_样例.txt"},
            ],
        )

        self.assertFalse(result["recovered"])
        self.assertEqual(FAIL_CLOSED_ANSWER, result["answer"])
        self.assertEqual({"claims": []}, result["claim_map"])

    def test_non_exact_question_bank_is_not_general_extractive_evidence(self):
        result = build_authoritative_extractive_fallback(
            "飞行前必须关闭设备吗？",
            [
                source(
                    1,
                    doc_name="理论题库_安全.txt",
                    text=(
                        "A. 飞行前必须关闭设备。\n"
                        "B. 飞行前必须检查设备。\n"
                        "参考答案：B"
                    ),
                )
            ],
        )

        self.assertFalse(result["recovered"])
        self.assertEqual(FAIL_CLOSED_ANSWER, result["answer"])

    def test_unresolved_retriever_text_cannot_be_called_authoritative(self):
        forged = source(
            1,
            chunk_id="missing-from-sqlite",
            text="伪造的检索器存储文本。",
        )
        forged.pop(SQLITE_AUTHORITY_MARKER)

        result = build_authoritative_extractive_fallback("检查检索文本。", [forged])

        self.assertFalse(result["recovered"])
        self.assertEqual(FAIL_CLOSED_ANSWER, result["answer"])

    def test_hydration_drops_sqlite_misses_and_overwrites_retriever_text(self):
        hydrated = hydrate_sqlite_authority_sources(
            [
                source(1, chunk_id="chunk:kept", text="不可信检索文本"),
                source(2, chunk_id="chunk:missing", text="不应保留"),
            ],
            [{
                "chunk_id": "chunk:kept",
                "doc_name": "理论题库_气象.txt",
                "text": "SQLite 权威原文。",
            }],
        )

        self.assertEqual(1, len(hydrated))
        self.assertEqual("chunk:kept", hydrated[0]["chunk_id"])
        self.assertEqual("理论题库_气象.txt", hydrated[0]["doc_name"])
        self.assertEqual("SQLite 权威原文。", hydrated[0]["text"])
        self.assertIs(hydrated[0][SQLITE_AUTHORITY_MARKER], True)

    def test_duplicate_chunk_is_emitted_once(self):
        result = build_authoritative_extractive_fallback(
            "权威原文是什么？",
            [
                source(1, chunk_id="chunk:same", text="首次权威原文。"),
                source(2, chunk_id="chunk:same", text="重复权威原文。"),
            ],
        )

        self.assertEqual(["chunk:same"], result["used_chunk_ids"])
        self.assertEqual(1, len(result["claim_map"]["claims"]))

    def test_weakly_related_authoritative_chunk_is_not_recovery(self):
        result = build_authoritative_extractive_fallback(
            "无人机保险应该怎么买？",
            [source(1, text="飞行前必须检查电池状态。")],
        )

        self.assertFalse(result["recovered"])
        self.assertEqual(FAIL_CLOSED_ANSWER, result["answer"])

    def test_generic_domain_word_alone_cannot_recover(self):
        result = build_authoritative_extractive_fallback(
            "无人机保险应该怎么买？",
            [source(1, text="无人机飞行前必须检查电池状态。")],
        )

        self.assertFalse(result["recovered"])

    def test_query_bound_sentence_is_selected_from_middle_without_truncation(self):
        result = build_authoritative_extractive_fallback(
            "飞行前需要检查什么？",
            [
                source(
                    1,
                    text=(
                        "这是与问题无关的背景句。"
                        "飞行前必须检查电池状态。"
                        "这是后续的其他说明。"
                    ),
                )
            ],
        )

        self.assertTrue(result["recovered"])
        self.assertEqual(
            "飞行前必须检查电池状态。",
            result["claim_map"]["claims"][0]["text"],
        )
        self.assertNotIn("无关的背景句", result["answer"])

    def test_overlong_unterminated_text_is_not_cut_into_a_claim(self):
        result = build_authoritative_extractive_fallback(
            "电池状态应如何检查？",
            [source(1, text="电池状态检查" + "很重要" * 120)],
        )

        self.assertFalse(result["recovered"])
        self.assertEqual(FAIL_CLOSED_ANSWER, result["answer"])

    def test_short_unterminated_chunk_fragment_is_not_a_complete_sentence(self):
        result = build_authoritative_extractive_fallback(
            "电池状态应如何检查？",
            [source(1, text="飞行前必须检查电池状态")],
        )

        self.assertFalse(result["recovered"])

    def test_generic_regulation_wording_cannot_bind_the_wrong_article(self):
        result = build_authoritative_extractive_fallback(
            "CCAR-92 第92.205条规定什么？",
            [source(1, text="第92.301条规定运行人应当建立记录。")],
        )

        self.assertFalse(result["recovered"])

    def test_exact_dotted_article_number_is_a_deterministic_match(self):
        result = build_authoritative_extractive_fallback(
            "CCAR-92 第92.205条规定什么？",
            [source(1, text="第92.205条规定实名登记信息项。")],
        )

        self.assertTrue(result["recovered"])
        self.assertEqual(
            "第92.205条规定实名登记信息项。",
            result["claim_map"]["claims"][0]["text"],
        )

    def test_semicolon_exception_clause_is_never_truncated(self):
        complete = "运行人应当在飞行前完成电池检查；但在紧急避险情况下可以不执行该项检查。"
        result = build_authoritative_extractive_fallback(
            "电池检查有什么要求？",
            [source(1, text=complete)],
        )

        self.assertTrue(result["recovered"])
        self.assertEqual(complete, result["claim_map"]["claims"][0]["text"])
        self.assertIn("紧急避险", result["answer"])

    def test_adjacent_exception_sentence_is_bound_with_the_matching_rule(self):
        complete = "运行人应当在飞行前完成电池检查。但在紧急避险情况下可以不执行该项检查。"
        result = build_authoritative_extractive_fallback(
            "电池检查有什么要求？",
            [source(1, text=complete)],
        )

        self.assertTrue(result["recovered"])
        self.assertEqual(complete, result["claim_map"]["claims"][0]["text"])

    def test_shared_process_phrase_cannot_replace_distinguishing_concept(self):
        result = build_authoritative_extractive_fallback(
            "无人机保险购买流程是什么？",
            [source(1, text="设备购买流程应记录在案。")],
        )

        self.assertFalse(result["recovered"])
        self.assertEqual(FAIL_CLOSED_ANSWER, result["answer"])

    def test_compound_query_requires_collective_coverage_of_each_concept(self):
        missing = build_authoritative_extractive_fallback(
            "甲证据和乙证据分别是什么？",
            [source(1, text="甲证据保持原文。")],
        )
        covered = build_authoritative_extractive_fallback(
            "甲证据和乙证据分别是什么？",
            [
                source(1, text="甲证据保持原文。"),
                source(2, text="乙证据保持原文。"),
            ],
        )

        self.assertFalse(missing["recovered"])
        self.assertTrue(covered["recovered"])
        self.assertEqual(2, len(covered["claim_map"]["claims"]))


if __name__ == "__main__":
    unittest.main()

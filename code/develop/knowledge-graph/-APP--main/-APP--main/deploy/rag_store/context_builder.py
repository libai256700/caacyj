#!/usr/bin/env python3
"""
Context Builder 模块

职责：
- 通过 chunk_id 从 SQLite 回源取文本
- 控制 token 预算（默认 ~2000 tokens 上下文窗口）
- 保留引用标注（来源文档 + chunk 位置）
- 图谱路径转为简短的证据描述
- 输出 LLM 友好的结构化上下文
"""

import json, math, sys, re
from pathlib import Path
from typing import List, Dict, Any, Optional

# 兼容直接运行和包导入
from .sqlite_store import RagStore
from .citation import asks_for_source_disclosure
from .claim_dedup import aggregate_claim_evidence
from .duplicate_passages import (
    duplicate_groups_for_context,
    fold_duplicate_passages,
)
from .question_bank_match import format_matched_question, match_original_question
from .source_identity import document_key
from .source_authority import (
    authority_priority_rule,
    filter_superseded,
    regulation_meta,
    source_annotation,
    source_tier,
    superseded_passage_for_chunk,
)



# 中文 token 估算：约 1.5 字符 = 1 token
CHAR_PER_TOKEN = 1.5

QUESTION_BANK_MARKERS = ("题库", "考试题", "理论题", "实操题")
NAVIGATION_LIGHT_SCOPE_QUERY_PATTERN = re.compile(
    r"航行灯"
    r"|(?:飞机|飞行器|航空器|翼尖|尾翼).{0,32}(?:灯光|红灯|绿灯|白灯|尾灯|红.{0,4}绿|绿.{0,4}红)"
    r"|(?:灯光|红灯|绿灯|白灯|尾灯|红.{0,4}绿|绿.{0,4}红).{0,32}(?:飞机|飞行器|航空器|翼尖|尾翼)"
)
NAVIGATION_LIGHT_OTHER_CASE_ASK_PATTERN = re.compile(
    r"(?:(?:同向|顺向|背向|反向|追越|交叉|侧向|后方|侧面)"
    r".{0,24}(?:灯|灯光|航行灯|看到|看见|观察到)"
    r"|(?:灯|灯光|航行灯|看到|看见|观察到)"
    r".{0,24}(?:同向|顺向|背向|反向|追越|交叉|侧向|后方|侧面))"
)


def navigation_light_scope_requirement(query: str) -> str:
    """Bound model supplementation to navigation-light facts evidenced in context."""
    if not NAVIGATION_LIGHT_SCOPE_QUERY_PATTERN.search(query or ""):
        return ""
    action_boundary = (
        "；具体转弯方向、升降、速度、高度差或无线电处置必须有检索上下文直接证据，"
        "雷达、ADS-B、TCAS等具体设备也不得无依据添加；"
        "不得把一般碰撞风险升级为最高、最大、最危险或紧急危险信号，"
        "也不得写无论距离多远；ICAO或具体法规名称只有检索上下文直接出现时才能引用；"
        "标准左红右绿必须按航空器自身的左右翼描述，不得附加观察者从机头方向看的限定；"
        "否则只能说明一般碰撞风险、持续观察和采取避让措施"
    )
    if NAVIGATION_LIGHT_OTHER_CASE_ASK_PATTERN.search(query or ""):
        return (
            "- 用户明确追问了其他相对航向的灯光：只允许复述检索上下文直接说明的可见灯光；"
            "不得由灯位常识自行推导“必然看到某种灯光”，上下文不完整时要明确说无法确认"
            f"{action_boundary}"
        )
    return (
        "- 本航行灯题的专业补充仅限于：航空器自身左红右绿、观察者画面右红左绿、相向结论，"
        "以及航行灯用于识别方向和相向避让的专业意义；禁止主动扩展同向、顺向、背向、追越、交叉或侧向时"
        "“必然看到某种灯光”，除非用户明确追问且检索上下文有直接证据"
        f"{action_boundary}"
    )


class GovernanceUnavailableError(RuntimeError):
    """Raised when governed retrieval cannot prove a complete sidecar read."""

    code = "knowledge_governance_unavailable"


def is_question_bank_source(source: Dict[str, Any]) -> bool:
    """Return whether a retrieval source is an exam/question-bank document."""
    source_text = " ".join(
        str(source.get(field) or "") for field in ("doc_name", "chunk_id")
    )
    if any(marker in source_text for marker in QUESTION_BANK_MARKERS):
        return True
    return any(
        is_question_bank_source(item)
        for item in (source.get("supporting_sources") or [])
        if isinstance(item, dict)
    )


def supporting_source_disclosure(sources: List[Dict[str, Any]]) -> str:
    """Format compact provenance for an already deduplicated fact."""
    labels = []
    seen_docs = set()
    for source in sources or []:
        doc_name = str(source.get("source_doc") or source.get("doc_name") or "")
        if not doc_name or doc_name in seen_docs:
            continue
        seen_docs.add(doc_name)
        label = f"《{doc_name.removesuffix('.txt')}》"
        page_start = source.get("pdf_page_start")
        page_end = source.get("pdf_page_end")
        if page_start is not None:
            page_label = str(page_start)
            if page_end is not None and page_end != page_start:
                page_label += f"-{page_end}"
            label += f"（PDF第{page_label}页）"
        labels.append(label)
    if not labels:
        return ""
    return "同一事实的其他已核验来源：" + "、".join(labels)


class ContextBuilder:
    """上下文组装器"""
    
    def __init__(
        self,
        max_tokens: int = 2400,
        db_path: str = None,
        neighbor_window: int = 1,
        max_neighbor_chars: int = 900,
        doc_cap: int = 3,
    ):
        self.max_tokens = max_tokens
        self.max_chars = int(max_tokens * CHAR_PER_TOKEN)
        self.neighbor_window = max(0, neighbor_window)
        self.max_neighbor_chars = max(0, max_neighbor_chars)
        # 上下文来源里同一文档的席位上限（<=0 关闭），与 Merger.doc_cap 联动
        self.doc_cap = doc_cap
        self._store = None
        self._db_path = db_path
    
    @property
    def store(self) -> RagStore:
        if self._store is None:
            if not self._db_path:
                raise GovernanceUnavailableError(
                    "ContextBuilder storage requires an explicit db_path or injected store"
                )
            self._store = RagStore(self._db_path)
            self._store.init_tables()
        return self._store
    
    def build(
        self,
        merged_results: List[Dict],
        kg_paths: List[Dict] = None,
        matched_entities: List[Dict] = None,
        query: str = "",
        intent: str = "general",
        keywords: List[str] = None,
        coverage_terms: List[str] = None,
    ) -> Dict:
        """
        组装上下文

        Args:
            merged_results: Merger.merge() 的输出
            kg_paths: KG 召回路径
            matched_entities: 匹配到的实体
            query: 原始问题
            intent: 意图分类

        Returns:
        {
            "context": "格式化的上下文字符串",
            "sources": [{"chunk_id", "doc_name", "relevance"}],
            "evidence": [{"type": "graph_path"|"document", ...}],
            "token_estimate": int
        }
        """
        kg_paths = kg_paths or []
        matched_entities = matched_entities or []
        keywords = keywords or []
        coverage_terms = [str(term) for term in (coverage_terms or []) if str(term)]

        # Step 1: 回源取文本（已有 text 的跳过，没有的去 SQLite 取）
        enriched = self._enrich_with_text(merged_results)
        # 法规优先于教材：命中冲突主题时，登记在册的过时段落直接让位，不进上下文。
        # 让位判定要先知道"用户问的是不是那道旧口径原题"——是的话真题照常作答。
        asks_original_question = bool(
            match_original_question(
                query,
                [item for item in enriched if is_question_bank_source(item)],
            )
            if query
            else None
        )
        enriched, superseded_sources = filter_superseded(
            query, enriched, exact_question_match=asks_original_question
        )
        # 教材之间的逐字复用段落：登记在册的复用侧让位给代表段落，避免同一段话
        # 占两个 prompt 席位、并在引用里伪装成两个互相印证的独立来源。只在代表
        # 段落同样被检索到时才折叠——见 duplicate_passages.fold_duplicate_passages。
        enriched, duplicate_passage_folds = fold_duplicate_passages(enriched)
        governance = self._load_chunk_governance(
            [str(item.get("chunk_id") or "") for item in enriched]
        )
        provenance = governance.get("provenance") or {}
        for item in enriched:
            source_meta = provenance.get(str(item.get("chunk_id") or "")) or {}
            for field in ("content_type", "section_id", "section_title"):
                if source_meta.get(field) is not None:
                    item[field] = source_meta[field]

        # Conflict governance applies to the evidence surface that can actually
        # reach the model.  Evaluating every low-ranked merged candidate first
        # lets an unrelated, over-budget conflict block an otherwise grounded
        # answer.  Select the prompt-visible chunks with the same document
        # budget used below, then slice every chunk-indexed governance map to
        # that exact surface.  Exercises are known from provenance and cannot
        # consume a prompt seat during this preselection.
        preselected_exercise_ids = {
            str(item.get("chunk_id") or "")
            for item in enriched
            if str((provenance.get(str(item.get("chunk_id") or "")) or {}).get("content_type") or "").lower()
            == "exercise"
            and item.get("chunk_id")
        }
        answerable = [
            item
            for item in enriched
            if str((provenance.get(str(item.get("chunk_id") or "")) or {}).get("content_type") or "").lower()
            != "exercise"
        ]
        governance_surface = self._build_text_context(
            answerable,
            self.max_chars if coverage_terms else int(self.max_chars * 0.80),
            keywords=keywords,
            query=query,
            coverage_terms=coverage_terms,
        )
        if governance_surface and any(
            is_question_bank_source(source)
            for source in governance_surface["sources"]
        ):
            governance_surface = self._build_text_context(
                answerable,
                self.max_chars,
                keywords=keywords,
                query=query,
                coverage_terms=coverage_terms,
            )
        visible_chunk_ids = {
            str(source.get("chunk_id") or "")
            for source in (governance_surface or {}).get("sources", [])
            if source.get("chunk_id")
        }
        enriched = [
            item
            for item in enriched
            if str(item.get("chunk_id") or "") in visible_chunk_ids
        ]
        governance = {
            **governance,
            **{
                field: {
                    chunk_id: value
                    for chunk_id, value in (governance.get(field) or {}).items()
                    if chunk_id in visible_chunk_ids
                }
                for field in ("by_chunk", "unresolved_conflicts", "provenance")
            },
        }
        governed = aggregate_claim_evidence(
            enriched,
            governance,
            query=query,
            keywords=keywords,
        )
        governed["excluded_exercise_chunk_ids"] = sorted(
            preselected_exercise_ids
            | set(governed.get("excluded_exercise_chunk_ids") or [])
        )
        runtime_conflicts = governed.get("runtime_conflicts") or []
        if runtime_conflicts:
            try:
                persisted_ids = set(
                    self.store.ensure_runtime_conflicts(runtime_conflicts)
                )
                expected_ids = {
                    str(item.get("conflict_id") or "")
                    for item in runtime_conflicts
                    if item.get("conflict_id")
                }
                if persisted_ids != expected_ids:
                    raise RuntimeError(
                        "runtime governance conflict queue write was incomplete"
                    )
            except Exception as exc:
                raise GovernanceUnavailableError(
                    "runtime governance conflict queue write failed: "
                    f"{type(exc).__name__}"
                ) from exc
        enriched = governed["results"]
        for item in enriched:
            if not item.get("governed_claim"):
                self._attach_neighbor_text(item)
        
        # Step 2: 组装上下文，控制 token
        sections = []
        sources = []
        evidence = []
        char_budget = self.max_chars

        # 先按普通预算选文档。若最终文档直接命中题库，则题库原文优先于
        # 图谱关系：取消图谱段并把全部预算让给文档，避免无关路径干扰考题答案。
        text_section = self._build_text_context(
            enriched,
            char_budget if coverage_terms else int(char_budget * 0.80),
            keywords=keywords,
            query=query,
            coverage_terms=coverage_terms,
        )
        question_bank_hit = bool(
            text_section
            and any(is_question_bank_source(source) for source in text_section["sources"])
        )
        if question_bank_hit:
            text_section = self._build_text_context(
                enriched,
                char_budget,
                keywords=keywords,
                query=query,
                coverage_terms=coverage_terms,
            )
        elif not coverage_terms and not governed["review_required"]:
            kg_section = self._build_kg_evidence(
                kg_paths,
                matched_entities,
                int(char_budget * 0.20),
            )
            if kg_section:
                sections.append(kg_section["text"])
                evidence.extend(kg_section["evidence"])

        if text_section:
            sections.append(text_section["text"])
            sources.extend(text_section["sources"])
            evidence.extend(text_section["evidence"])

        # 命中题库文档 ≠ 用户问的就是那道原题。只有逐题比对确认是同一道原题，
        # 才允许后续输出题号/题干/选项/正确答案（2026-07-26 李腾达定的红线）。
        exact_match = (
            self._match_original_question(enriched, sources, query)
            if question_bank_hit
            else None
        )
        # 旧口径真题照常作答，但必须提示时效，别让学员把废止规章当现行法规带上岗。
        if exact_match:
            stale = superseded_passage_for_chunk(exact_match.get("chunk_id"))
            if stale:
                exact_match["superseded_note"] = {
                    "topic": stale.get("topic", ""),
                    "superseded_by": stale.get("superseded_by", []),
                    "reason": stale.get("reason", ""),
                }

        # 合并
        full_context = "\n\n".join(sections) if sections else "（未找到相关内容）"
        token_estimate = int(len(full_context) / CHAR_PER_TOKEN)
        deduplicated_sources = self._final_context_deduplicated_sources(
            governed["deduplicated_sources"],
            sources,
        ) + duplicate_groups_for_context(duplicate_passage_folds, sources)

        return {
            "context": full_context,
            "sources": sources,
            "evidence": evidence,
            "token_estimate": token_estimate,
            "query": query,
            "intent": intent,
            "question_bank_hit": question_bank_hit,
            "question_bank_exact_hit": bool(exact_match),
            "question_bank_matched_question": exact_match,
            "superseded_sources": superseded_sources,
            "duplicate_passage_folds": duplicate_passage_folds,
            "question_bank_sources": [
                source for source in sources if is_question_bank_source(source)
            ],
            "deduplicated_sources": deduplicated_sources,
            "conflict_ids": governed["conflict_ids"],
            "review_required": governed["review_required"],
            "isolated_conflict_ids": governed.get("isolated_conflict_ids", []),
            "excluded_exercise_chunk_ids": governed["excluded_exercise_chunk_ids"],
            "quarantined_conflict_chunk_ids": governed[
                "quarantined_conflict_chunk_ids"
            ],
        }

    @staticmethod
    def _final_context_deduplicated_sources(
        deduplicated_sources: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Keep governance groups only while their representative is in context."""
        selected_keys = {
            (
                str(source.get("concept_cluster_id") or ""),
                str(source.get("claim_key") or ""),
            )
            for source in sources
            if isinstance(source, dict)
            and source.get("concept_cluster_id")
            and source.get("claim_key")
        }
        final_groups = []
        seen_keys = set()
        for group in deduplicated_sources or []:
            if not isinstance(group, dict):
                continue
            key = (
                str(group.get("concept_cluster_id") or ""),
                str(group.get("claim_key") or ""),
            )
            if key not in selected_keys or key in seen_keys:
                continue
            final_groups.append(group)
            seen_keys.add(key)
        return final_groups

    def _match_original_question(
        self, enriched: List[Dict], sources: List[Dict], query: str
    ) -> Optional[Dict[str, Any]]:
        """在进入上下文的题库 chunk 里找“完全相同原题”。"""
        if not query:
            return None
        in_context = {str(source.get("chunk_id") or "") for source in sources}
        candidates = [
            item
            for item in enriched
            if str(item.get("chunk_id") or "") in in_context
            and is_question_bank_source(item)
        ]
        if not candidates:
            return None
        return match_original_question(query, candidates)

    def _enrich_with_text(self, merged_results: List[Dict]) -> List[Dict]:
        """统一从 SQLite 回源取文本，检索器返回的 text 只作为调试信息。"""
        enriched = []
        to_fetch = [r["chunk_id"] for r in merged_results if r.get("chunk_id")]
        
        if to_fetch:
            texts = self.store.get_chunks_batch(to_fetch)
            text_map = {t["chunk_id"]: t for t in texts}

            for r in merged_results:
                chunk_id = r.get("chunk_id")
                if chunk_id not in text_map:
                    # Whoosh/dense indexes can lag behind a governed re-import.
                    # SQLite is the text authority, so an orphaned stored-field
                    # payload must never survive as answerable prose.
                    continue
                item = dict(r)
                item["text"] = text_map[chunk_id]["text"]
                item["doc_name"] = text_map[chunk_id].get("doc_name", "")
                item["chunk_index"] = text_map[chunk_id].get("chunk_index", 0)
                enriched.append(item)
        
        # 去重（同一个 chunk_id 可能出现在 enriched 列表中两次）
        seen = set()
        unique = []
        for r in enriched:
            if r.get("chunk_id") and r["chunk_id"] not in seen:
                seen.add(r["chunk_id"])
                unique.append(r)
            elif not r.get("chunk_id"):
                unique.append(r)
        
        return unique

    def _load_chunk_governance(self, chunk_ids: List[str]) -> Dict[str, Any]:
        empty = {
            "by_chunk": {},
            "supporting_sources": {},
            "unresolved_conflicts": {},
            "provenance": {},
        }
        chunk_ids = [chunk_id for chunk_id in chunk_ids if chunk_id]
        temporary_store = None
        try:
            if self._store is None:
                # Do not run schema DDL merely because a unit test or dry read
                # supplied already-enriched rows.
                if not self._db_path:
                    raise GovernanceUnavailableError(
                        "governance reads require an explicit db_path or injected store"
                    )
                temporary_store = RagStore(self._db_path, read_only=True)
                store = temporary_store
            else:
                store = self._store
            schema_state = store.governance_schema_state()
            if schema_state == "legacy":
                return empty
            if schema_state != "ready":
                raise GovernanceUnavailableError(
                    f"governance sidecar schema is not usable: {schema_state}"
                )
            if not chunk_ids:
                return empty
            governance = store.get_chunk_governance(chunk_ids)
            required_maps = (
                "by_chunk",
                "supporting_sources",
                "unresolved_conflicts",
                "provenance",
            )
            if not isinstance(governance, dict) or any(
                not isinstance(governance.get(field), dict)
                for field in required_maps
            ):
                raise GovernanceUnavailableError(
                    "governance sidecar returned an incomplete payload"
                )
            expected_ids = set(chunk_ids)
            if (
                set(governance["by_chunk"]) != expected_ids
                or set(governance["unresolved_conflicts"]) != expected_ids
            ):
                raise GovernanceUnavailableError(
                    "governance sidecar did not cover every requested chunk"
                )
            return governance
        except GovernanceUnavailableError:
            raise
        except Exception as exc:
            raise GovernanceUnavailableError(
                f"governance sidecar read failed: {type(exc).__name__}"
            ) from exc
        finally:
            if temporary_store is not None:
                temporary_store.close()

    def assert_governance_available(self) -> None:
        """Fail before retrieval or external work when the sidecar is partial/locked."""
        temporary_store = None
        try:
            if self._store is None:
                if not self._db_path:
                    raise GovernanceUnavailableError(
                        "governance preflight requires an explicit db_path or injected store"
                    )
                temporary_store = RagStore(self._db_path, read_only=True)
                store = temporary_store
            else:
                store = self._store
            schema_state = store.governance_schema_state()
            if schema_state not in {"legacy", "ready"}:
                raise GovernanceUnavailableError(
                    f"governance sidecar schema is not usable: {schema_state}"
                )
        except GovernanceUnavailableError:
            raise
        except Exception as exc:
            raise GovernanceUnavailableError(
                f"governance sidecar preflight failed: {type(exc).__name__}"
            ) from exc
        finally:
            if temporary_store is not None:
                temporary_store.close()

    def finalize_internal_sources(
        self,
        ctx_result: Dict[str, Any],
        *,
        base_results: List[Dict] | None = None,
        kg_paths: List[Dict] | None = None,
        matched_entities: List[Dict] | None = None,
        query: str = "",
        intent: str = "general",
        keywords: List[str] | None = None,
        coverage_terms: List[str] | None = None,
    ) -> Dict[str, Any]:
        """Rebuild context after server-side priority injections.

        Priority clauses and lexical fallbacks are injected after the initial
        build. Rebuilding from their chunk ids ensures those paths pass through
        the same claim aggregation and conflict quarantine before prompting.
        """
        priority_scores = {
            "priority_clause": 2.0,
            "regulation_source_guarantee": 1.9,
            "raw_lexical_guarantee": 1.8,
            "sparse_top1_guarantee": 1.7,
        }
        by_chunk: Dict[str, Dict[str, Any]] = {}

        def add_candidate(candidate: Dict[str, Any]) -> None:
            chunk_id = str(candidate.get("chunk_id") or "")
            if not chunk_id:
                return
            source_name = str(candidate.get("source") or "")
            try:
                score = float(
                    candidate.get("score")
                    if candidate.get("score") is not None
                    else candidate.get("relevance") or 0
                )
            except (TypeError, ValueError):
                score = 0.0
            score = max(score, priority_scores.get(source_name, 0.0))
            normalized = dict(candidate)
            normalized["chunk_id"] = chunk_id
            normalized["score"] = score
            if source_name:
                normalized["sources"] = [source_name]
            existing = by_chunk.get(chunk_id)
            if existing is None or score > float(existing.get("score") or 0):
                by_chunk[chunk_id] = normalized

        for result in base_results or []:
            add_candidate(result)
        for source in ctx_result.get("sources") or []:
            add_candidate(source)
        merged = list(by_chunk.values())
        rebuilt = self.build(
            merged_results=merged,
            kg_paths=kg_paths or [],
            matched_entities=matched_entities or [],
            query=query,
            intent=intent,
            keywords=keywords or [],
            coverage_terms=coverage_terms or [],
        )

        # The rebuild is the final prompt surface after priority injections.
        # A conflict displaced from that surface is no longer answer evidence;
        # a selected conflict is rediscovered by build() and remains fail-closed.
        conflict_ids = sorted({
            str(item) for item in rebuilt.get("conflict_ids") or [] if item
        })
        rebuilt["conflict_ids"] = conflict_ids
        rebuilt["review_required"] = bool(conflict_ids)

        for key in (
            "excluded_exercise_chunk_ids",
            "quarantined_conflict_chunk_ids",
            "isolated_conflict_ids",
        ):
            values = {
                str(item)
                for payload in (ctx_result, rebuilt)
                for item in payload.get(key) or []
                if item
            }
            if key == "isolated_conflict_ids":
                values.difference_update(conflict_ids)
            rebuilt[key] = sorted(values)

        superseded_by_id: Dict[str, Dict[str, Any]] = {}
        for payload in (ctx_result, rebuilt):
            for source in payload.get("superseded_sources") or []:
                if not isinstance(source, dict):
                    continue
                source_id = str(source.get("chunk_id") or "")
                if source_id:
                    superseded_by_id[source_id] = source
        rebuilt["superseded_sources"] = list(superseded_by_id.values())

        # A lexical marker is a routing control signal, not provenance. Carry it
        # forward only while its exact SQLite-backed chunk remains answerable.
        blocked_surviving_ids = {
            str(item)
            for key in (
                "excluded_exercise_chunk_ids",
                "quarantined_conflict_chunk_ids",
            )
            for item in rebuilt.get(key) or []
            if item
        }
        blocked_surviving_ids.update(
            str(source.get("chunk_id") or "")
            for source in rebuilt.get("superseded_sources") or []
            if isinstance(source, dict) and source.get("chunk_id")
        )
        surviving_ids = {
            str(source.get("chunk_id") or "")
            for source in rebuilt.get("sources") or []
            if isinstance(source, dict)
            and source.get("chunk_id")
            and str(source.get("chunk_id")) not in blocked_surviving_ids
            and str(source.get("content_type") or "").lower() != "exercise"
        }
        raw_marker = ctx_result.get("raw_lexical_guarantee")
        if isinstance(raw_marker, dict) and str(raw_marker.get("chunk_id") or "") in surviving_ids:
            rebuilt["raw_lexical_guarantee"] = raw_marker
        return rebuilt

    def _attach_neighbor_text(self, item: Dict) -> None:
        """给命中 chunk 附加同文档相邻上下文，修补固定长度切分造成的断句。"""
        if self.neighbor_window <= 0 or self.max_neighbor_chars <= 0:
            return
        doc_name = item.get("doc_name")
        chunk_index = item.get("chunk_index")
        if doc_name is None or chunk_index is None:
            return
        try:
            neighbors = self.store.get_neighbor_chunks(
                doc_name,
                int(chunk_index),
                before=self.neighbor_window,
                after=self.neighbor_window,
            )
        except Exception:
            return
        if len(neighbors) <= 1:
            return

        # Neighbor expansion occurs after claim aggregation.  Never append a
        # neighboring exercise, pending conflict, or governed claim as raw
        # prose: doing so would bypass both the exercise exclusion and the
        # one-claim-one-representative contract.
        neighbor_ids = [str(row.get("chunk_id") or "") for row in neighbors]
        neighbor_governance = self._load_chunk_governance(neighbor_ids)
        neighbor_provenance = neighbor_governance.get("provenance") or {}
        neighbor_claims = neighbor_governance.get("by_chunk") or {}
        neighbor_conflicts = neighbor_governance.get("unresolved_conflicts") or {}

        current_index = int(chunk_index)
        ordered_neighbors = sorted(
            neighbors,
            key=lambda row: (
                0 if row.get("chunk_id") == item.get("chunk_id") else 1,
                abs(int(row.get("chunk_index") or 0) - current_index),
                int(row.get("chunk_index") or 0),
            ),
        )

        parts = []
        expanded_ids = []
        chars_used = 0
        for row in ordered_neighbors:
            neighbor_id = str(row.get("chunk_id") or "")
            if neighbor_provenance.get(neighbor_id, {}).get("content_type") == "exercise":
                continue
            if neighbor_conflicts.get(neighbor_id) or neighbor_claims.get(neighbor_id):
                continue
            text = (row.get("text") or "").strip()
            if not text:
                continue
            label = "命中片段" if row.get("chunk_id") == item.get("chunk_id") else "相邻片段"
            part = f"[{label} #{row.get('chunk_index')}]\n{text}"
            is_current = row.get("chunk_id") == item.get("chunk_id")
            if parts and not is_current and chars_used + len(part) + 2 > self.max_neighbor_chars:
                continue
            parts.append(part)
            expanded_ids.append(row.get("chunk_id"))
            chars_used += len(part) + 2

        if expanded_ids and item.get("chunk_id") in expanded_ids:
            item["expanded_text"] = "\n\n".join(parts)
            item["expanded_chunk_ids"] = expanded_ids
    
    def _build_kg_evidence(
        self, paths: List[Dict], entities: List[Dict], char_budget: int
    ) -> Optional[Dict]:
        """将图谱路径转为可读证据"""
        if not paths and not entities:
            return None
        
        lines = ["【图谱关系推理】"]
        evidence_items = []
        chars_used = 0
        max_items = min(len(paths), 5)
        
        for i, p in enumerate(paths[:max_items]):
            confidence = p.get("confidence")
            reason = p.get("relation_reason", "")
            suffix = ""
            if confidence is not None:
                suffix += f" (confidence={confidence})"
            if reason:
                suffix += f" — {reason}"
            path_line = f"  • {p.get('path', '')}{suffix}"
            path_chars = len(path_line) + 1
            if chars_used + path_chars > char_budget:
                break
            lines.append(path_line)
            chars_used += path_chars
            evidence_items.append({
                "type": "graph_path",
                "path": p.get("path", ""),
                "relation": p.get("relation", ""),
                "domain": p.get("domain", ""),
                "confidence": p.get("confidence"),
                "relation_reason": p.get("relation_reason", ""),
                "evidence_required": p.get("evidence_required", []),
            })
        
        if entities:
            entity_line = "  涉及实体: " + "、".join(
                f"{e.get('name', '')}({e.get('type', '')})" for e in entities[:5]
            )
            lines.append(entity_line)
            evidence_items.append({
                "type": "matched_entities",
                "entities": [e.get("name", "") for e in entities[:5]],
            })
        
        return {"text": "\n".join(lines), "evidence": evidence_items}
    
    def _build_text_context(
        self,
        merged: List[Dict],
        char_budget: int,
        keywords: List[str] = None,
        query: str = "",
        coverage_terms: List[str] = None,
    ) -> Optional[Dict]:
        """组装文档文本上下文"""
        if not merged:
            return None
        
        lines = ["【文档知识库】"]
        sources = []
        evidence = []
        chars_used = 0
        source_seq = 1
        
        # 按 score 排序，优先取高分 chunk；再叠加同文档席位约束（cap=3）：
        # 大文档（CCAR-92/气象等）的连续命中会把小众正解挤出上下文，超出
        # 席位的条目降到队尾（候选不足时仍会被预算捡回，总量不减）。
        # 注意 cap 必须作用在这次 score 重排之后——只在 Merger 层 cap 会被
        # 本处重排还原垄断（2026-07-11 全量评测实锤）。
        by_score = sorted(merged, key=lambda x: -x.get("score", 0))
        coverage_terms = [str(term) for term in (coverage_terms or []) if str(term)]
        coverage_results = []
        coverage_ids = set()
        for term in coverage_terms:
            hit = next(
                (
                    item
                    for item in by_score
                    if str(item.get("chunk_id") or "") not in coverage_ids
                    and term in (item.get("expanded_text") or item.get("text") or "")
                ),
                None,
            )
            if hit is not None:
                coverage_results.append(hit)
                coverage_ids.add(str(hit.get("chunk_id") or ""))

        sorted_results = list(coverage_results)
        deferred = []
        doc_seat_counts: Dict[str, int] = {}
        for r in by_score:
            if str(r.get("chunk_id") or "") in coverage_ids:
                continue
            doc_key = document_key(r)
            if doc_seat_counts.get(doc_key, 0) >= self.doc_cap > 0:
                deferred.append(r)
                continue
            doc_seat_counts[doc_key] = doc_seat_counts.get(doc_key, 0) + 1
            sorted_results.append(r)
        sorted_results.extend(deferred)
        
        for r in sorted_results:
            text = r.get("expanded_text") or r.get("text", "")
            if not text or len(text.strip()) < 5:
                continue
            
            cid = r.get("chunk_id", f"unknown_{source_seq}")
            doc_name = r.get("doc_name", self._parse_doc_from_chunk_id(cid))
            score = r.get("score", 0)
            
            excerpt_chars = 560
            if coverage_results:
                excerpt_chars = min(
                    excerpt_chars,
                    max(320, int(char_budget / len(coverage_results)) - 120),
                )
            chunk_preview = self._query_aware_excerpt(
                text,
                keywords or [],
                query,
                max_chars=excerpt_chars,
            )

            # 格式: 【来源N】文档名〔效力层级·施行日期〕(相关度: XX%)
            # 层级+日期标注让模型在教材/题库与法规冲突、法规与法规冲突时都有
            # 明确取舍依据（法规优先；法规之间新法覆盖老法），不用猜。
            tier = source_tier(doc_name, cid)
            header = (
                f"【来源{source_seq}】{doc_name}"
                f"〔{source_annotation(doc_name, cid)}〕(相关度: {score*100:.0f}%)\n"
                f"{chunk_preview}"
            )
            if asks_for_source_disclosure(query):
                supporting_line = supporting_source_disclosure(
                    r.get("supporting_sources") or []
                )
                if supporting_line:
                    header += f"\n{supporting_line}"
            
            if chars_used + len(header) + 2 > char_budget:
                break
            
            lines.append(header)
            chars_used += len(header) + 1
            
            sources.append({
                "chunk_id": cid,
                "doc_name": doc_name,
                "relevance": round(score, 4),
                "seq": source_seq,
                "authority": tier["tier"],
                "authority_rank": tier["rank"],
                "effective_date": (regulation_meta(doc_name) or {}).get("effective_date"),
                "expanded_chunk_ids": r.get("expanded_chunk_ids", [cid]),
                "concept_cluster_id": r.get("concept_cluster_id"),
                "claim_key": r.get("claim_key"),
                "claim_id": r.get("claim_id"),
                "supporting_sources": r.get("supporting_sources", []),
                "source_pages": r.get("source_pages"),
                "content_type": r.get("content_type"),
                "section_id": r.get("section_id"),
                "section_title": r.get("section_title"),
                "source": r.get("source")
                or next(iter(r.get("sources") or []), "internal"),
            })
            evidence.append({
                "type": "document",
                "source_num": source_seq,
                "chunk_id": cid,
                "expanded_chunk_ids": r.get("expanded_chunk_ids", [cid]),
                "preview": chunk_preview[:100],
                "concept_cluster_id": r.get("concept_cluster_id"),
                "claim_key": r.get("claim_key"),
                "supporting_sources": r.get("supporting_sources", []),
            })
            source_seq += 1
        
        return {"text": "\n\n".join(lines), "sources": sources, "evidence": evidence}

    def _query_aware_excerpt(self, text: str, keywords: List[str], query: str, max_chars: int = 420) -> str:
        """围绕命中词截取窗口；无命中时回退到开头。"""
        if len(text) <= max_chars:
            return text.strip()

        terms = []
        terms.extend(k for k in keywords if k and len(k) >= 2)
        for part in re.split(r"[\s,，。！？、；：:;()（）【】《》]+", query or ""):
            if len(part) >= 2:
                terms.append(part)
        # 粗粒度关键词（如整句长尾词）常在正文找不到命中；用 jieba 细分
        # 补充词元，让密度窗口能对准数值/参数所在的段落。
        try:
            import jieba

            stop = {"的", "和", "是", "多少", "什么", "哪些", "如何", "怎么", "为什么", "以及", "或者"}
            for tok in jieba.cut(query or ""):
                tok = tok.strip()
                if len(tok) >= 2 and tok not in stop:
                    terms.append(tok)
        except Exception:
            pass

        seen = set()
        terms = [t for t in terms if not (t in seen or seen.add(t))]
        hit_positions = [text.find(t) for t in terms if text.find(t) >= 0]
        if not hit_positions:
            return text[:max_chars].strip() + "..."

        # 锚定“命中最密”的窗口而不是最早命中：参数表/数据表类答案常在
        # chunk 尾部，最早命中锚定会把它们截掉（2026-07-10 Mavic 参数题）。
        all_hits = []
        for t in terms:
            idx = 0
            while True:
                p = text.find(t, idx)
                if p < 0:
                    break
                all_hits.append((p, t))
                idx = p + 1
        best_pos, best_cover = min(hit_positions), -1
        for p, _t in all_hits:
            w_start = max(0, p - max_chars // 3)
            w_end = min(len(text), w_start + max_chars)
            w_start = max(0, w_end - max_chars)
            cover = len({t2 for (p2, t2) in all_hits if w_start <= p2 < w_end})
            if cover > best_cover or (cover == best_cover and p < best_pos):
                best_cover, best_pos = cover, p
        pos = best_pos
        start = max(0, pos - max_chars // 3)
        end = min(len(text), start + max_chars)
        start = max(0, end - max_chars)
        excerpt = text[start:end].strip()
        if start > 0:
            excerpt = "..." + excerpt
        if end < len(text):
            excerpt += "..."
        return excerpt
    
    def _parse_doc_from_chunk_id(self, chunk_id: str) -> str:
        """从 chunk_id 推导文档名"""
        if "_" in chunk_id:
            parts = chunk_id.split("_", 1)
            return parts[-1] if len(parts) > 1 else chunk_id
        return chunk_id
    
    def build_answer_prompt(
        self,
        context: str,
        query: str,
        intent: str,
        evidence: List[Dict],
        sources: List[Dict],
        matched_question: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建 LLM 回答 prompt

        `matched_question` 非空才代表用户问的就是题库里那道原题；只有这种情况
        才允许输出题库关联栏目。仅仅"检索命中了题库文档"不算。
        """
        
        # 意图特定指令
        intent_prompts = {
            "regulation": "你是CAAC无人机法规助手。回答需引用法规条文，标注来源编号。",
            "job": "你是无人机行业就业顾问。基于真实招聘数据和你对行业的了解回答。",
            "training": "你是CAAC无人机培训教员。回答要专业清晰，适合学员理解。",
            "general": "你是无人机知识助手。回答要专业、简洁、有用。",
        }
        role_prompt = intent_prompts.get(intent, intent_prompts["general"])
        
        question_bank_hit = any(is_question_bank_source(source) for source in sources)

        # 证据摘要
        evidence_summary = ""
        if evidence:
            ev_lines = []
            for e in evidence[:5]:
                if e["type"] == "graph_path":
                    ev_lines.append(f"  （图谱）{e.get('path', '')}")
                elif e["type"] == "document":
                    ev_lines.append(f"  （来源{e.get('source_num', '?')}）{e.get('preview', '')[:60]}")
            if ev_lines:
                evidence_summary = "\n证据链：\n" + "\n".join(ev_lines)
        
        if matched_question:
            original_question = format_matched_question(matched_question)
            stale_note = matched_question.get("superseded_note") or {}
            stale_requirement = (
                "\n- 这道题依据的规章已被取代：在“题库关联”之后必须单列“时效提示”，"
                f"说明考试仍按题库答案作答，但现行口径以 {'、'.join(stale_note.get('superseded_by') or []) or '现行法规'} 为准，"
                "实际运行不要照搬本题结论"
                if stale_note
                else ""
            )
            answer_requirements = f"""- 先完整回答用户的问题，保留原理、定义、计算过程和实际意义，不得只给一句标准答案{stale_requirement}
- 正文建议 500-900 个中文字符；复杂问题可略长，以讲清楚为准
- 本题已确认命中题库原题，随后单列“题库关联”，逐字照抄下面这道原题，不得改写、不得补造字段：
{original_question}
- 单列“考试关注点”：说明命题人考什么、判断或计算步骤是什么
- 有公式或数量关系时单列“计算方法”，给出公式、变量含义和至少一个贴合问题的示例
- 单列“常见误区”：指出容易混淆的概念、单位、线数或选项陷阱
- 涉及设备操作、电池、飞行或现场处置时，补充“实操与安全”；纯理论题可省略该栏目
- 题库答案与教材原理都命中时，先给题库标准结论，再用教材解释原因；不得用图谱路径覆盖题库原文"""
        elif question_bank_hit:
            # 检索捞到题库文档，但用户问的不是那道原题。此时任何题号/选项/参考答案
            # 都不属于用户这道题，挂出来只会误导（2026-07-26 实测挂错 113 题）。
            answer_requirements = """- 250字左右，简洁专业；把题库片段当普通资料用，只取其中的知识点和原理
- 本轮没有匹配到与用户问题完全相同的原题：禁止输出“题库关联”“近似题”“相关题目”“原题”等任何栏目
- 禁止给出题号、题干、选项、参考答案，也不要写“来源未提供”这类占位字段
- 不要提示用户“题库中有相近题目”，不要罗列不是用户所问的那道题"""
        else:
            answer_requirements = "- 250字左右，简洁专业"

        # 用户没追问来源时，答案里不许出现【来源N】：那是内部检索列表的临时编号，
        # 用户看不到也无法核验，还显得不专业（2026-07-26 李腾达）。
        disclose_sources = asks_for_source_disclosure(query)
        citation_requirements = (
            """- 用户在追问来源，请给出可核验的引用：写《文档名》+条款号/章节/题号
- 禁止输出“【来源1】”这类内部编号；用户看不到那张列表
- 来源里没有确切条款号时写“内部资料显示……（待核验）”，不要编造"""
            if disclose_sources
            else """- 直接给结论，像专业教员那样说话；禁止出现“【来源1】”这类内部编号
- 不要用“根据知识库已有信息”“根据提供的上下文”“本轮检索”开头，也不要点评哪条来源相关或不相关
- 需要点明法规依据时，直接写《法规名》第 x 条这类专业引证，不要罗列来源清单"""
        )
        navigation_light_requirement = navigation_light_scope_requirement(query)

        prompt = f"""{role_prompt}

检索上下文：
{context}
{evidence_summary}

问题：{query}

要求：
- 基于上下文回答，不要编造信息
- 先用检索上下文确定事实锚点；上下文中的明确结论、题库标准答案和现行法规不得被大模型专业知识改写或推翻
- 可以用大模型专业知识补充原理、背景、实务说明和表达，让答案更完整专业；上下文未直接覆盖的判断必须标为“分析推断”，且不得与内部证据冲突
- 大模型补充必须服务于用户当前问题；不得主动扩展为内部证据没有直接支撑的新事实断言
{navigation_light_requirement}
- {authority_priority_rule()}
{citation_requirements}
- 图谱路径可作为推理依据标注
- 对“来源、出处、官方原文、文号、是否准确、对不对”等核验类问题，不能把用户问题里的表述当作事实；上下文没有直接证据时要明确说无法证实
- 不要引用与待核验结论无关的来源来支撑该结论
- 涉及数字、比例、排名、趋势、预测、新增/变化、通过率、题库规模、考试难度时，必须能在上下文或来源中找到直接依据；没有依据就写“当前上下文无法证明”
- 如需给出分析推断，必须单列“分析推断”，且不得加入无来源的精确数值
{answer_requirements}"""
        
        return prompt
    
    def close(self):
        if self._store:
            self._store.close()


# ============ 测试 ============

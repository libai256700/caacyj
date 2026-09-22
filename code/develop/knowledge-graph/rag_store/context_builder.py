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
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    from sqlite_store import RagStore
else:
    from .sqlite_store import RagStore


# 中文 token 估算：约 1.5 字符 = 1 token
CHAR_PER_TOKEN = 1.5


class ContextBuilder:
    """上下文组装器"""
    
    def __init__(
        self,
        max_tokens: int = 2400,
        db_path: str = None,
        neighbor_window: int = 1,
        max_neighbor_chars: int = 900,
    ):
        self.max_tokens = max_tokens
        self.max_chars = int(max_tokens * CHAR_PER_TOKEN)
        self.neighbor_window = max(0, neighbor_window)
        self.max_neighbor_chars = max(0, max_neighbor_chars)
        self._store = None
        self._db_path = db_path
    
    @property
    def store(self) -> RagStore:
        if self._store is None:
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
        
        # Step 1: 回源取文本（已有 text 的跳过，没有的去 SQLite 取）
        enriched = self._enrich_with_text(merged_results)
        
        # Step 2: 组装上下文，控制 token
        sections = []
        sources = []
        evidence = []
        char_budget = self.max_chars
        
        # 分配预算：图谱路径占 20%，文本上下文占 80%
        kg_budget = int(char_budget * 0.20)
        text_budget = int(char_budget * 0.80)
        
        # 2a: 图谱证据
        kg_section = self._build_kg_evidence(kg_paths, matched_entities, kg_budget)
        if kg_section:
            sections.append(kg_section["text"])
            evidence.extend(kg_section["evidence"])
        
        # 2b: 文档上下文
        text_section = self._build_text_context(enriched, text_budget, keywords=keywords, query=query)
        if text_section:
            sections.append(text_section["text"])
            sources.extend(text_section["sources"])
            evidence.extend(text_section["evidence"])
        
        # 合并
        full_context = "\n\n".join(sections) if sections else "（未找到相关内容）"
        token_estimate = int(len(full_context) / CHAR_PER_TOKEN)
        
        return {
            "context": full_context,
            "sources": sources,
            "evidence": evidence,
            "token_estimate": token_estimate,
            "query": query,
            "intent": intent,
        }
    
    def _enrich_with_text(self, merged_results: List[Dict]) -> List[Dict]:
        """统一从 SQLite 回源取文本，检索器返回的 text 只作为调试信息。"""
        enriched = []
        to_fetch = [r["chunk_id"] for r in merged_results if r.get("chunk_id")]
        
        if to_fetch:
            texts = self.store.get_chunks_batch(to_fetch)
            text_map = {t["chunk_id"]: t for t in texts}
            
            for r in merged_results:
                item = dict(r)
                if item.get("chunk_id") in text_map:
                    item["text"] = text_map[item["chunk_id"]]["text"]
                    item["doc_name"] = text_map[item["chunk_id"]].get("doc_name", "")
                    item["chunk_index"] = text_map[item["chunk_id"]].get("chunk_index", 0)
                    self._attach_neighbor_text(item)
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
        self, merged: List[Dict], char_budget: int, keywords: List[str] = None, query: str = ""
    ) -> Optional[Dict]:
        """组装文档文本上下文"""
        if not merged:
            return None
        
        lines = ["【文档知识库】"]
        sources = []
        evidence = []
        chars_used = 0
        source_seq = 1
        
        # 按 score 排序，优先取高分 chunk
        sorted_results = sorted(merged, key=lambda x: -x.get("score", 0))
        
        for r in sorted_results:
            text = r.get("expanded_text") or r.get("text", "")
            if not text or len(text.strip()) < 5:
                continue
            
            cid = r.get("chunk_id", f"unknown_{source_seq}")
            doc_name = r.get("doc_name", self._parse_doc_from_chunk_id(cid))
            score = r.get("score", 0)
            
            chunk_preview = self._query_aware_excerpt(text, keywords or [], query, max_chars=560)
            
            # 格式: 【来源N】文档名 (相关度: XX%)
            header = f"【来源{source_seq}】{doc_name} (相关度: {score*100:.0f}%)\n{chunk_preview}"
            
            if chars_used + len(header) + 2 > char_budget:
                break
            
            lines.append(header)
            chars_used += len(header) + 1
            
            sources.append({
                "chunk_id": cid,
                "doc_name": doc_name,
                "relevance": round(score, 4),
                "seq": source_seq,
                "expanded_chunk_ids": r.get("expanded_chunk_ids", [cid]),
            })
            evidence.append({
                "type": "document",
                "source_num": source_seq,
                "chunk_id": cid,
                "expanded_chunk_ids": r.get("expanded_chunk_ids", [cid]),
                "preview": chunk_preview[:100],
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

        seen = set()
        terms = [t for t in terms if not (t in seen or seen.add(t))]
        hit_positions = [text.find(t) for t in terms if text.find(t) >= 0]
        if not hit_positions:
            return text[:max_chars].strip() + "..."

        pos = min(hit_positions)
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
    ) -> str:
        """构建 LLM 回答 prompt"""
        
        # 意图特定指令
        intent_prompts = {
            "regulation": "你是CAAC无人机法规助手。回答需引用法规条文，标注来源编号。",
            "company": "你是云技科技客服助手。回答要准确、友好，基于公司真实信息。",
            "job": "你是无人机行业就业顾问。基于真实招聘数据和你对行业的了解回答。",
            "training": "你是CAAC无人机培训教员。回答要专业清晰，适合学员理解。",
            "general": "你是无人机知识助手。回答要专业、简洁、有用。",
        }
        role_prompt = intent_prompts.get(intent, intent_prompts["general"])
        
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
        
        prompt = f"""{role_prompt}

检索上下文：
{context}
{evidence_summary}

问题：{query}

要求：
- 基于上下文回答，不要编造信息
- 用引用标注来源编号，如 【来源1】
- 图谱路径可作为推理依据标注
- 对“来源、出处、官方原文、文号、是否准确、对不对”等核验类问题，不能把用户问题里的表述当作事实；上下文没有直接证据时要明确说无法证实
- 不要引用与待核验结论无关的来源来支撑该结论
- 250字左右，简洁专业"""
        
        return prompt
    
    def close(self):
        if self._store:
            self._store.close()


# ============ 测试 ============
if __name__ == "__main__":
    builder = ContextBuilder()
    
    # 模拟 merged 结果
    merged = [
        {"chunk_id": "理论题库_飞行原理与飞行性能.txt_0", "score": 0.85, "text": ""},
        {"chunk_id": "企业信息_价格表.txt_0", "score": 0.72, "text": ""},
    ]
    
    kg_paths = [
        {"path": "云技科技 -[PROVIDES]-> 培训课程 -[INCLUDES]-> CAAC考证", "relation": "PROVIDES → INCLUDES"},
    ]
    entities = [{"name": "云技科技", "type": "Company"}]
    
    result = builder.build(merged, kg_paths, entities, query="CAAC考证多少钱？", intent="company")
    
    print("📝 上下文 (前500字):")
    print(result["context"][:500])
    print(f"\n📊 token估计: {result['token_estimate']}")
    print(f"📚 来源数: {len(result['sources'])}")
    print(f"🔗 证据数: {len(result['evidence'])}")
    
    prompt = builder.build_answer_prompt(**{k: v for k, v in result.items() if k in ("context", "query", "intent", "evidence", "sources")})
    print(f"\n🤖 LLM Prompt (后300字):\n{prompt[-300:]}")
    
    builder.close()

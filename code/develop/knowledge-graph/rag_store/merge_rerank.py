#!/usr/bin/env python3
"""
Merge + Rerank 模块

融合三路召回结果（Dense向量 / Sparse关键词 / Neo4j图谱），
去重、加权排序，返回 Top-K。
"""

import json, re, math
from typing import List, Dict, Any, Set, Tuple
from collections import defaultdict


class Merger:
    """三路结果融合 + 去重 + Rerank"""

    def __init__(
        self,
        top_k: int = 20,
        weight_vector: float = 1.0,
        weight_sparse: float = 1.0,
        weight_kg: float = 1.0,
        rrf_k: int = 60,
        max_external_boost: float = 0.00005,
    ):
        self.top_k = top_k
        self.weight_vector = weight_vector
        self.weight_sparse = weight_sparse
        self.weight_kg = weight_kg
        self.rrf_k = rrf_k
        self.max_external_boost = max_external_boost

    def merge(
        self,
        vector_results: List[Dict] = None,
        sparse_results: List[Dict] = None,
        kg_results: Dict = None,
        keywords: List[str] = None,
        entities: List[Dict] = None,
    ) -> List[Dict]:
        """
        主入口：融合三路结果
        
        Args:
            vector_results: [{"chunk_id", "score", "text"(可选), "type", "source"}]
            sparse_results: [{"chunk_id", "score", "text"(可选), "source"}]
            kg_results: {"chunk_ids": [...], "paths": [...], "matched_entities": [...]}
            keywords: 关键词列表（用于计算关键词命中分）
            entities: 实体列表
        
        Returns:
            [{"chunk_id", "text", "combined_score", "source", "vector_score", "kg_score"}]
        """
        vector_results = vector_results or []
        sparse_results = sparse_results or []
        kg_results = kg_results or {}
        keywords = keywords or []
        entities = entities or []

        # Step 1: 为 KG 结果构造条目
        kg_chunk_ids = kg_results.get("chunk_ids", [])
        kg_entries = self._score_kg_chunks(
            kg_chunk_ids,
            kg_results.get("paths", []),
            kg_results.get("matched_entities", []),
            keywords,
        )

        # Step 2: RRF 融合，避免 min-max 在单路单条结果时劫持排序。
        merged: Dict[str, Dict] = {}

        self._add_ranked_source(merged, vector_results, "vector", self.weight_vector, keywords)
        self._add_ranked_source(merged, sparse_results, "sparse", self.weight_sparse, keywords)
        self._add_ranked_source(merged, kg_entries, "kg", self.weight_kg, keywords)

        # Step 3: 关键词命中轻微加分，不能超过 RRF 主排序。
        for entry in merged.values():
            entry["combined_score"] += min(entry.get("keyword_hits", 0) * 0.002, 0.01)

        # Step 5: 排序，取 top_k
        ranked = sorted(merged.values(), key=lambda x: -x["combined_score"])
        top = ranked[: self.top_k]

        # Step 6: 补充文本（如果有的话）
        result = []
        for i, item in enumerate(top):
            result.append({
                "chunk_id": item["chunk_id"],
                "text": item.get("text", ""),
                "score": round(item["combined_score"], 4),
                "rank": i + 1,
                "sources": item["sources"],
                "vector_score": round(item["vector_score"], 4),
                "sparse_score": round(item["sparse_score"], 4),
                "kg_score": round(item["kg_score"], 4),
                "source_ranks": item.get("source_ranks", {}),
                "type": item.get("type", "chunk"),
            })

        return result

    def _normalize_scores(self, items: List[Dict], score_key: str = "score") -> List[Dict]:
        """将分数归一化到 [0, 1]"""
        if not items:
            return []
        scores = [item.get(score_key, 0.0) for item in items]
        min_s = min(scores)
        max_s = max(scores)
        
        if max_s == min_s:
            return [{**item, "score": 1.0 if max_s > 0 else 0.0} for item in items]
        
        return [
            {**item, "score": (item.get(score_key, 0.0) - min_s) / (max_s - min_s)}
            for item in items
        ]

    def _add_ranked_source(
        self,
        merged: Dict[str, Dict],
        items: List[Dict],
        source_name: str,
        source_weight: float,
        keywords: List[str],
    ):
        sorted_items = sorted(items or [], key=lambda x: -float(x.get("score", 0)))
        for rank, item in enumerate(sorted_items, start=1):
            cid = item.get("chunk_id", "")
            if not cid:
                continue
            entry = merged.setdefault(cid, {
                "chunk_id": cid,
                "text": item.get("text", ""),
                "vector_score": 0.0,
                "sparse_score": 0.0,
                "kg_score": 0.0,
                "keyword_hits": self._count_keyword_hits(item.get("text", ""), keywords),
                "sources": [],
                "source_ranks": {},
                "combined_score": 0.0,
                "type": item.get("type", "chunk"),
            })
            if item.get("text") and not entry.get("text"):
                entry["text"] = item["text"]
            if source_name not in entry["sources"]:
                entry["sources"].append(source_name)
            entry["source_ranks"][source_name] = rank
            raw_score = float(item.get("score", 0))
            entry[f"{source_name}_score"] = max(entry.get(f"{source_name}_score", 0.0), raw_score)
            entry["combined_score"] += source_weight / (self.rrf_k + rank)
            entry["combined_score"] += min(float(item.get("boost", 0.0)), self.max_external_boost)

    def _score_kg_chunks(
        self,
        chunk_ids: List[str],
        paths: List[Dict],
        matched_entities: List[Dict],
        keywords: List[str],
    ) -> List[Dict]:
        """为 KG 召回的 chunk_id 计算相关性分数
        
        分数构成：
        - 基础分 0.6（图谱召回代表有明确关联）
        - 路径深度加分（1-hop: +0.2, 2-hop: +0.1）
        - 实体匹配数加分（每多1个匹配实体 +0.05，上限 0.2）
        """
        base_score = 0.6
        path_bonus = 0.0
        if paths:
            min_hops = min(len(p.get("nodes", [2])) - 1 for p in paths)
            path_bonus = 0.2 if min_hops == 1 else 0.1
        
        entity_bonus = min(len(matched_entities) * 0.05, 0.2)
        score = min(base_score + path_bonus + entity_bonus, 1.0)

        return [
            {"chunk_id": cid, "score": score, "text": ""}
            for cid in chunk_ids
        ]

    def _count_keyword_hits(self, text: str, keywords: List[str]) -> int:
        """计算文本中命中的关键词数量"""
        if not text or not keywords:
            return 0
        return sum(1 for kw in keywords if kw in text)

    def merge_stats(self, results: List[Dict]) -> Dict:
        """返回融合结果统计"""
        sources = defaultdict(int)
        for r in results:
            for s in r.get("sources", []):
                sources[s] += 1

        return {
            "total": len(results),
            "source_distribution": dict(sources),
            "score_range": {
                "min": round(min(r["score"] for r in results), 4) if results else 0,
                "max": round(max(r["score"] for r in results), 4) if results else 0,
                "avg": round(sum(r["score"] for r in results) / len(results), 4) if results else 0,
            },
        }


# ============ 测试 ============
if __name__ == "__main__":
    merger = Merger(top_k=10)

    # 模拟三路结果
    vector = [
        {"chunk_id": "c1", "score": 0.85, "text": "云技科技位于硚口区，主营无人机培训业务"},
        {"chunk_id": "c2", "score": 0.72, "text": "CAAC考证需要完成理论和实操考试"},
        {"chunk_id": "c3", "score": 0.65, "text": "无人机测绘资质由民航局和地方测绘部门联合审批"},
    ]

    sparse = [
        {"chunk_id": "c2", "score": 0.90, "text": "CAAC考证需要完成理论和实操考试"},
        {"chunk_id": "c4", "score": 0.80, "text": "培训课程价格表：兴趣爱好班 5800元"},
    ]

    kg = {
        "chunk_ids": ["c5", "c3"],
        "paths": [
            {"path": "云技科技 -[PROVIDES]-> 培训课程", "nodes": ["云技科技", "培训课程"]},
        ],
        "matched_entities": [
            {"name": "云技科技", "type": "Company"},
        ],
    }

    merged = merger.merge(vector, sparse, kg, keywords=["测绘", "资质", "CAAC"])
    stats = merger.merge_stats(merged)

    print("📊 融合结果:")
    for m in merged:
        print(f"  #{m['rank']} [{', '.join(m['sources'])}] "
              f"score={m['score']} | {m['chunk_id']}: {m['text'][:50]}...")

    print(f"\n📈 统计: {json.dumps(stats, ensure_ascii=False)}")

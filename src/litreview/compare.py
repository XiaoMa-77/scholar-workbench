"""Rule-based cross-paper analysis: tags, similarity, clusters, comparison table."""

from __future__ import annotations

import math
import re
from collections import Counter

from .models import Paper, PaperContent

STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with", "we",
    "is", "are", "this", "that", "by", "as", "at", "from", "it", "its", "be",
    "our", "their", "these", "those", "which", "can", "than", "into", "such",
    "using", "used", "use", "based", "propose", "proposed", "proposewe",
    "paper", "work", "results", "show", "shown", "also", "between", "over",
    "both", "each", "other", "more", "most", "less", "least", "new", "novel",
    "approach", "method", "methods", "model", "models", "task", "tasks",
    "problem", "problems", "study", "studies", "different", "significant",
    "significantly", "respectively", "however", "there", "have", "has", "not",
    "but", "when", "where", "while", "then", "thus", "hence", "via", "per",
    "propose", "presents", "present", "proposewe", "et", "al",
}
TOKEN_RE = re.compile(r"[a-z][a-z0-9-]{2,}")


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def tag_papers(papers: list[Paper], top: int = 5) -> dict[str, list[str]]:
    """Discriminative terms per paper: tf-idf against the paper corpus."""
    docs = {p.id: Counter(tokenize(f"{p.title} {p.abstract}")) for p in papers}
    total_docs = max(1, len(docs))
    tags: dict[str, list[str]] = {}
    for paper_id, counts in docs.items():
        scores = []
        for term, count in counts.items():
            if len(term) < 4 or count < 1:
                continue
            doc_freq = sum(1 for other in docs.values() if term in other)
            if doc_freq == 0:
                continue
            idf = math.log((1 + total_docs) / (1 + doc_freq)) + 1.0
            exclusivity = 1.0 / max(1, doc_freq - 1) if doc_freq > 1 else 1.0
            scores.append((count * idf * (0.4 + 0.6 * exclusivity), term))
        tags[paper_id] = [term for _, term in sorted(scores, reverse=True)[:top]]
    return tags


def similarity(papers: list[Paper]) -> dict[tuple[str, str], float]:
    """Jaccard similarity of abstract token sets (upper-triangle keys)."""
    sets = {p.id: set(tokenize(p.abstract)) for p in papers}
    out: dict[tuple[str, str], float] = {}
    ids = [p.id for p in papers]
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            union = sets[a] | sets[b]
            out[(a, b)] = len(sets[a] & sets[b]) / len(union) if union else 0.0
    return out


def frequent_terms(papers: list[Paper], top: int = 10) -> dict[str, set[str]]:
    """Most frequent terms per paper; unlike discriminative tags these capture
    shared topic vocabulary, which is what clustering needs."""
    out: dict[str, set[str]] = {}
    for paper in papers:
        counts = Counter(tokenize(f"{paper.title} {paper.abstract}"))
        out[paper.id] = {term for term, count in counts.most_common(top) if count >= 1
                         and len(term) >= 4}
    return out


def cluster_papers(papers: list[Paper], tags: dict[str, list[str]],
                   threshold: float = 0.2) -> list[list[Paper]]:
    """Greedy clustering on overlap coefficient of frequent terms.

    Overlap coefficient (intersection / smaller set) tolerates abstracts of
    very different lengths, unlike raw Jaccard.
    """
    freq = frequent_terms(papers)
    by_id = {p.id: p for p in papers}
    clusters: list[list[str]] = []
    for paper in papers:
        target = None
        for cluster in clusters:
            for member in cluster:
                shared = freq[paper.id] & freq[member]
                smaller = min(len(freq[paper.id]), len(freq[member]))
                if smaller and len(shared) / smaller >= threshold:
                    target = cluster
                    break
            if target:
                break
        if target is None:
            clusters.append([])
            target = clusters[-1]
        target.append(paper.id)
    return [[by_id[i] for i in cluster] for cluster in clusters]


def comparison_rows(papers: list[Paper], contents: dict[str, PaperContent],
                    tags: dict[str, list[str]]) -> list[list[str]]:
    header = ["#", "论文", "年份", "发表处", "引用", "方法标签", "图表数", "全文字符"]
    rows = [header]
    for index, paper in enumerate(papers, start=1):
        content = contents.get(paper.id)
        rows.append([
            str(index), _short(paper.title, 46), str(paper.year or "—"),
            _short(paper.venue or "arXiv preprint", 24),
            str(paper.citations if paper.citations is not None else "—"),
            ", ".join(tags.get(paper.id, [])[:4]) or "—",
            str(content.figure_count if content else "—"),
            str(content.text_chars if content else "—"),
        ])
    return rows


def markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    head, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(head) + " |",
             "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def _short(text: str, width: int) -> str:
    text = text.replace("|", "/")
    return text if len(text) <= width else text[: width - 1] + "…"

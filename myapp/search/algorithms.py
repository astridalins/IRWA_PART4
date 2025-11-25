# myapp/search/algorithms.py

import math
from array import array
from collections import defaultdict


def create_inverted_index(corpus: dict):
    """
    Input:
      corpus: dict(pid -> Document)
    Output:
      inverted_index: term -> list of [doc_id, array(positions)]
      doc_id_map: dict(doc_id -> pid)
      reverse_map: dict(pid -> doc_id)
    """
    inverted_index = defaultdict(list)
    doc_id_map = {}
    reverse_map = {}

    for doc_id, pid in enumerate(corpus.keys()):
        doc_id_map[doc_id] = pid
        reverse_map[pid] = doc_id

        doc = corpus[pid]
        title_tokens = getattr(doc, "title_tokens", []) or []
        desc_tokens = getattr(doc, "desc_tokens", []) or []
        all_tokens = title_tokens + desc_tokens

        local_index = {}
        for pos, term in enumerate(all_tokens):
            if term not in local_index:
                local_index[term] = [doc_id, array("I", [pos])]
            else:
                local_index[term][1].append(pos)

        for term, posting in local_index.items():
            inverted_index[term].append(posting)

    return inverted_index, doc_id_map, reverse_map


# ---------- TF-IDF simple ----------
def rank_query_tf_idf(query: str, inverted_index, corpus, doc_id_map):
    N = len(doc_id_map)
    query_terms = query.lower().split()

    df = {t: len(inverted_index.get(t, [])) for t in query_terms}
    idf = {t: math.log(N / df[t]) if df[t] > 0 else 0 for t in query_terms}

    scores = defaultdict(float)
    for t in query_terms:
        postings = inverted_index.get(t, [])
        for posting in postings:
            doc_id, positions = posting[0], posting[1]
            tf = len(positions)
            scores[doc_id] += tf * idf[t]

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked


# ---------- TF-IDF + Cosine (AND semantics) ----------
def rank_query_tf_idf_cosine(query: str, inverted_index, corpus, doc_id_map):
    N = len(doc_id_map)
    query_terms = query.lower().split()

    df = {t: len(inverted_index.get(t, [])) for t in query_terms}
    idf = {t: math.log(N / df[t]) if df[t] > 0 else 0 for t in query_terms}

    # compute doc lengths
    doc_lengths = {}
    for doc_id, pid in doc_id_map.items():
        doc = corpus[pid]
        tokens = getattr(doc, "title_tokens", []) + getattr(doc, "desc_tokens", [])
        doc_lengths[doc_id] = len(tokens)

    # AND semantics: only docs containing all terms
    matching_docs = set(doc_id_map.keys())
    for t in query_terms:
        postings = inverted_index.get(t, [])
        if not postings:
            matching_docs = set()
            break
        docs_with_t = {p[0] for p in postings}
        matching_docs &= docs_with_t

    if not matching_docs:
        return []

    query_vec = [idf[t] for t in query_terms]

    def cosine(v1, v2):
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        return dot / (n1 * n2) if n1 and n2 else 0

    scores = {}
    for doc_id in matching_docs:
        doc_vec = []
        for t in query_terms:
            tf = 0
            for p in inverted_index.get(t, []):
                if p[0] == doc_id:
                    tf = len(p[1])
                    break
            doc_vec.append(tf * idf[t])
        scores[doc_id] = cosine(query_vec, doc_vec)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked


# ---------- BM25 ----------
def rank_query_bm25(query: str, inverted_index, corpus, doc_id_map, k1=1.5, b=0.75):
    N = len(doc_id_map)
    query_terms = query.lower().split()

    doc_lengths = {}
    for doc_id, pid in doc_id_map.items():
        doc = corpus[pid]
        tokens = getattr(doc, "title_tokens", []) + getattr(doc, "desc_tokens", [])
        doc_lengths[doc_id] = len(tokens)

    avg_len = sum(doc_lengths.values()) / N if N > 0 else 1.0

    df = {t: len(inverted_index.get(t, [])) for t in query_terms}
    idf = {
        t: math.log((N - df[t] + 0.5) / (df[t] + 0.5) + 1) if df[t] > 0 else 0
        for t in query_terms
    }

    scores = defaultdict(float)
    matching_docs = set(doc_id_map.keys())

    for t in query_terms:
        postings = inverted_index.get(t, [])
        if not postings:
            matching_docs = set()
            break

        docs_with_t = set()
        for doc_id, positions in postings:
            docs_with_t.add(doc_id)
            tf = len(positions)
            L = doc_lengths[doc_id]
            num = tf * (k1 + 1)
            den = tf + k1 * (1 - b + b * (L / avg_len))
            scores[doc_id] += idf[t] * (num / den)

        matching_docs &= docs_with_t

    filtered = {doc_id: scores[doc_id] for doc_id in matching_docs}
    ranked = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
    return ranked


# ---------- Wrapper (función solicitada por el enunciado) ----------
def search_in_corpus(
    query: str, algo: str, corpus: dict, inverted_index, doc_id_map, top_k: int = 20
):
    """
    High-level search function used by search_engine.SearchEngine.
    Returns list of dicts (pid,title,description,selling_price,discount,average_rating,url,score)
    """
    if not query or query.strip() == "":
        return []

    if algo == "tfidf":
        ranked = rank_query_tf_idf(query, inverted_index, corpus, doc_id_map)
    elif algo == "tfidf_cos":
        ranked = rank_query_tf_idf_cosine(query, inverted_index, corpus, doc_id_map)
    elif algo == "bm25":
        ranked = rank_query_bm25(query, inverted_index, corpus, doc_id_map)
    else:
        ranked = []

    results = []
    for doc_id, score in ranked[:top_k]:
        pid = doc_id_map[doc_id]
        d = corpus[pid]
        results.append(
            {
                "pid": pid,
                "title": d.title,
                "description": d.description,
                "selling_price": d.selling_price,
                "discount": d.discount,
                "average_rating": d.average_rating,
                "url": d.url,
                "score": float(score),
            }
        )
    return results

import random
import numpy as np
from myapp.search.objects import Document, ResultItem
from myapp.search.load_corpus import load_corpus
from myapp.search.algorithms import create_inverted_index, search_in_corpus

# Globals cached for the app
_CORPUS = None  # dict pid -> Document
_INVERTED_INDEX = None  # term -> postings
_DOC_ID_MAP = None  # doc_id -> pid
_PID_TO_DOCID = None  # pid -> doc_id
_LOADED = False


def initialize(corpus_path=None):
    """
    Initialize corpus and index. Call once at app startup.
    corpus_path: path to JSON file (if None, caller must pass in).
    """
    global _CORPUS, _INVERTED_INDEX, _DOC_ID_MAP, _PID_TO_DOCID, _LOADED
    if _LOADED:
        return

    if corpus_path is None:
        # default path relative to project root
        import pathlib

        base = pathlib.Path(__file__).resolve().parents[2]
        corpus_path = base / "data" / "fashion_products_dataset.json"

    # load corpus (returns dict pid -> Document)
    _CORPUS = load_corpus(str(corpus_path))

    # build inverted index using algorithms.create_inverted_index
    _INVERTED_INDEX, _DOC_ID_MAP, _PID_TO_DOCID = create_inverted_index(_CORPUS)

    _LOADED = True


def dummy_search(corpus: dict, search_id, num_results=20):
    """
    Keep original dummy_search behaviour as fallback (returns list of Document-like objects).
    We adapt to return ResultItem instances for consistency.
    """
    res = []
    doc_ids = list(corpus.keys())
    docs_to_return = np.random.choice(
        doc_ids, size=min(num_results, len(doc_ids)), replace=False
    )
    for pid in docs_to_return:
        doc = corpus[pid]
        # Return ResultItem-like dict for compatibility with templates
        res.append(
            {
                "pid": doc.pid,
                "title": doc.title,
                "description": doc.description,
                "url": doc.url,
                "ranking": random.random(),
            }
        )
    return res


class SearchEngine:
    """Class that implements the search engine logic"""

    def __init__(self, corpus_path=None):
        initialize(corpus_path)

    def search(self, search_query, search_id, corpus=None, algo="tfidf", top_k=20):
        """
        search_query: query string
        search_id: (unused) original parameter kept for compatibility
        corpus: if provided, must be dict pid->Document; otherwise use loaded corpus
        algo: "tfidf", "tfidf_cos", "bm25" (default "tfidf")
        """
        global _CORPUS, _INVERTED_INDEX, _DOC_ID_MAP

        if corpus is None:
            corpus = _CORPUS

        if _INVERTED_INDEX is None or _DOC_ID_MAP is None:
            # fallback to dummy
            return dummy_search(corpus, search_id, num_results=top_k)

        # Call search_in_corpus from algorithms
        results = search_in_corpus(
            search_query, algo, corpus, _INVERTED_INDEX, _DOC_ID_MAP, top_k=top_k
        )

        # Convert dict results to ResultItem pydantic objects (if you want) or keep as dicts.
        adapted = []
        for r in results:
            # Using ResultItem model (pydantic) is optional; templates accept dicts.
            doc = corpus[r["pid"]]
            try:
                ri = ResultItem(
                    pid=doc.pid,
                    title=doc.title,
                    description=doc.description,
                    url=f"/doc_details?pid={doc.pid}",  # enlace interno
                    ranking=r.get("score"),
                    # Campos extra para mostrar en results.html
                    selling_price=doc.selling_price,
                    discount=doc.discount,
                    average_rating=doc.average_rating,
                    # URL real del producto en la tienda original
                    external_url=doc.url,
                )
                adapted.append(ri)
            except Exception:
                # fallback: keep dict
                adapted.append(r)

        return adapted

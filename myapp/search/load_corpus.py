import pandas as pd

from myapp.search.objects import Document
from typing import List, Dict
import json
from pathlib import Path
from typing import List
from myapp.search.objects import Document
from myapp.core.utils import preprocess_document

import pandas as pd
from typing import List, Dict
from myapp.search.objects import Document
from myapp.core.utils import clean_line


def load_corpus(path) -> Dict[str, Document]:
    """
    Load file and transform into dict(pid -> Document).
    Adds title_tokens and desc_tokens so algorithms can index.
    """
    df = pd.read_json(path)
    corpus = {}

    for _, row in df.iterrows():
        data = row.to_dict()

        # --- ADD TOKENIZATION ---
        title = data.get("title", "")
        desc = data.get("description", "")

        data["title_tokens"] = clean_line(title)
        data["desc_tokens"] = clean_line(desc)

        doc = Document(**data)
        corpus[doc.pid] = doc

    return corpus


def _build_corpus(df: pd.DataFrame) -> Dict[str, Document]:
    """
    Build corpus from dataframe.
    Each row is converted into a Document (Pydantic model).
    We also enrich the Document with:
      - title_tokens
      - desc_tokens
    """
    corpus = {}

    for _, row in df.iterrows():
        data = row.to_dict()

        # Preprocess text BEFORE creating Document
        title = data.get("title", "")
        description = data.get("description", "")

        title_tokens = clean_line(title)
        desc_tokens = clean_line(description)

        # Add tokens to the raw data so Document(**kwargs) accepts them
        data["title_tokens"] = title_tokens
        data["desc_tokens"] = desc_tokens

        # Build the Pydantic object
        doc = Document(**data)

        corpus[doc.pid] = doc

    return corpus

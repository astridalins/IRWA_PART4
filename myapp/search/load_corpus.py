import pandas as pd
import re
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
    Public function.
    Reads JSON file and returns corpus as dict(pid -> Document).
    Internally calls _build_corpus().
    """
    df = pd.read_json(path)
    return _build_corpus(df)


def _build_corpus(df: pd.DataFrame) -> Dict[str, Document]:
    """
    Internal corpus builder.
    Converts each row into a Document object with:
    - title_tokens
    - desc_tokens
    """
    corpus = {}

    for _, row in df.iterrows():
        data = row.to_dict()

        # extract raw text
        title = data.get("title", "") or ""
        desc = data.get("description", "") or ""

        # tokenize using project-wide function
        data["title_tokens"] = clean_line(title)
        data["desc_tokens"] = clean_line(desc)

        # build the Document Pydantic model
        doc = Document(**data)

        corpus[doc.pid] = doc

    return corpus

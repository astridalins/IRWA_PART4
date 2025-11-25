import datetime
from random import random
import re
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from faker import Faker

fake = Faker()

stemmer = PorterStemmer()
stop_words = set(stopwords.words("english"))


def clean_line(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split()
    tokens = [stemmer.stem(w) for w in tokens if w not in stop_words and len(w) > 2]
    return tokens


def preprocess_document(doc):
    for field in ["title", "description"]:
        if field in doc and isinstance(doc[field], str):
            doc[field] = clean_line(doc[field])

    return doc


def get_random_date():
    """Generate a random datetime between `start` and `end`"""
    return fake.date_time_between(start_date="-30d", end_date="now")


def get_random_date_in(start, end):
    """Generate a random datetime between `start` and `end`"""
    return start + datetime.timedelta(
        # Get a random amount of seconds between `start` and `end`
        seconds=random.randint(0, int((end - start).total_seconds())),
    )

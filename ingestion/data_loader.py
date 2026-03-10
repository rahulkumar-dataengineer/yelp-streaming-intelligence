import os
import pandas as pd

from config.settings import settings
from utils.logger import Logger

log = Logger.get(__name__)


def load_business_data() -> pd.DataFrame:
    path = settings.yelp.BUSINESS_JSON_PATH
    log.debug("Loading business data from: %s", path)

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Business JSON not found at: {path} — "
            f"check YELP_BUSINESS_JSON_PATH in your .env file."
        )

    df = pd.read_json(path, lines=True)
    log.debug("Business JSONs loaded into DataFrame — %s rows.", len(df))

    required_cols = {"business_id", "name", "city", "state", "stars", "categories"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Business dataset missing expected columns: {missing}")

    df = (
        df[["business_id", "name", "city", "state", "stars", "categories"]]
        .rename(columns={"stars": "business_stars"})
    )
    df["categories"] = df["categories"].fillna("")

    log.info("Loaded %s businesses.", f"{len(df):,}")
    return df


def load_review_data() -> pd.DataFrame:
    """
    Loads the Yelp review dataset and selects relevant columns.

    Returns:
        DataFrame with columns:
            review_id, business_id, review_stars, review_text, review_date

    Raises:
        FileNotFoundError: If the file does not exist at the configured path.
        ValueError: If required columns are missing from the dataset.
    """
    path = settings.yelp.REVIEW_JSON_PATH
    log.debug("Loading review data from: %s", path)

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Review JSON not found at: {path} — "
            f"check YELP_REVIEW_JSON_PATH in your .env file."
        )

    df = pd.read_json(path, lines=True)
    log.debug("Review JSON read into DataFrame — %s rows.", len(df))

    required_cols = {"review_id", "business_id", "stars", "text", "date"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Review dataset missing expected columns: {missing}")

    df = (
        df[["review_id", "business_id", "stars", "text", "date"]]
        .rename(columns={
            "stars": "review_stars",
            "text":  "review_text",
            "date":  "review_date",
        })
    )
    df["review_date"] = df["review_date"].astype(str)

    log.info("Loaded %s reviews.", f"{len(df):,}")
    return df


def build_joined_dataset() -> pd.DataFrame:
    """
    Loads and inner-joins businesses and reviews on business_id.

    Only reviews with a matching business record are included —
    this guarantees every Kafka message has complete business context.

    Returns:
        Joined DataFrame ready for streaming.
    """
    businesses = load_business_data()
    reviews    = load_review_data()

    log.debug("Merging reviews and businesses on business_id (inner join)...")
    joined = reviews.merge(businesses, on="business_id", how="inner")

    log.info("Joined dataset ready — %s records.", f"{len(joined):,}")
    return joined

"""
Schema artifact package — the internal equivalent of an Artifactory-hosted schema repo.
"""

import json
from importlib.resources import files

_PACKAGE = files(__package__)

BUSINESS_AVRO_SCHEMA: dict = json.loads((_PACKAGE / "yelp_business.avsc").read_text())
REVIEW_AVRO_SCHEMA: dict = json.loads((_PACKAGE / "yelp_review.avsc").read_text())
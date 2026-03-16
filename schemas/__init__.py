"""
Schema artifact package — the internal equivalent of an Artifactory-hosted schema repo.
"""

from platform_commons.kafka import load_avsc

BUSINESS_AVRO_SCHEMA: dict = load_avsc("schemas", "yelp_business.avsc")
REVIEW_AVRO_SCHEMA: dict = load_avsc("schemas", "yelp_review.avsc")

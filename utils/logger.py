"""Project-specific logger — configures platform_commons Logger with this app's root."""

from platform_commons.utils.logger import Logger

Logger.configure("yelp_platform")

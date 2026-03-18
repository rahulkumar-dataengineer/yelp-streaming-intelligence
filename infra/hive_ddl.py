"""
Hive DDL definitions — raw SQL DDL for Metastore table provisioning.

Enterprise standard: platform teams write DDL directly as SQL strings,
version-controlled alongside migration tooling (Flyway, dbt, etc.).
"""


#---------------------------------------------
# BRONZE
# raw landing, all STRING, zero transforms
#---------------------------------------------

BRONZE_BUSINESSES_DDL = """\
CREATE TABLE IF NOT EXISTS {db}.businesses (
    business_id STRING,
    name STRING,
    address STRING,
    city STRING,
    state STRING,
    postal_code STRING,
    latitude STRING,
    longitude STRING,
    stars STRING,
    review_count STRING,
    is_open STRING,
    categories STRING,

    attributes_AcceptsInsurance STRING,
    attributes_Alcohol STRING,
    attributes_Ambience STRING,
    attributes_BYOB STRING,
    attributes_BYOBCorkage STRING,
    attributes_BestNights STRING,
    attributes_BikeParking STRING,
    attributes_BusinessAcceptsBitcoin STRING,
    attributes_BusinessAcceptsCreditCards STRING,
    attributes_BusinessParking STRING,
    attributes_ByAppointmentOnly STRING,
    attributes_Caters STRING,
    attributes_CoatCheck STRING,
    attributes_Corkage STRING,
    attributes_DogsAllowed STRING,
    attributes_DriveThru STRING,
    attributes_GoodForDancing STRING,
    attributes_GoodForKids STRING,
    attributes_GoodForMeal STRING,
    attributes_HairSpecializesIn STRING,
    attributes_HappyHour STRING,
    attributes_HasTV STRING,
    attributes_Music STRING,
    attributes_NoiseLevel STRING,
    attributes_Open24Hours STRING,
    attributes_OutdoorSeating STRING,
    attributes_RestaurantsAttire STRING,
    attributes_RestaurantsCounterService STRING,
    attributes_RestaurantsDelivery STRING,
    attributes_RestaurantsGoodForGroups STRING,
    attributes_RestaurantsPriceRange2 STRING,
    attributes_RestaurantsReservations STRING,
    attributes_RestaurantsTableService STRING,
    attributes_RestaurantsTakeOut STRING,
    attributes_Smoking STRING,
    attributes_WheelchairAccessible STRING,
    attributes_WiFi STRING,

    hours_Monday STRING,
    hours_Tuesday STRING,
    hours_Wednesday STRING,
    hours_Thursday STRING,
    hours_Friday STRING,
    hours_Saturday STRING,
    hours_Sunday STRING,

    ingestion_timestamp STRING
)
USING parquet
PARTITIONED BY (ingestion_date STRING)
"""

BRONZE_REVIEWS_DDL = """\
CREATE TABLE IF NOT EXISTS {db}.reviews (
    review_id STRING,
    user_id STRING,
    business_id STRING,
    stars STRING,
    useful STRING,
    funny STRING,
    cool STRING,
    text STRING,
    date STRING,

    ingestion_timestamp STRING
)
USING parquet
PARTITIONED BY (ingestion_date STRING)
"""


#---------------------------------
# SILVER — typed, cleaned, joined
#---------------------------------

SILVER_REVIEWS_DDL = """\
CREATE TABLE IF NOT EXISTS {db}.reviews (
    business_id STRING,
    name STRING,
    address STRING,
    city STRING,
    postal_code STRING,
    business_stars FLOAT,
    review_count INT,
    is_open BOOLEAN,
    categories STRING,

    bike_parking BOOLEAN,
    business_accepts_bitcoin BOOLEAN,
    business_accepts_credit_cards BOOLEAN,
    by_appointment_only BOOLEAN,
    byob BOOLEAN,
    caters BOOLEAN,
    dogs_allowed BOOLEAN,
    drive_thru BOOLEAN,
    good_for_dancing BOOLEAN,
    good_for_kids BOOLEAN,
    happy_hour BOOLEAN,
    has_tv BOOLEAN,
    open_24_hours BOOLEAN,
    outdoor_seating BOOLEAN,
    restaurants_delivery BOOLEAN,
    restaurants_good_for_groups BOOLEAN,
    restaurants_reservations BOOLEAN,
    restaurants_table_service BOOLEAN,
    restaurants_take_out BOOLEAN,
    wheelchair_accessible BOOLEAN,

    parking_garage BOOLEAN,
    parking_street BOOLEAN,
    parking_validated BOOLEAN,
    parking_lot BOOLEAN,
    parking_valet BOOLEAN,

    music_dj BOOLEAN,
    music_background BOOLEAN,
    music_no_music BOOLEAN,
    music_jukebox BOOLEAN,
    music_live BOOLEAN,
    music_video BOOLEAN,
    music_karaoke BOOLEAN,

    alcohol STRING,
    noise_level STRING,
    restaurants_attire STRING,
    smoking STRING,
    wifi STRING,

    restaurants_price_range INT,

    hours_monday STRING,
    hours_tuesday STRING,
    hours_wednesday STRING,
    hours_thursday STRING,
    hours_friday STRING,
    hours_saturday STRING,
    hours_sunday STRING,

    review_id STRING,
    user_id STRING,
    review_stars INT,
    useful INT,
    funny INT,
    cool INT,
    text STRING,
    date TIMESTAMP,

    ingestion_timestamp TIMESTAMP
)
USING parquet
PARTITIONED BY (state STRING, ingestion_date DATE)
"""


#---------------------------------
# SILVER — quarantine (raw review columns + reason)
#---------------------------------

SILVER_QUARANTINE_DDL = """\
CREATE TABLE IF NOT EXISTS {db}.quarantine (
    review_id STRING,
    user_id STRING,
    business_id STRING,
    stars STRING,
    useful STRING,
    funny STRING,
    cool STRING,
    text STRING,
    date STRING,
    reason STRING,
    quarantine_timestamp TIMESTAMP
)
USING parquet
PARTITIONED BY (ingestion_date STRING)
"""

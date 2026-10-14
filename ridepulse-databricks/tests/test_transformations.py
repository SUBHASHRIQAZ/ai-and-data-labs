from datetime import datetime

from transformations import add_zone_names, clean_trips, enrich_trips

BASE_ROW = {
    "hvfhs_license_num": "HV0003",
    "dispatching_base_num": "B0001",
    "pickup_datetime": datetime(2026, 1, 15, 10, 0, 0),
    "dropoff_datetime": datetime(2026, 1, 15, 10, 20, 0),
    "PULocationID": 100,
    "DOLocationID": 200,
    "trip_miles": 5.0,
    "base_passenger_fare": 20.0,
}


def trips_df(spark, rows):
    return spark.createDataFrame([{**BASE_ROW, **row} for row in rows])


def test_clean_trips_drops_null_pickup_and_dropoff(spark):
    df = trips_df(spark, [{}, {"pickup_datetime": None}, {"DOLocationID": None}])
    result = clean_trips(df)
    assert result.count() == 1


def test_clean_trips_drops_negative_fare(spark):
    df = trips_df(spark, [{}, {"base_passenger_fare": -5.0}])
    result = clean_trips(df)
    assert result.count() == 1


def test_clean_trips_drops_zero_distance(spark):
    df = trips_df(spark, [{}, {"trip_miles": 0.0}])
    result = clean_trips(df)
    assert result.count() == 1


def test_clean_trips_drops_invalid_timestamps(spark):
    df = trips_df(
        spark,
        [
            {},
            {
                "pickup_datetime": datetime(2026, 1, 15, 10, 0, 0),
                "dropoff_datetime": datetime(2026, 1, 15, 9, 0, 0),
            },
        ],
    )
    result = clean_trips(df)
    assert result.count() == 1


def test_clean_trips_dedupes_identical_trips(spark):
    df = trips_df(spark, [{}, {}])
    result = clean_trips(df)
    assert result.count() == 1


def test_enrich_trips_adds_derived_columns(spark):
    df = trips_df(spark, [{}])
    result = enrich_trips(df).collect()[0]

    assert result["pickup_date"] == datetime(2026, 1, 15).date()
    assert result["pickup_hour"] == 10
    assert result["trip_duration_minutes"] == 20.0
    # 5 miles in 20 minutes = 15 mph
    assert result["average_speed"] == 15.0


def test_enrich_trips_drops_unrealistic_duration(spark):
    df = trips_df(
        spark,
        [
            {},
            {
                "pickup_datetime": datetime(2026, 1, 15, 8, 0, 0),
                "dropoff_datetime": datetime(2026, 1, 15, 14, 0, 0),
            },
        ],
    )
    result = enrich_trips(df, max_trip_duration_minutes=180)
    assert result.count() == 1
    assert result.collect()[0]["trip_duration_minutes"] == 20.0


def test_add_zone_names_joins_pickup_and_dropoff_zones(spark):
    df = trips_df(spark, [{}])
    zone_lookup = spark.createDataFrame(
        [(100, "Midtown"), (200, "JFK Airport")], ["LocationID", "Zone"]
    )

    result = add_zone_names(df, zone_lookup).collect()[0]

    assert result["pickup_zone"] == "Midtown"
    assert result["dropoff_zone"] == "JFK Airport"


def test_add_zone_names_unmatched_location_is_null(spark):
    df = trips_df(spark, [{"PULocationID": 999}])
    zone_lookup = spark.createDataFrame(
        [(100, "Midtown"), (200, "JFK Airport")], ["LocationID", "Zone"]
    )

    result = add_zone_names(df, zone_lookup).collect()[0]

    assert result["pickup_zone"] is None

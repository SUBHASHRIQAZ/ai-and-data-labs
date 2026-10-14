# Data Dictionary — HVFHV Trip Records

Source columns as published by NYC TLC for High Volume For-Hire Vehicle trip
records. See the official data dictionary for the authoritative, current
definitions: https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_hvfhs.pdf

| Column | Type | Description |
|---|---|---|
| `hvfhs_license_num` | string | TLC license number of the HVFHV base (e.g. Uber, Lyft) |
| `dispatching_base_num` | string | TLC base license number that dispatched the trip |
| `originating_base_num` | string | Base that received the original trip request |
| `request_datetime` | timestamp | Time the passenger requested the trip |
| `on_scene_datetime` | timestamp | Time the driver arrived at the pickup location |
| `pickup_datetime` | timestamp | Trip start time |
| `dropoff_datetime` | timestamp | Trip end time |
| `PULocationID` | int | TLC Taxi Zone ID for pickup |
| `DOLocationID` | int | TLC Taxi Zone ID for drop-off |
| `trip_miles` | double | Trip distance in miles |
| `trip_time` | int | Trip duration in seconds |
| `base_passenger_fare` | double | Base fare before tolls, tips, taxes, fees |
| `tolls` | double | Total tolls charged |
| `bcf` | double | Black Car Fund surcharge |
| `sales_tax` | double | Sales tax charged |
| `congestion_surcharge` | double | NY congestion surcharge |
| `airport_fee` | double | Airport pickup/drop-off fee, where applicable |
| `tips` | double | Tip amount |
| `driver_pay` | double | Total driver pay for the trip |
| `shared_request_flag` | string (Y/N) | Whether the passenger agreed to a shared/pooled ride |
| `shared_match_flag` | string (Y/N) | Whether the trip was actually shared with another passenger |
| `access_a_ride_flag` | string (Y/N) | Whether the trip was administered by NYC's Access-a-Ride program |
| `wav_request_flag` | string (Y/N) | Whether the passenger requested a wheelchair-accessible vehicle |
| `wav_match_flag` | string (Y/N) | Whether the trip was completed in a wheelchair-accessible vehicle |

## Derived columns (Silver / Gold)

| Column | Derived from | Description |
|---|---|---|
| `pickup_date` | `pickup_datetime` | Calendar date of pickup |
| `pickup_hour` | `pickup_datetime` | Hour of day (0–23) of pickup |
| `day_of_week` | `pickup_datetime` | Day of week of pickup |
| `trip_duration_minutes` | `dropoff_datetime` − `pickup_datetime` | Trip duration in minutes |
| `average_speed` | `trip_miles` / `trip_duration_minutes` | Average trip speed |
| `pickup_zone` / `dropoff_zone` | `PULocationID` / `DOLocationID` joined against the TLC Taxi Zone lookup table | Human-readable zone name |

Note: the TLC Taxi Zone lookup table (`taxi_zone_lookup.csv`) is a separate,
small reference file from the same TLC data page — download it alongside the
trip data to resolve zone names.

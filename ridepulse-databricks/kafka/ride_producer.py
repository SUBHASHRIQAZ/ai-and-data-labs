"""Ride-event Kafka producer.

Replays downloaded TLC HVFHV trip data as a stream of JSON ride events onto
a Kafka topic, simulating a live ride-hailing event feed:

    {
      "trip_id": "0000123456",
      "pickup_time": "2026-01-15T10:25:12",
      "pickup_zone": "Midtown",
      "dropoff_zone": "JFK Airport",
      "distance": 8.7,
      "fare": 32.5
    }

Only build/run this after Phase 1 (batch) and Phase 2 (Auto Loader /
Structured Streaming) are working. Databricks Free Edition restricts
outbound internet access, so this producer is meant to run *outside*
Databricks (e.g. on your laptop) against a Kafka broker that Databricks can
read from.

Usage:
    pip install -r kafka/requirements.txt
    python kafka/ride_producer.py \
        --source-path /path/to/fhvhv_tripdata_2026-01.parquet \
        --bootstrap-servers localhost:9092 \
        --topic ride-events \
        --rate 5

HVFHV has no trip ID column, so one is synthesized from the row's position
in the source file. `pickup_zone`/`dropoff_zone` are resolved via the TLC
taxi zone lookup CSV when `--zone-lookup-path` is given; otherwise the raw
location IDs are sent instead.

`--duplicate-rate` and `--late-rate` exist so the watermark/dedup logic in
`07_kafka_streaming_ingestion.py` has something real to do — without them
every event is unique and on time, and that notebook's `dropDuplicates` /
`withWatermark` calls would just be dead code you'd have to take on faith.
With `--late-rate 0.1 --late-minutes 20` and a consumer watermark of 10
minutes, roughly 1 in 10 events arrive backdated far enough to get dropped
by the watermark instead of processed — you can watch that happen in
`ridepulse.bronze.ride_events`.
"""

import argparse
import json
import random
import time
from datetime import datetime, timedelta

import pandas as pd
from kafka import KafkaProducer


def load_trips(source_path: str, zone_lookup_path: str | None, limit: int | None) -> pd.DataFrame:
    trips = pd.read_parquet(
        source_path,
        columns=["pickup_datetime", "dropoff_datetime", "PULocationID", "DOLocationID",
                 "trip_miles", "base_passenger_fare"],
    )
    trips = trips.sort_values("pickup_datetime").reset_index(drop=True)
    trips["trip_id"] = trips.index.map(lambda i: f"{i:010d}")

    if zone_lookup_path:
        zones = pd.read_csv(zone_lookup_path)[["LocationID", "Zone"]]
        trips = trips.merge(zones.rename(columns={"LocationID": "PULocationID", "Zone": "pickup_zone"}),
                             on="PULocationID", how="left")
        trips = trips.merge(zones.rename(columns={"LocationID": "DOLocationID", "Zone": "dropoff_zone"}),
                             on="DOLocationID", how="left")
    else:
        trips["pickup_zone"] = trips["PULocationID"]
        trips["dropoff_zone"] = trips["DOLocationID"]

    if limit:
        trips = trips.head(limit)

    return trips


def to_event(row: pd.Series) -> dict:
    return {
        "trip_id": row["trip_id"],
        "pickup_time": row["pickup_datetime"].isoformat(),
        "pickup_zone": row["pickup_zone"],
        "dropoff_zone": row["dropoff_zone"],
        "distance": float(row["trip_miles"]),
        "fare": float(row["base_passenger_fare"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay TLC HVFHV trips as Kafka ride events.")
    parser.add_argument("--source-path", required=True, help="Path to a downloaded HVFHV parquet file")
    parser.add_argument("--zone-lookup-path", default=None, help="Path to taxi_zone_lookup.csv (optional)")
    parser.add_argument("--bootstrap-servers", default="localhost:9092")
    parser.add_argument("--topic", default="ride-events")
    parser.add_argument("--rate", type=float, default=5.0, help="Events per second")
    parser.add_argument("--limit", type=int, default=None, help="Max number of events to send")
    parser.add_argument(
        "--duplicate-rate", type=float, default=0.0,
        help="Probability (0-1) of resending the previous event right after the current one, "
             "simulating a producer retry that Kafka's at-least-once delivery allows",
    )
    parser.add_argument(
        "--late-rate", type=float, default=0.0,
        help="Probability (0-1) of backdating an event's pickup_time before sending it, "
             "simulating an event that arrives out of order",
    )
    parser.add_argument("--late-minutes", type=float, default=20.0, help="How far back to backdate a late event")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible duplicate/late injection")
    args = parser.parse_args()

    trips = load_trips(args.source_path, args.zone_lookup_path, args.limit)
    print(f"Loaded {len(trips):,} trips from {args.source_path}")

    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    rng = random.Random(args.seed)
    delay = 1.0 / args.rate
    previous_event = None

    for _, row in trips.iterrows():
        event = to_event(row)

        if args.late_rate and rng.random() < args.late_rate:
            backdated = datetime.fromisoformat(event["pickup_time"]) - timedelta(minutes=args.late_minutes)
            event["pickup_time"] = backdated.isoformat()
            print(f"[late, -{args.late_minutes:.0f}min]", event)
        else:
            print(event)

        producer.send(args.topic, value=event)

        if previous_event is not None and args.duplicate_rate and rng.random() < args.duplicate_rate:
            print("[duplicate]", previous_event)
            producer.send(args.topic, value=previous_event)

        previous_event = event
        time.sleep(delay)

    producer.flush()
    print("Done.")


if __name__ == "__main__":
    main()

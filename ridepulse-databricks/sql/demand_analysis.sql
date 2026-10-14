-- Demand analysis: busiest zones, highest-demand hours, weekday vs weekend.

-- Busiest pickup zones overall
SELECT pickup_zone, SUM(trip_count) AS total_trips
FROM ridepulse.gold.hourly_demand
GROUP BY pickup_zone
ORDER BY total_trips DESC
LIMIT 20;

-- Highest-demand hours of day
SELECT pickup_hour, SUM(trip_count) AS total_trips
FROM ridepulse.gold.hourly_demand
GROUP BY pickup_hour
ORDER BY pickup_hour;

-- Weekday vs weekend demand (day_of_week: 1 = Sunday ... 7 = Saturday)
SELECT
  CASE WHEN dayofweek(pickup_date) IN (1, 7) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
  SUM(trip_count) AS total_trips
FROM ridepulse.gold.hourly_demand
GROUP BY day_type;

-- Peak demand buckets by zone
SELECT zone, demand_level, COUNT(*) AS bucket_count
FROM ridepulse.gold.peak_demand
GROUP BY zone, demand_level
ORDER BY zone, demand_level;

-- Dashboard queries backing a Databricks SQL dashboard summarizing
-- gold.trip_kpis, gold.hourly_demand, gold.zone_revenue, and gold.peak_demand.

-- Headline KPIs (latest date)
SELECT *
FROM ridepulse.gold.trip_kpis
ORDER BY date DESC
LIMIT 1;

-- KPI trend over time
SELECT date, total_trips, total_revenue, average_fare, average_distance, average_duration
FROM ridepulse.gold.trip_kpis
ORDER BY date;

-- Top 10 busiest zones (latest date)
SELECT pickup_zone, trip_count
FROM ridepulse.gold.hourly_demand
WHERE pickup_date = (SELECT MAX(pickup_date) FROM ridepulse.gold.hourly_demand)
ORDER BY trip_count DESC
LIMIT 10;

-- Top 10 revenue zones (latest date)
SELECT pickup_zone, total_revenue
FROM ridepulse.gold.zone_revenue
WHERE pickup_date = (SELECT MAX(pickup_date) FROM ridepulse.gold.zone_revenue)
ORDER BY total_revenue DESC
LIMIT 10;

-- Demand heatmap: hour x zone trip counts (latest date)
SELECT hour, zone, trip_count, demand_level
FROM ridepulse.gold.peak_demand
WHERE date = (SELECT MAX(date) FROM ridepulse.gold.peak_demand)
ORDER BY hour, trip_count DESC;

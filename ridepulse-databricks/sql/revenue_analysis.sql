-- Revenue analysis: top-earning zones, fare/tip trends.

-- Top revenue-generating zones
SELECT pickup_zone, SUM(total_revenue) AS total_revenue, SUM(trip_count) AS total_trips
FROM ridepulse.gold.zone_revenue
GROUP BY pickup_zone
ORDER BY total_revenue DESC
LIMIT 20;

-- Average fare and tip by zone
SELECT pickup_zone, ROUND(AVG(average_fare), 2) AS avg_fare, ROUND(AVG(average_tip), 2) AS avg_tip
FROM ridepulse.gold.zone_revenue
GROUP BY pickup_zone
ORDER BY avg_fare DESC
LIMIT 20;

-- Daily revenue trend
SELECT pickup_date, SUM(total_revenue) AS total_revenue
FROM ridepulse.gold.zone_revenue
GROUP BY pickup_date
ORDER BY pickup_date;

-- Top revenue zone per day (revenue_rank is precomputed in the Gold notebook
-- with a window function, so this is just a filter, not a recompute)
SELECT pickup_date, pickup_zone, total_revenue
FROM ridepulse.gold.zone_revenue
WHERE revenue_rank = 1
ORDER BY pickup_date;

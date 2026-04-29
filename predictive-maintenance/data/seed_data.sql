-- ============================================================
-- Air India Predictive Maintenance - Lakebase Seed Data
-- ============================================================

-- Drop tables if they exist (for re-seeding)
DROP TABLE IF EXISTS anomaly_alerts CASCADE;
DROP TABLE IF EXISTS hangar_availability CASCADE;
DROP TABLE IF EXISTS flight_schedule CASCADE;
DROP TABLE IF EXISTS component_lifecycle CASCADE;
DROP TABLE IF EXISTS parts_inventory CASCADE;
DROP TABLE IF EXISTS maintenance_history CASCADE;
DROP TABLE IF EXISTS sensor_telemetry CASCADE;
DROP TABLE IF EXISTS aircraft_fleet CASCADE;

-- ============================================================
-- 1. AIRCRAFT FLEET
-- ============================================================
CREATE TABLE aircraft_fleet (
    aircraft_reg VARCHAR(10) PRIMARY KEY,
    aircraft_type VARCHAR(50) NOT NULL,
    engine_type VARCHAR(30) NOT NULL,
    total_flight_hours INTEGER NOT NULL,
    total_cycles INTEGER NOT NULL,
    last_heavy_check DATE,
    base_station VARCHAR(5) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'OPERATIONAL'
);

INSERT INTO aircraft_fleet VALUES
('VT-ALJ', 'Boeing 787-9 Dreamliner', 'GEnx-1B', 32500, 8200, '2025-08-15', 'DEL', 'OPERATIONAL'),
('VT-ANA', 'Airbus A321neo', 'CFM LEAP-1A', 18700, 12400, '2025-11-20', 'DEL', 'OPERATIONAL'),
('VT-ALQ', 'Boeing 777-300ER', 'GE90-115B', 45200, 11800, '2025-06-10', 'BOM', 'OPERATIONAL'),
('VT-ANE', 'Airbus A350-900', 'Trent XWB', 12300, 4100, '2026-01-05', 'DEL', 'OPERATIONAL'),
('VT-ANP', 'Boeing 787-9 Dreamliner', 'GEnx-1B', 28900, 7500, '2025-09-22', 'BLR', 'OPERATIONAL'),
('VT-ALM', 'Airbus A321neo', 'CFM LEAP-1A', 22100, 14800, '2025-07-18', 'BOM', 'OPERATIONAL'),
('VT-ANG', 'Boeing 777-300ER', 'GE90-115B', 51000, 13200, '2025-04-30', 'DEL', 'IN_MAINTENANCE'),
('VT-ANR', 'Airbus A350-900', 'Trent XWB', 9800, 3200, '2026-02-14', 'MAA', 'OPERATIONAL'),
('VT-ALK', 'Boeing 787-9 Dreamliner', 'GEnx-1B', 35600, 9100, '2025-05-25', 'DEL', 'OPERATIONAL'),
('VT-ANB', 'Airbus A321neo', 'CFM LEAP-1A', 16500, 11000, '2025-12-08', 'HYD', 'OPERATIONAL'),
('VT-ALC', 'Boeing 777-300ER', 'GE90-115B', 48300, 12500, '2025-07-01', 'BOM', 'OPERATIONAL'),
('VT-AND', 'Airbus A350-900', 'Trent XWB', 14200, 4700, '2025-10-15', 'DEL', 'OPERATIONAL'),
('VT-ANF', 'Boeing 787-9 Dreamliner', 'GEnx-1B', 30100, 7800, '2025-08-03', 'BLR', 'OPERATIONAL'),
('VT-ANH', 'Airbus A321neo', 'CFM LEAP-1A', 20400, 13600, '2025-09-11', 'MAA', 'OPERATIONAL'),
('VT-ANK', 'Boeing 777-300ER', 'GE90-115B', 42700, 11100, '2025-06-20', 'DEL', 'OPERATIONAL');

-- ============================================================
-- 2. SENSOR TELEMETRY
-- ============================================================
CREATE TABLE sensor_telemetry (
    telemetry_id SERIAL PRIMARY KEY,
    aircraft_reg VARCHAR(10) NOT NULL REFERENCES aircraft_fleet(aircraft_reg),
    sensor_type VARCHAR(30) NOT NULL,
    engine_position VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    value DECIMAL(10,3) NOT NULL,
    unit VARCHAR(10) NOT NULL,
    normal_min DECIMAL(10,3) NOT NULL,
    normal_max DECIMAL(10,3) NOT NULL,
    anomaly_score DECIMAL(4,3) NOT NULL DEFAULT 0.0
);

-- ============================================================
-- VT-ALJ Engine #2 DEGRADING TREND (the star demo scenario)
-- N2 Vibration: 2.1 -> 3.8 mm/s over 7 days (normal 0.5-3.0)
-- Oil Temp: 85 -> 112 C (normal 70-100)
-- EGT: 850 -> 920 C (normal 750-900)
-- ============================================================

-- Day 1 (7 days ago) - VT-ALJ Engine 2
INSERT INTO sensor_telemetry (aircraft_reg, sensor_type, engine_position, timestamp, value, unit, normal_min, normal_max, anomaly_score) VALUES
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '0 hours', 2.100, 'mm/s', 0.500, 3.000, 0.15),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '4 hours', 2.150, 'mm/s', 0.500, 3.000, 0.16),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '8 hours', 2.180, 'mm/s', 0.500, 3.000, 0.17),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '12 hours', 2.200, 'mm/s', 0.500, 3.000, 0.18),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '16 hours', 2.220, 'mm/s', 0.500, 3.000, 0.18),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '20 hours', 2.250, 'mm/s', 0.500, 3.000, 0.19),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '0 hours', 85.000, 'C', 70.000, 100.000, 0.10),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '8 hours', 86.200, 'C', 70.000, 100.000, 0.11),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '16 hours', 87.000, 'C', 70.000, 100.000, 0.12),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '0 hours', 850.000, 'C', 750.000, 900.000, 0.12),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '8 hours', 853.000, 'C', 750.000, 900.000, 0.13),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '7 days' + INTERVAL '16 hours', 856.000, 'C', 750.000, 900.000, 0.13),
-- Day 2
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '0 hours', 2.300, 'mm/s', 0.500, 3.000, 0.22),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '4 hours', 2.350, 'mm/s', 0.500, 3.000, 0.24),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '8 hours', 2.380, 'mm/s', 0.500, 3.000, 0.25),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '12 hours', 2.420, 'mm/s', 0.500, 3.000, 0.27),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '16 hours', 2.450, 'mm/s', 0.500, 3.000, 0.28),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '20 hours', 2.500, 'mm/s', 0.500, 3.000, 0.30),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '0 hours', 88.500, 'C', 70.000, 100.000, 0.15),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '8 hours', 89.800, 'C', 70.000, 100.000, 0.17),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '16 hours', 91.200, 'C', 70.000, 100.000, 0.19),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '0 hours', 860.000, 'C', 750.000, 900.000, 0.18),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '8 hours', 864.000, 'C', 750.000, 900.000, 0.19),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '6 days' + INTERVAL '16 hours', 868.000, 'C', 750.000, 900.000, 0.20),
-- Day 3
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '0 hours', 2.550, 'mm/s', 0.500, 3.000, 0.35),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '4 hours', 2.600, 'mm/s', 0.500, 3.000, 0.38),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '8 hours', 2.650, 'mm/s', 0.500, 3.000, 0.40),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '12 hours', 2.700, 'mm/s', 0.500, 3.000, 0.42),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '16 hours', 2.750, 'mm/s', 0.500, 3.000, 0.45),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '20 hours', 2.800, 'mm/s', 0.500, 3.000, 0.48),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '0 hours', 93.000, 'C', 70.000, 100.000, 0.28),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '8 hours', 94.500, 'C', 70.000, 100.000, 0.32),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '16 hours', 96.200, 'C', 70.000, 100.000, 0.36),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '0 hours', 873.000, 'C', 750.000, 900.000, 0.30),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '8 hours', 878.000, 'C', 750.000, 900.000, 0.33),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '5 days' + INTERVAL '16 hours', 882.000, 'C', 750.000, 900.000, 0.36),
-- Day 4
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '0 hours', 2.850, 'mm/s', 0.500, 3.000, 0.52),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '4 hours', 2.900, 'mm/s', 0.500, 3.000, 0.55),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '8 hours', 2.950, 'mm/s', 0.500, 3.000, 0.58),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '12 hours', 3.000, 'mm/s', 0.500, 3.000, 0.62),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '16 hours', 3.050, 'mm/s', 0.500, 3.000, 0.65),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '20 hours', 3.100, 'mm/s', 0.500, 3.000, 0.68),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '0 hours', 98.000, 'C', 70.000, 100.000, 0.48),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '8 hours', 99.500, 'C', 70.000, 100.000, 0.52),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '16 hours', 101.200, 'C', 70.000, 100.000, 0.58),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '0 hours', 887.000, 'C', 750.000, 900.000, 0.45),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '8 hours', 891.000, 'C', 750.000, 900.000, 0.48),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '4 days' + INTERVAL '16 hours', 895.000, 'C', 750.000, 900.000, 0.52),
-- Day 5
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '0 hours', 3.150, 'mm/s', 0.500, 3.000, 0.70),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '4 hours', 3.200, 'mm/s', 0.500, 3.000, 0.72),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '8 hours', 3.280, 'mm/s', 0.500, 3.000, 0.74),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '12 hours', 3.320, 'mm/s', 0.500, 3.000, 0.76),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '16 hours', 3.380, 'mm/s', 0.500, 3.000, 0.78),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '20 hours', 3.420, 'mm/s', 0.500, 3.000, 0.80),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '0 hours', 103.500, 'C', 70.000, 100.000, 0.65),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '8 hours', 105.200, 'C', 70.000, 100.000, 0.70),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '16 hours', 107.000, 'C', 70.000, 100.000, 0.74),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '0 hours', 900.000, 'C', 750.000, 900.000, 0.60),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '8 hours', 904.000, 'C', 750.000, 900.000, 0.65),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '3 days' + INTERVAL '16 hours', 908.000, 'C', 750.000, 900.000, 0.70),
-- Day 6
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '0 hours', 3.450, 'mm/s', 0.500, 3.000, 0.82),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '4 hours', 3.500, 'mm/s', 0.500, 3.000, 0.83),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '8 hours', 3.550, 'mm/s', 0.500, 3.000, 0.84),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '12 hours', 3.580, 'mm/s', 0.500, 3.000, 0.85),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '16 hours', 3.620, 'mm/s', 0.500, 3.000, 0.86),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '20 hours', 3.650, 'mm/s', 0.500, 3.000, 0.87),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '0 hours', 108.500, 'C', 70.000, 100.000, 0.78),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '8 hours', 109.800, 'C', 70.000, 100.000, 0.80),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '16 hours', 110.500, 'C', 70.000, 100.000, 0.82),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '0 hours', 912.000, 'C', 750.000, 900.000, 0.75),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '8 hours', 915.000, 'C', 750.000, 900.000, 0.78),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '2 days' + INTERVAL '16 hours', 917.000, 'C', 750.000, 900.000, 0.80),
-- Day 7 (today) - CRITICAL readings
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '1 day' + INTERVAL '0 hours', 3.680, 'mm/s', 0.500, 3.000, 0.88),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '1 day' + INTERVAL '4 hours', 3.720, 'mm/s', 0.500, 3.000, 0.89),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '1 day' + INTERVAL '8 hours', 3.750, 'mm/s', 0.500, 3.000, 0.90),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '1 day' + INTERVAL '12 hours', 3.780, 'mm/s', 0.500, 3.000, 0.91),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '16 hours', 3.800, 'mm/s', 0.500, 3.000, 0.92),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', NOW() - INTERVAL '8 hours', 3.800, 'mm/s', 0.500, 3.000, 0.93),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '1 day' + INTERVAL '0 hours', 111.000, 'C', 70.000, 100.000, 0.85),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '1 day' + INTERVAL '8 hours', 111.500, 'C', 70.000, 100.000, 0.87),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '8 hours', 112.000, 'C', 70.000, 100.000, 0.89),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '1 day' + INTERVAL '0 hours', 918.000, 'C', 750.000, 900.000, 0.83),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '1 day' + INTERVAL '8 hours', 919.000, 'C', 750.000, 900.000, 0.85),
('VT-ALJ', 'EGT', 'ENGINE_2', NOW() - INTERVAL '8 hours', 920.000, 'C', 750.000, 900.000, 0.88);

-- VT-ALJ Engine 1 (NORMAL readings for contrast)
INSERT INTO sensor_telemetry (aircraft_reg, sensor_type, engine_position, timestamp, value, unit, normal_min, normal_max, anomaly_score) VALUES
('VT-ALJ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.200, 'mm/s', 0.500, 3.000, 0.05),
('VT-ALJ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '6 days', 1.180, 'mm/s', 0.500, 3.000, 0.04),
('VT-ALJ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '5 days', 1.220, 'mm/s', 0.500, 3.000, 0.05),
('VT-ALJ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '4 days', 1.190, 'mm/s', 0.500, 3.000, 0.04),
('VT-ALJ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '3 days', 1.210, 'mm/s', 0.500, 3.000, 0.05),
('VT-ALJ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '2 days', 1.230, 'mm/s', 0.500, 3.000, 0.05),
('VT-ALJ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.200, 'mm/s', 0.500, 3.000, 0.04),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.350, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '6 days', 1.340, 'mm/s', 0.500, 3.000, 0.05),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '5 days', 1.360, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '4 days', 1.330, 'mm/s', 0.500, 3.000, 0.05),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '3 days', 1.350, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '2 days', 1.370, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.340, 'mm/s', 0.500, 3.000, 0.05),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 82.000, 'C', 70.000, 100.000, 0.04),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '5 days', 83.500, 'C', 70.000, 100.000, 0.05),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '3 days', 82.800, 'C', 70.000, 100.000, 0.04),
('VT-ALJ', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 83.200, 'C', 70.000, 100.000, 0.05),
('VT-ALJ', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 835.000, 'C', 750.000, 900.000, 0.06),
('VT-ALJ', 'EGT', 'ENGINE_1', NOW() - INTERVAL '5 days', 838.000, 'C', 750.000, 900.000, 0.07),
('VT-ALJ', 'EGT', 'ENGINE_1', NOW() - INTERVAL '3 days', 836.000, 'C', 750.000, 900.000, 0.06),
('VT-ALJ', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 837.000, 'C', 750.000, 900.000, 0.06),
('VT-ALJ', 'OIL_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '7 days', 45.000, 'PSI', 35.000, 55.000, 0.03),
('VT-ALJ', 'OIL_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '3 days', 44.500, 'PSI', 35.000, 55.000, 0.03),
('VT-ALJ', 'OIL_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '1 day', 45.200, 'PSI', 35.000, 55.000, 0.03),
('VT-ALJ', 'OIL_PRESSURE', 'ENGINE_2', NOW() - INTERVAL '7 days', 44.000, 'PSI', 35.000, 55.000, 0.04),
('VT-ALJ', 'OIL_PRESSURE', 'ENGINE_2', NOW() - INTERVAL '3 days', 43.200, 'PSI', 35.000, 55.000, 0.05),
('VT-ALJ', 'OIL_PRESSURE', 'ENGINE_2', NOW() - INTERVAL '1 day', 42.500, 'PSI', 35.000, 55.000, 0.08),
('VT-ALJ', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '7 days', 3050.000, 'PSI', 2800.000, 3200.000, 0.03),
('VT-ALJ', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '3 days', 3020.000, 'PSI', 2800.000, 3200.000, 0.03),
('VT-ALJ', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '1 day', 3040.000, 'PSI', 2800.000, 3200.000, 0.03),
('VT-ALJ', 'FUEL_FLOW', 'ENGINE_1', NOW() - INTERVAL '7 days', 2800.000, 'kg/h', 2200.000, 3500.000, 0.04),
('VT-ALJ', 'FUEL_FLOW', 'ENGINE_1', NOW() - INTERVAL '3 days', 2850.000, 'kg/h', 2200.000, 3500.000, 0.04),
('VT-ALJ', 'FUEL_FLOW', 'ENGINE_1', NOW() - INTERVAL '1 day', 2820.000, 'kg/h', 2200.000, 3500.000, 0.04),
('VT-ALJ', 'FUEL_FLOW', 'ENGINE_2', NOW() - INTERVAL '7 days', 2900.000, 'kg/h', 2200.000, 3500.000, 0.05),
('VT-ALJ', 'FUEL_FLOW', 'ENGINE_2', NOW() - INTERVAL '3 days', 3050.000, 'kg/h', 2200.000, 3500.000, 0.10),
('VT-ALJ', 'FUEL_FLOW', 'ENGINE_2', NOW() - INTERVAL '1 day', 3150.000, 'kg/h', 2200.000, 3500.000, 0.15),
('VT-ALJ', 'BLEED_AIR_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 220.000, 'C', 180.000, 260.000, 0.03),
('VT-ALJ', 'BLEED_AIR_TEMP', 'ENGINE_1', NOW() - INTERVAL '3 days', 222.000, 'C', 180.000, 260.000, 0.03),
('VT-ALJ', 'BLEED_AIR_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 221.000, 'C', 180.000, 260.000, 0.03);

-- ============================================================
-- VT-ANP HYDRAULIC ISSUE - Pressure dropping over 3 days
-- ============================================================
INSERT INTO sensor_telemetry (aircraft_reg, sensor_type, engine_position, timestamp, value, unit, normal_min, normal_max, anomaly_score) VALUES
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '7 days', 3100.000, 'PSI', 2800.000, 3200.000, 0.05),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '6 days', 3080.000, 'PSI', 2800.000, 3200.000, 0.05),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '5 days', 3050.000, 'PSI', 2800.000, 3200.000, 0.06),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '4 days', 3000.000, 'PSI', 2800.000, 3200.000, 0.08),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '3 days' + INTERVAL '0 hours', 2900.000, 'PSI', 2800.000, 3200.000, 0.20),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '3 days' + INTERVAL '8 hours', 2850.000, 'PSI', 2800.000, 3200.000, 0.28),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '3 days' + INTERVAL '16 hours', 2780.000, 'PSI', 2800.000, 3200.000, 0.38),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '2 days' + INTERVAL '0 hours', 2700.000, 'PSI', 2800.000, 3200.000, 0.50),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '2 days' + INTERVAL '8 hours', 2620.000, 'PSI', 2800.000, 3200.000, 0.58),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '2 days' + INTERVAL '16 hours', 2550.000, 'PSI', 2800.000, 3200.000, 0.65),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '1 day' + INTERVAL '0 hours', 2450.000, 'PSI', 2800.000, 3200.000, 0.72),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '1 day' + INTERVAL '8 hours', 2350.000, 'PSI', 2800.000, 3200.000, 0.78),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '8 hours', 2280.000, 'PSI', 2800.000, 3200.000, 0.82),
('VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '4 hours', 2200.000, 'PSI', 2800.000, 3200.000, 0.88),
-- VT-ANP normal sensors for context
('VT-ANP', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.100, 'mm/s', 0.500, 3.000, 0.04),
('VT-ANP', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '3 days', 1.120, 'mm/s', 0.500, 3.000, 0.04),
('VT-ANP', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.090, 'mm/s', 0.500, 3.000, 0.04),
('VT-ANP', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.250, 'mm/s', 0.500, 3.000, 0.05),
('VT-ANP', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '3 days', 1.270, 'mm/s', 0.500, 3.000, 0.05),
('VT-ANP', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.240, 'mm/s', 0.500, 3.000, 0.05),
('VT-ANP', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 80.000, 'C', 70.000, 100.000, 0.03),
('VT-ANP', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '3 days', 81.500, 'C', 70.000, 100.000, 0.04),
('VT-ANP', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 80.800, 'C', 70.000, 100.000, 0.03),
('VT-ANP', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 830.000, 'C', 750.000, 900.000, 0.05),
('VT-ANP', 'EGT', 'ENGINE_1', NOW() - INTERVAL '3 days', 832.000, 'C', 750.000, 900.000, 0.05),
('VT-ANP', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 831.000, 'C', 750.000, 900.000, 0.05),
('VT-ANP', 'ENGINE_VIBRATION_N1', 'ENGINE_2', NOW() - INTERVAL '7 days', 1.150, 'mm/s', 0.500, 3.000, 0.04),
('VT-ANP', 'ENGINE_VIBRATION_N1', 'ENGINE_2', NOW() - INTERVAL '3 days', 1.170, 'mm/s', 0.500, 3.000, 0.04),
('VT-ANP', 'ENGINE_VIBRATION_N1', 'ENGINE_2', NOW() - INTERVAL '1 day', 1.140, 'mm/s', 0.500, 3.000, 0.04),
('VT-ANP', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '7 days', 81.000, 'C', 70.000, 100.000, 0.03),
('VT-ANP', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '3 days', 82.000, 'C', 70.000, 100.000, 0.04),
('VT-ANP', 'OIL_TEMP', 'ENGINE_2', NOW() - INTERVAL '1 day', 81.500, 'C', 70.000, 100.000, 0.03),
('VT-ANP', 'EGT', 'ENGINE_2', NOW() - INTERVAL '7 days', 828.000, 'C', 750.000, 900.000, 0.05),
('VT-ANP', 'EGT', 'ENGINE_2', NOW() - INTERVAL '3 days', 830.000, 'C', 750.000, 900.000, 0.05),
('VT-ANP', 'EGT', 'ENGINE_2', NOW() - INTERVAL '1 day', 829.000, 'C', 750.000, 900.000, 0.05);

-- ============================================================
-- Normal aircraft sensor data (VT-ANA, VT-ALQ, VT-ANE, etc.)
-- ============================================================
INSERT INTO sensor_telemetry (aircraft_reg, sensor_type, engine_position, timestamp, value, unit, normal_min, normal_max, anomaly_score) VALUES
-- VT-ANA (A321neo) - all normal
('VT-ANA', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 0.950, 'mm/s', 0.500, 3.000, 0.03),
('VT-ANA', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '3 days', 0.970, 'mm/s', 0.500, 3.000, 0.03),
('VT-ANA', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 0.960, 'mm/s', 0.500, 3.000, 0.03),
('VT-ANA', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.100, 'mm/s', 0.500, 3.000, 0.04),
('VT-ANA', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '3 days', 1.080, 'mm/s', 0.500, 3.000, 0.04),
('VT-ANA', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.110, 'mm/s', 0.500, 3.000, 0.04),
('VT-ANA', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 78.000, 'C', 70.000, 100.000, 0.03),
('VT-ANA', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '3 days', 79.200, 'C', 70.000, 100.000, 0.03),
('VT-ANA', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 78.500, 'C', 70.000, 100.000, 0.03),
('VT-ANA', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 820.000, 'C', 750.000, 900.000, 0.05),
('VT-ANA', 'EGT', 'ENGINE_1', NOW() - INTERVAL '3 days', 822.000, 'C', 750.000, 900.000, 0.05),
('VT-ANA', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 821.000, 'C', 750.000, 900.000, 0.05),
('VT-ANA', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '7 days', 3080.000, 'PSI', 2800.000, 3200.000, 0.03),
('VT-ANA', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '3 days', 3060.000, 'PSI', 2800.000, 3200.000, 0.03),
('VT-ANA', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '1 day', 3070.000, 'PSI', 2800.000, 3200.000, 0.03),
-- VT-ALQ (777-300ER) - all normal
('VT-ALQ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.400, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALQ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '3 days', 1.380, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALQ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.410, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALQ', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.550, 'mm/s', 0.500, 3.000, 0.07),
('VT-ALQ', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '3 days', 1.530, 'mm/s', 0.500, 3.000, 0.07),
('VT-ALQ', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.560, 'mm/s', 0.500, 3.000, 0.07),
('VT-ALQ', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 84.000, 'C', 70.000, 100.000, 0.04),
('VT-ALQ', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '3 days', 85.200, 'C', 70.000, 100.000, 0.05),
('VT-ALQ', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 84.500, 'C', 70.000, 100.000, 0.04),
('VT-ALQ', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 842.000, 'C', 750.000, 900.000, 0.06),
('VT-ALQ', 'EGT', 'ENGINE_1', NOW() - INTERVAL '3 days', 844.000, 'C', 750.000, 900.000, 0.06),
('VT-ALQ', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 843.000, 'C', 750.000, 900.000, 0.06),
('VT-ALQ', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '7 days', 3020.000, 'PSI', 2800.000, 3200.000, 0.03),
('VT-ALQ', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '3 days', 3000.000, 'PSI', 2800.000, 3200.000, 0.03),
('VT-ALQ', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '1 day', 3010.000, 'PSI', 2800.000, 3200.000, 0.03),
-- VT-ANE (A350) - all normal
('VT-ANE', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 0.800, 'mm/s', 0.500, 3.000, 0.02),
('VT-ANE', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '3 days', 0.820, 'mm/s', 0.500, 3.000, 0.02),
('VT-ANE', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 0.810, 'mm/s', 0.500, 3.000, 0.02),
('VT-ANE', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '7 days', 0.950, 'mm/s', 0.500, 3.000, 0.03),
('VT-ANE', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '3 days', 0.940, 'mm/s', 0.500, 3.000, 0.03),
('VT-ANE', 'ENGINE_VIBRATION_N2', 'ENGINE_1', NOW() - INTERVAL '1 day', 0.960, 'mm/s', 0.500, 3.000, 0.03),
('VT-ANE', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 76.000, 'C', 70.000, 100.000, 0.02),
('VT-ANE', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '3 days', 77.000, 'C', 70.000, 100.000, 0.02),
('VT-ANE', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 76.500, 'C', 70.000, 100.000, 0.02),
('VT-ANE', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 810.000, 'C', 750.000, 900.000, 0.04),
('VT-ANE', 'EGT', 'ENGINE_1', NOW() - INTERVAL '3 days', 812.000, 'C', 750.000, 900.000, 0.04),
('VT-ANE', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 811.000, 'C', 750.000, 900.000, 0.04),
('VT-ANE', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '7 days', 3120.000, 'PSI', 2800.000, 3200.000, 0.02),
('VT-ANE', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '3 days', 3100.000, 'PSI', 2800.000, 3200.000, 0.02),
('VT-ANE', 'HYDRAULIC_PRESSURE', 'ENGINE_1', NOW() - INTERVAL '1 day', 3110.000, 'PSI', 2800.000, 3200.000, 0.02),
-- VT-ALM normal
('VT-ALM', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.050, 'mm/s', 0.500, 3.000, 0.04),
('VT-ALM', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.060, 'mm/s', 0.500, 3.000, 0.04),
('VT-ALM', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 81.000, 'C', 70.000, 100.000, 0.03),
('VT-ALM', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 81.500, 'C', 70.000, 100.000, 0.03),
('VT-ALM', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 825.000, 'C', 750.000, 900.000, 0.05),
('VT-ALM', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 826.000, 'C', 750.000, 900.000, 0.05),
-- VT-ANR normal
('VT-ANR', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 0.750, 'mm/s', 0.500, 3.000, 0.02),
('VT-ANR', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 0.770, 'mm/s', 0.500, 3.000, 0.02),
('VT-ANR', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 74.000, 'C', 70.000, 100.000, 0.02),
('VT-ANR', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 74.500, 'C', 70.000, 100.000, 0.02),
('VT-ANR', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 805.000, 'C', 750.000, 900.000, 0.03),
('VT-ANR', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 806.000, 'C', 750.000, 900.000, 0.03),
-- VT-ALK normal
('VT-ALK', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.300, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALK', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.310, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALK', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 86.000, 'C', 70.000, 100.000, 0.05),
('VT-ALK', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 86.500, 'C', 70.000, 100.000, 0.05),
('VT-ALK', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 845.000, 'C', 750.000, 900.000, 0.06),
('VT-ALK', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 846.000, 'C', 750.000, 900.000, 0.06),
-- VT-ANB normal
('VT-ANB', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 0.900, 'mm/s', 0.500, 3.000, 0.03),
('VT-ANB', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 0.910, 'mm/s', 0.500, 3.000, 0.03),
('VT-ANB', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 77.000, 'C', 70.000, 100.000, 0.02),
('VT-ANB', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 77.500, 'C', 70.000, 100.000, 0.02),
('VT-ANB', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 815.000, 'C', 750.000, 900.000, 0.04),
('VT-ANB', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 816.000, 'C', 750.000, 900.000, 0.04),
-- VT-ALC normal
('VT-ALC', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.450, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALC', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.460, 'mm/s', 0.500, 3.000, 0.06),
('VT-ALC', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 88.000, 'C', 70.000, 100.000, 0.06),
('VT-ALC', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 88.500, 'C', 70.000, 100.000, 0.06),
('VT-ALC', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 855.000, 'C', 750.000, 900.000, 0.07),
('VT-ALC', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 856.000, 'C', 750.000, 900.000, 0.07),
-- VT-AND normal
('VT-AND', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 0.850, 'mm/s', 0.500, 3.000, 0.02),
('VT-AND', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 0.860, 'mm/s', 0.500, 3.000, 0.02),
('VT-AND', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 75.000, 'C', 70.000, 100.000, 0.02),
('VT-AND', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 75.500, 'C', 70.000, 100.000, 0.02),
('VT-AND', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 808.000, 'C', 750.000, 900.000, 0.04),
('VT-AND', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 809.000, 'C', 750.000, 900.000, 0.04),
-- VT-ANF normal
('VT-ANF', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.150, 'mm/s', 0.500, 3.000, 0.05),
('VT-ANF', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.160, 'mm/s', 0.500, 3.000, 0.05),
('VT-ANF', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 82.000, 'C', 70.000, 100.000, 0.04),
('VT-ANF', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 82.500, 'C', 70.000, 100.000, 0.04),
('VT-ANF', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 835.000, 'C', 750.000, 900.000, 0.05),
('VT-ANF', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 836.000, 'C', 750.000, 900.000, 0.05),
-- VT-ANH normal
('VT-ANH', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.000, 'mm/s', 0.500, 3.000, 0.03),
('VT-ANH', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.010, 'mm/s', 0.500, 3.000, 0.03),
('VT-ANH', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 79.000, 'C', 70.000, 100.000, 0.03),
('VT-ANH', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 79.500, 'C', 70.000, 100.000, 0.03),
('VT-ANH', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 818.000, 'C', 750.000, 900.000, 0.04),
('VT-ANH', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 819.000, 'C', 750.000, 900.000, 0.04),
-- VT-ANK normal
('VT-ANK', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '7 days', 1.350, 'mm/s', 0.500, 3.000, 0.06),
('VT-ANK', 'ENGINE_VIBRATION_N1', 'ENGINE_1', NOW() - INTERVAL '1 day', 1.360, 'mm/s', 0.500, 3.000, 0.06),
('VT-ANK', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '7 days', 87.000, 'C', 70.000, 100.000, 0.05),
('VT-ANK', 'OIL_TEMP', 'ENGINE_1', NOW() - INTERVAL '1 day', 87.500, 'C', 70.000, 100.000, 0.05),
('VT-ANK', 'EGT', 'ENGINE_1', NOW() - INTERVAL '7 days', 848.000, 'C', 750.000, 900.000, 0.06),
('VT-ANK', 'EGT', 'ENGINE_1', NOW() - INTERVAL '1 day', 849.000, 'C', 750.000, 900.000, 0.06);

-- ============================================================
-- 3. MAINTENANCE HISTORY
-- ============================================================
CREATE TABLE maintenance_history (
    work_order_id VARCHAR(20) PRIMARY KEY,
    aircraft_reg VARCHAR(10) NOT NULL REFERENCES aircraft_fleet(aircraft_reg),
    component VARCHAR(80) NOT NULL,
    ata_chapter VARCHAR(10) NOT NULL,
    action_type VARCHAR(20) NOT NULL,
    description TEXT NOT NULL,
    technician VARCHAR(60) NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED',
    cost_usd DECIMAL(12,2),
    parts_used TEXT
);

INSERT INTO maintenance_history VALUES
('WO-2025-0001', 'VT-ALJ', 'Engine #1 N1 Fan Blade', '72-00', 'SCHEDULED', 'Routine fan blade inspection per GEnx-1B service bulletin. No defects found.', 'Rajesh Kumar', '2025-09-10 06:00:00', '2025-09-10 14:00:00', 'COMPLETED', 4500.00, 'Borescope inspection kit'),
('WO-2025-0002', 'VT-ALJ', 'Engine #2 Oil Filter', '79-20', 'SCHEDULED', 'Replacement of engine oil filter at 30000 hour interval. Metal particles found in filter - monitored.', 'Amit Sharma', '2025-10-05 08:00:00', '2025-10-05 12:00:00', 'COMPLETED', 2800.00, 'GEnx oil filter PN-2055843'),
('WO-2025-0003', 'VT-ALJ', 'Landing Gear Strut', '32-10', 'INSPECTION', 'Nose landing gear strut servicing and pressure check.', 'Suresh Patel', '2025-11-15 07:00:00', '2025-11-15 15:00:00', 'COMPLETED', 3200.00, 'Hydraulic fluid MIL-PRF-83282'),
('WO-2025-0004', 'VT-ANA', 'CFM LEAP Engine Wash', '72-00', 'SCHEDULED', 'Engine compressor water wash for performance recovery. EGT margin improved by 8C.', 'Vikram Singh', '2025-08-20 05:00:00', '2025-08-20 09:00:00', 'COMPLETED', 1500.00, 'Demineralized water, cleaning solution'),
('WO-2025-0005', 'VT-ANA', 'APU Starter Motor', '49-10', 'UNSCHEDULED', 'APU failed to start on ground. Starter motor replaced.', 'Deepak Verma', '2025-09-12 10:00:00', '2025-09-12 18:00:00', 'COMPLETED', 28500.00, 'APU starter motor PN-3800754'),
('WO-2025-0006', 'VT-ALQ', 'Engine #1 Fuel Nozzle', '73-10', 'UNSCHEDULED', 'Hot start reported by crew. Fuel nozzle #3 found clogged, replaced.', 'Pradeep Rao', '2025-07-18 06:00:00', '2025-07-19 02:00:00', 'COMPLETED', 18200.00, 'GE90 fuel nozzle PN-1853M29'),
('WO-2025-0007', 'VT-ALQ', 'Hydraulic Pump', '29-10', 'SCHEDULED', 'Hydraulic system A pump replacement at 12000 cycle limit.', 'Manoj Tiwari', '2025-10-22 07:00:00', '2025-10-22 19:00:00', 'COMPLETED', 42000.00, 'Hydraulic pump PN-65-47681-13'),
('WO-2025-0008', 'VT-ANE', 'Trent XWB Borescope', '72-00', 'SCHEDULED', 'Routine borescope inspection of HP turbine blades. All within limits.', 'Arun Nair', '2025-12-08 06:00:00', '2025-12-08 14:00:00', 'COMPLETED', 5500.00, 'Borescope equipment'),
('WO-2025-0009', 'VT-ANE', 'Cabin Pressurization Valve', '21-30', 'UNSCHEDULED', 'Slow cabin pressurization reported. Outflow valve actuator replaced.', 'Sanjay Gupta', '2026-01-15 08:00:00', '2026-01-15 16:00:00', 'COMPLETED', 15800.00, 'Outflow valve PN-103480-3'),
('WO-2025-0010', 'VT-ANP', 'Engine #1 Vibration Sensor', '77-20', 'UNSCHEDULED', 'Intermittent vibration readings. Sensor replaced, readings normalized.', 'Rahul Joshi', '2025-11-28 09:00:00', '2025-11-28 13:00:00', 'COMPLETED', 6200.00, 'Vibration sensor PN-4015782'),
('WO-2025-0011', 'VT-ANP', 'Wing Anti-Ice Valve', '30-10', 'SCHEDULED', 'Wing anti-ice valve inspection and functional test.', 'Karthik Reddy', '2025-12-20 06:00:00', '2025-12-20 10:00:00', 'COMPLETED', 2100.00, NULL),
('WO-2025-0012', 'VT-ALM', 'Engine #2 Compressor Blade', '72-30', 'AOG_REPAIR', 'FOD damage to stage 1 compressor blade. Blade blended per SRM limits.', 'Vijay Menon', '2025-08-05 02:00:00', '2025-08-05 14:00:00', 'COMPLETED', 8500.00, 'Blending tools, dye penetrant kit'),
('WO-2025-0013', 'VT-ALM', 'Brake Assembly', '32-40', 'SCHEDULED', 'Main landing gear brake stack replacement at wear limit.', 'Anand Pillai', '2025-10-10 07:00:00', '2025-10-10 17:00:00', 'COMPLETED', 35000.00, 'Carbon brake stack PN-2612577-3'),
('WO-2025-0014', 'VT-ANG', 'Engine #1 Complete Overhaul', '72-00', 'SCHEDULED', 'GE90-115B engine removed for shop visit at 18000 cycle limit. Currently at GE Overhaul facility.', 'Prakash Das', '2026-04-15 06:00:00', NULL, 'IN_PROGRESS', 2500000.00, 'Complete engine overhaul kit'),
('WO-2025-0015', 'VT-ANG', 'Landing Gear Overhaul', '32-00', 'SCHEDULED', 'Main and nose landing gear overhaul during engine shop visit.', 'Mohan Lal', '2026-04-15 06:00:00', NULL, 'IN_PROGRESS', 180000.00, 'Landing gear overhaul kit'),
('WO-2025-0016', 'VT-ALK', 'Engine #2 Bleed Valve', '36-10', 'UNSCHEDULED', 'Bleed air leak detected during ground ops. Bleed valve replaced.', 'Ramesh Iyer', '2026-01-20 08:00:00', '2026-01-20 16:00:00', 'COMPLETED', 12400.00, 'Bleed valve PN-393C200-3'),
('WO-2025-0017', 'VT-ALK', 'Flight Data Recorder', '31-30', 'SCHEDULED', 'FDR calibration and data dump per regulatory requirement.', 'Nitin Jain', '2026-02-05 06:00:00', '2026-02-05 10:00:00', 'COMPLETED', 1800.00, NULL),
('WO-2025-0018', 'VT-ANB', 'Engine #1 Igniter Plug', '74-10', 'SCHEDULED', 'Igniter plug replacement at 5000 hour interval.', 'Gaurav Mishra', '2025-11-10 07:00:00', '2025-11-10 11:00:00', 'COMPLETED', 3500.00, 'Igniter plug PN-9-166-121-01'),
('WO-2025-0019', 'VT-ANB', 'Weather Radar', '34-10', 'UNSCHEDULED', 'Radar display intermittent. R/T unit replaced.', 'Alok Saxena', '2026-02-18 09:00:00', '2026-02-18 15:00:00', 'COMPLETED', 22000.00, 'Weather radar R/T PN-WXR-2100'),
('WO-2025-0020', 'VT-ALC', 'Engine #1 Thrust Reverser', '78-20', 'SCHEDULED', 'Thrust reverser blocker door rigging check and adjustment.', 'Dinesh Kumar', '2025-09-25 06:00:00', '2025-09-25 14:00:00', 'COMPLETED', 4800.00, NULL),
('WO-2025-0021', 'VT-ALC', 'APU Exhaust', '49-00', 'INSPECTION', 'APU exhaust duct inspection for cracks.', 'Harish Bhat', '2026-01-08 08:00:00', '2026-01-08 12:00:00', 'COMPLETED', 1200.00, NULL),
('WO-2025-0022', 'VT-AND', 'Fuel Quantity System', '28-40', 'UNSCHEDULED', 'Fuel quantity indication discrepancy. Tank probe recalibrated.', 'Sunil Choudhury', '2025-12-15 07:00:00', '2025-12-15 15:00:00', 'COMPLETED', 7500.00, 'Probe calibration kit'),
('WO-2025-0023', 'VT-AND', 'Air Conditioning Pack', '21-50', 'SCHEDULED', 'Pack valve and heat exchanger inspection.', 'Vivek Pandey', '2026-03-10 06:00:00', '2026-03-10 18:00:00', 'COMPLETED', 9200.00, NULL),
('WO-2025-0024', 'VT-ANF', 'Engine #1 Oil Chip Detector', '79-10', 'UNSCHEDULED', 'Chip detector light illuminated. Detector inspected - fine metallic fuzz, no significant particles.', 'Ajay Bhatt', '2026-02-22 10:00:00', '2026-02-22 14:00:00', 'COMPLETED', 1600.00, 'Oil chip detector PN-4935182'),
('WO-2025-0025', 'VT-ANF', 'Wheel and Tire', '32-40', 'SCHEDULED', 'Main gear tire replacement at tread wear limit.', 'Sandeep Kulkarni', '2026-03-15 07:00:00', '2026-03-15 11:00:00', 'COMPLETED', 4200.00, 'Main tire PN-H40X14.5-19'),
('WO-2025-0026', 'VT-ANH', 'Engine #2 Gearbox', '72-60', 'INSPECTION', 'Accessory gearbox inspection after oil analysis showed elevated iron.', 'Ravi Shankar', '2026-01-25 06:00:00', '2026-01-25 18:00:00', 'COMPLETED', 6800.00, NULL),
('WO-2025-0027', 'VT-ANH', 'Navigation System', '34-50', 'SCHEDULED', 'GPS/IRS alignment check and software update.', 'Ashok Mehta', '2026-03-05 08:00:00', '2026-03-05 14:00:00', 'COMPLETED', 3200.00, NULL),
('WO-2025-0028', 'VT-ANK', 'Engine #2 EGT Probe', '77-20', 'UNSCHEDULED', 'EGT reading erratic on Engine #2. Thermocouple harness replaced.', 'Sachin Patil', '2026-02-10 09:00:00', '2026-02-10 15:00:00', 'COMPLETED', 8900.00, 'EGT harness PN-6040T39'),
('WO-2025-0029', 'VT-ANK', 'Oxygen System', '35-10', 'SCHEDULED', 'Flight deck and cabin oxygen system pressure check and regulator test.', 'Naveen Chandra', '2026-03-20 06:00:00', '2026-03-20 10:00:00', 'COMPLETED', 2400.00, NULL),
('WO-2025-0030', 'VT-ALJ', 'Engine #2 Vibration Analysis', '72-00', 'INSPECTION', 'Trending vibration increase on N2. Oil sample analysis ordered. Monitor closely.', 'Rajesh Kumar', '2026-04-20 08:00:00', '2026-04-20 12:00:00', 'COMPLETED', 2200.00, 'Oil sample collection kit'),
('WO-2025-0031', 'VT-ALJ', 'Cockpit Display Unit', '31-60', 'UNSCHEDULED', 'Captain PFD flickering intermittently. Display unit replaced.', 'Amit Sharma', '2026-03-28 07:00:00', '2026-03-28 13:00:00', 'COMPLETED', 45000.00, 'Display unit PN-DU-875'),
('WO-2025-0032', 'VT-ANA', 'Engine Wash', '72-00', 'SCHEDULED', 'Compressor water wash for EGT margin recovery.', 'Vikram Singh', '2026-03-01 05:00:00', '2026-03-01 09:00:00', 'COMPLETED', 1500.00, 'Cleaning solution'),
('WO-2025-0033', 'VT-ALQ', 'Flap Actuator', '27-50', 'UNSCHEDULED', 'Trailing edge flap asymmetry detected. Actuator replaced.', 'Pradeep Rao', '2026-04-02 06:00:00', '2026-04-02 18:00:00', 'COMPLETED', 38000.00, 'Flap actuator PN-65-23857-8'),
('WO-2025-0034', 'VT-ANE', 'IDG Replacement', '24-20', 'UNSCHEDULED', 'Integrated drive generator disconnected in flight due to high oil temp. Replaced.', 'Arun Nair', '2026-04-08 10:00:00', '2026-04-08 20:00:00', 'COMPLETED', 65000.00, 'IDG PN-976J315-3'),
('WO-2025-0035', 'VT-ANP', 'Hydraulic Reservoir', '29-00', 'INSPECTION', 'Hydraulic fluid level check and system pressure test following low-pressure indication.', 'Karthik Reddy', '2026-04-25 08:00:00', '2026-04-25 14:00:00', 'COMPLETED', 3500.00, 'Hydraulic fluid Skydrol LD-4'),
('WO-2025-0036', 'VT-ALJ', 'Engine #2 Bearing Inspection', '72-50', 'INSPECTION', 'Detailed inspection ordered following vibration trend analysis. N2 turbine bearing showing wear indicators. RECOMMEND REPLACEMENT WITHIN 200 FH.', 'Rajesh Kumar', '2026-04-25 06:00:00', '2026-04-25 16:00:00', 'COMPLETED', 8500.00, 'Borescope, vibration analysis kit'),
('WO-2025-0037', 'VT-ALM', 'Tire Change', '32-40', 'SCHEDULED', 'Nose wheel tire change at cycle limit.', 'Anand Pillai', '2026-04-12 07:00:00', '2026-04-12 10:00:00', 'COMPLETED', 2800.00, 'Nose tire PN-H22X8.25-10'),
('WO-2025-0038', 'VT-ALC', 'Pitot Tube Heating', '34-10', 'UNSCHEDULED', 'Pitot heat fail indication. Heating element replaced.', 'Harish Bhat', '2026-04-18 09:00:00', '2026-04-18 13:00:00', 'COMPLETED', 4100.00, 'Pitot heating element'),
('WO-2025-0039', 'VT-AND', 'Fire Detection Loop', '26-10', 'SCHEDULED', 'Engine fire detection loop continuity check.', 'Vivek Pandey', '2026-04-10 06:00:00', '2026-04-10 10:00:00', 'COMPLETED', 1800.00, NULL),
('WO-2025-0040', 'VT-ANR', 'AC Pack Valve', '21-50', 'UNSCHEDULED', 'Pack valve stuck closed. Replaced and tested.', 'Arun Nair', '2026-04-05 11:00:00', '2026-04-05 19:00:00', 'COMPLETED', 18500.00, 'Pack valve PN-832760-1'),
('WO-2025-0041', 'VT-ALJ', 'Engine #2 Oil Analysis', '79-00', 'INSPECTION', 'Spectrometric oil analysis shows elevated Fe and Cr levels consistent with bearing wear. Correlates with N2 vibration trend.', 'Amit Sharma', '2026-04-27 08:00:00', '2026-04-27 10:00:00', 'COMPLETED', 800.00, 'Oil analysis kit'),
('WO-2025-0042', 'VT-ANP', 'Hydraulic System Leak Check', '29-10', 'INSPECTION', 'System B hydraulic pressure declining. Leak found at pump case drain fitting. Temporary repair applied, full repair needed.', 'Rahul Joshi', '2026-04-27 14:00:00', '2026-04-27 18:00:00', 'COMPLETED', 2200.00, 'Leak detection dye, sealant');

-- ============================================================
-- 4. PARTS INVENTORY
-- ============================================================
CREATE TABLE parts_inventory (
    part_number VARCHAR(30) PRIMARY KEY,
    description VARCHAR(120) NOT NULL,
    component_category VARCHAR(20) NOT NULL,
    quantity_del INTEGER NOT NULL DEFAULT 0,
    quantity_bom INTEGER NOT NULL DEFAULT 0,
    quantity_blr INTEGER NOT NULL DEFAULT 0,
    quantity_maa INTEGER NOT NULL DEFAULT 0,
    quantity_hyd INTEGER NOT NULL DEFAULT 0,
    unit_cost_usd DECIMAL(12,2) NOT NULL,
    lead_time_days INTEGER NOT NULL,
    min_stock INTEGER NOT NULL DEFAULT 1,
    compatible_aircraft TEXT
);

INSERT INTO parts_inventory VALUES
-- CRITICAL: N2 turbine bearing ONLY at Mumbai
('PN-GE-N2B-7892', 'N2 Turbine Bearing Assembly - GEnx-1B', 'ENGINE', 0, 2, 0, 0, 0, 85000.00, 14, 1, 'Boeing 787-9 Dreamliner'),
('PN-GE-N2B-7893', 'N2 Turbine Bearing Seal Kit', 'ENGINE', 0, 3, 0, 0, 0, 12000.00, 10, 2, 'Boeing 787-9 Dreamliner'),
('PN-2055843', 'Engine Oil Filter - GEnx-1B', 'ENGINE', 5, 4, 2, 2, 1, 850.00, 3, 2, 'Boeing 787-9 Dreamliner'),
('PN-GE90-FB-101', 'Fan Blade - GE90-115B', 'ENGINE', 2, 1, 0, 0, 0, 125000.00, 21, 1, 'Boeing 777-300ER'),
('PN-LEAP-IGN-01', 'Igniter Plug - CFM LEAP-1A', 'ENGINE', 4, 3, 2, 2, 2, 1200.00, 5, 2, 'Airbus A321neo'),
('PN-1853M29', 'Fuel Nozzle Assembly - GE90-115B', 'ENGINE', 1, 2, 0, 0, 0, 8500.00, 12, 1, 'Boeing 777-300ER'),
('PN-TWB-HPT-01', 'HP Turbine Blade - Trent XWB', 'ENGINE', 1, 1, 1, 1, 0, 95000.00, 18, 1, 'Airbus A350-900'),
('PN-3800754', 'APU Starter Motor', 'APU', 2, 1, 1, 0, 1, 28000.00, 15, 1, 'Boeing 787-9 Dreamliner,Airbus A321neo'),
('PN-65-47681-13', 'Hydraulic Pump Assembly - System A', 'HYDRAULIC', 1, 2, 1, 1, 0, 42000.00, 20, 1, 'Boeing 777-300ER,Boeing 787-9 Dreamliner'),
('PN-HYD-SEAL-01', 'Hydraulic Pump Seal Kit', 'HYDRAULIC', 3, 4, 2, 1, 1, 2200.00, 5, 2, 'Boeing 787-9 Dreamliner,Boeing 777-300ER,Airbus A350-900,Airbus A321neo'),
('PN-HYD-ACCUM-01', 'Hydraulic Accumulator', 'HYDRAULIC', 1, 2, 1, 0, 0, 18500.00, 12, 1, 'Boeing 787-9 Dreamliner,Boeing 777-300ER'),
('PN-HYD-FITTING-01', 'Hydraulic Case Drain Fitting', 'HYDRAULIC', 2, 3, 2, 1, 1, 450.00, 3, 2, 'Boeing 787-9 Dreamliner,Boeing 777-300ER,Airbus A350-900'),
('PN-103480-3', 'Outflow Valve Actuator', 'PNEUMATIC', 1, 1, 0, 1, 0, 15000.00, 14, 1, 'Airbus A350-900,Airbus A321neo'),
('PN-393C200-3', 'Engine Bleed Valve Assembly', 'PNEUMATIC', 2, 1, 1, 0, 1, 12000.00, 10, 1, 'Boeing 787-9 Dreamliner'),
('PN-832760-1', 'Air Conditioning Pack Valve', 'PNEUMATIC', 1, 1, 1, 0, 0, 18000.00, 16, 1, 'Airbus A350-900,Boeing 787-9 Dreamliner'),
('PN-4935182', 'Oil Chip Detector', 'ENGINE', 3, 2, 1, 1, 1, 1500.00, 4, 2, 'Boeing 787-9 Dreamliner'),
('PN-4015782', 'Vibration Sensor Assembly', 'ENGINE', 2, 2, 1, 1, 0, 6000.00, 7, 1, 'Boeing 787-9 Dreamliner,Boeing 777-300ER'),
('PN-6040T39', 'EGT Thermocouple Harness', 'ENGINE', 2, 1, 1, 0, 1, 8500.00, 8, 1, 'Boeing 777-300ER,Boeing 787-9 Dreamliner'),
('PN-DU-875', 'Cockpit Display Unit', 'AVIONICS', 1, 1, 0, 0, 0, 44000.00, 25, 1, 'Boeing 787-9 Dreamliner,Boeing 777-300ER'),
('PN-WXR-2100', 'Weather Radar R/T Unit', 'AVIONICS', 1, 1, 1, 0, 0, 21000.00, 18, 1, 'All'),
('PN-FDR-980', 'Flight Data Recorder', 'AVIONICS', 1, 1, 0, 0, 0, 35000.00, 30, 1, 'All'),
('PN-2612577-3', 'Carbon Brake Stack Assembly', 'LANDING_GEAR', 4, 3, 2, 1, 1, 32000.00, 14, 2, 'Boeing 787-9 Dreamliner'),
('PN-H40X14.5-19', 'Main Gear Tire', 'LANDING_GEAR', 8, 6, 4, 3, 2, 3800.00, 3, 4, 'Boeing 787-9 Dreamliner,Boeing 777-300ER'),
('PN-H22X8.25-10', 'Nose Gear Tire', 'LANDING_GEAR', 6, 4, 3, 2, 2, 2200.00, 3, 3, 'All'),
('PN-65-23857-8', 'Trailing Edge Flap Actuator', 'LANDING_GEAR', 1, 1, 0, 0, 0, 37000.00, 22, 1, 'Boeing 777-300ER'),
('PN-976J315-3', 'Integrated Drive Generator (IDG)', 'ENGINE', 1, 1, 0, 1, 0, 62000.00, 20, 1, 'Airbus A350-900'),
('PN-PITOT-HE-01', 'Pitot Tube Heating Element', 'AVIONICS', 3, 2, 2, 1, 1, 3800.00, 5, 2, 'All'),
('PN-FIRE-LOOP-01', 'Fire Detection Loop Sensor', 'ENGINE', 2, 2, 1, 1, 1, 5500.00, 8, 1, 'All'),
('PN-OIL-SAMPLE-KIT', 'Oil Analysis Sample Kit', 'ENGINE', 10, 8, 5, 4, 3, 150.00, 1, 5, 'All'),
('PN-SKY-LD4-5L', 'Skydrol LD-4 Hydraulic Fluid 5L', 'HYDRAULIC', 12, 10, 8, 5, 4, 280.00, 2, 6, 'All'),
('PN-MIL-83282-5L', 'MIL-PRF-83282 Hydraulic Fluid 5L', 'HYDRAULIC', 10, 8, 6, 4, 3, 220.00, 2, 5, 'All');

-- ============================================================
-- 5. COMPONENT LIFECYCLE
-- ============================================================
CREATE TABLE component_lifecycle (
    component_id VARCHAR(20) PRIMARY KEY,
    aircraft_reg VARCHAR(10) NOT NULL REFERENCES aircraft_fleet(aircraft_reg),
    component_type VARCHAR(80) NOT NULL,
    part_number VARCHAR(30),
    install_date DATE NOT NULL,
    expected_life_hours INTEGER NOT NULL,
    current_hours INTEGER NOT NULL,
    health_score DECIMAL(5,2) NOT NULL,
    next_inspection_due DATE NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'NORMAL'
);

INSERT INTO component_lifecycle VALUES
-- VT-ALJ components - Engine #2 N2 bearing is CRITICAL
('CL-ALJ-E1-N1', 'VT-ALJ', 'Engine #1 N1 Fan Assembly', 'PN-GE-FAN-01', '2023-08-15', 25000, 18500, 78.00, '2026-06-15', 'NORMAL'),
('CL-ALJ-E1-N2', 'VT-ALJ', 'Engine #1 N2 Turbine Assembly', 'PN-GE-N2A-01', '2023-08-15', 20000, 18500, 72.00, '2026-06-15', 'NORMAL'),
('CL-ALJ-E2-N1', 'VT-ALJ', 'Engine #2 N1 Fan Assembly', 'PN-GE-FAN-01', '2023-08-15', 25000, 18500, 75.00, '2026-06-15', 'NORMAL'),
('CL-ALJ-E2-N2', 'VT-ALJ', 'Engine #2 N2 Turbine Bearing', 'PN-GE-N2B-7892', '2022-05-10', 20000, 19200, 32.00, '2026-04-30', 'CRITICAL'),
('CL-ALJ-E2-OIL', 'VT-ALJ', 'Engine #2 Oil System', 'PN-2055843', '2025-10-05', 5000, 3800, 55.00, '2026-05-15', 'WARNING'),
('CL-ALJ-LG-MAIN', 'VT-ALJ', 'Main Landing Gear Assembly', 'PN-MLG-787-01', '2023-01-20', 30000, 22500, 68.00, '2026-08-20', 'NORMAL'),
('CL-ALJ-LG-NOSE', 'VT-ALJ', 'Nose Landing Gear Assembly', 'PN-NLG-787-01', '2023-01-20', 30000, 22500, 70.00, '2026-08-20', 'NORMAL'),
('CL-ALJ-APU', 'VT-ALJ', 'Auxiliary Power Unit', 'PN-APU-787-01', '2024-02-10', 15000, 8200, 82.00, '2026-09-10', 'NORMAL'),
('CL-ALJ-HYD-A', 'VT-ALJ', 'Hydraulic System A Pump', 'PN-65-47681-13', '2024-06-15', 12000, 7800, 74.00, '2026-07-15', 'NORMAL'),
('CL-ALJ-HYD-B', 'VT-ALJ', 'Hydraulic System B Pump', 'PN-65-47681-13', '2024-06-15', 12000, 7800, 76.00, '2026-07-15', 'NORMAL'),
-- VT-ANA components
('CL-ANA-E1-N1', 'VT-ANA', 'Engine #1 N1 Fan Assembly', 'PN-LEAP-FAN-01', '2024-01-10', 25000, 12700, 88.00, '2026-08-10', 'NORMAL'),
('CL-ANA-E1-N2', 'VT-ANA', 'Engine #1 N2 Turbine Assembly', 'PN-LEAP-N2-01', '2024-01-10', 20000, 12700, 85.00, '2026-08-10', 'NORMAL'),
('CL-ANA-E2-N1', 'VT-ANA', 'Engine #2 N1 Fan Assembly', 'PN-LEAP-FAN-01', '2024-01-10', 25000, 12700, 87.00, '2026-08-10', 'NORMAL'),
('CL-ANA-E2-N2', 'VT-ANA', 'Engine #2 N2 Turbine Assembly', 'PN-LEAP-N2-01', '2024-01-10', 20000, 12700, 84.00, '2026-08-10', 'NORMAL'),
('CL-ANA-APU', 'VT-ANA', 'Auxiliary Power Unit', 'PN-3800754', '2025-09-12', 15000, 4800, 90.00, '2026-12-12', 'NORMAL'),
-- VT-ALQ components
('CL-ALQ-E1-N1', 'VT-ALQ', 'Engine #1 N1 Fan Assembly', 'PN-GE90-FB-101', '2022-06-10', 25000, 22100, 65.00, '2026-06-10', 'WATCH'),
('CL-ALQ-E1-N2', 'VT-ALQ', 'Engine #1 N2 Turbine Assembly', 'PN-GE90-N2-01', '2022-06-10', 20000, 18800, 58.00, '2026-05-10', 'WATCH'),
('CL-ALQ-E2-N1', 'VT-ALQ', 'Engine #2 N1 Fan Assembly', 'PN-GE90-FB-101', '2022-06-10', 25000, 22100, 67.00, '2026-06-10', 'WATCH'),
('CL-ALQ-E2-N2', 'VT-ALQ', 'Engine #2 N2 Turbine Assembly', 'PN-GE90-N2-01', '2022-06-10', 20000, 18800, 60.00, '2026-05-10', 'WATCH'),
('CL-ALQ-HYD-A', 'VT-ALQ', 'Hydraulic System A Pump', 'PN-65-47681-13', '2025-10-22', 12000, 3200, 92.00, '2026-10-22', 'NORMAL'),
-- VT-ANE components
('CL-ANE-E1-N1', 'VT-ANE', 'Engine #1 N1 Fan Assembly', 'PN-TWB-FAN-01', '2024-06-01', 25000, 8300, 92.00, '2026-12-01', 'NORMAL'),
('CL-ANE-E1-N2', 'VT-ANE', 'Engine #1 N2 Turbine Assembly', 'PN-TWB-HPT-01', '2024-06-01', 20000, 8300, 90.00, '2026-12-01', 'NORMAL'),
('CL-ANE-E2-N1', 'VT-ANE', 'Engine #2 N1 Fan Assembly', 'PN-TWB-FAN-01', '2024-06-01', 25000, 8300, 91.00, '2026-12-01', 'NORMAL'),
('CL-ANE-E2-N2', 'VT-ANE', 'Engine #2 N2 Turbine Assembly', 'PN-TWB-HPT-01', '2024-06-01', 20000, 8300, 89.00, '2026-12-01', 'NORMAL'),
('CL-ANE-IDG', 'VT-ANE', 'Integrated Drive Generator', 'PN-976J315-3', '2026-04-08', 10000, 200, 99.00, '2027-04-08', 'NORMAL'),
-- VT-ANP components - hydraulic showing degradation
('CL-ANP-E1-N1', 'VT-ANP', 'Engine #1 N1 Fan Assembly', 'PN-GE-FAN-01', '2023-09-22', 25000, 16900, 80.00, '2026-09-22', 'NORMAL'),
('CL-ANP-E1-N2', 'VT-ANP', 'Engine #1 N2 Turbine Assembly', 'PN-GE-N2A-01', '2023-09-22', 20000, 16900, 77.00, '2026-09-22', 'NORMAL'),
('CL-ANP-E2-N1', 'VT-ANP', 'Engine #2 N1 Fan Assembly', 'PN-GE-FAN-01', '2023-09-22', 25000, 16900, 79.00, '2026-09-22', 'NORMAL'),
('CL-ANP-E2-N2', 'VT-ANP', 'Engine #2 N2 Turbine Assembly', 'PN-GE-N2A-01', '2023-09-22', 20000, 16900, 76.00, '2026-09-22', 'NORMAL'),
('CL-ANP-HYD-B', 'VT-ANP', 'Hydraulic System B Pump', 'PN-65-47681-13', '2024-03-15', 12000, 8500, 45.00, '2026-05-15', 'WARNING'),
('CL-ANP-HYD-A', 'VT-ANP', 'Hydraulic System A Pump', 'PN-65-47681-13', '2024-03-15', 12000, 8500, 72.00, '2026-09-15', 'NORMAL'),
-- VT-ALM components
('CL-ALM-E1-N1', 'VT-ALM', 'Engine #1 N1 Fan Assembly', 'PN-LEAP-FAN-01', '2023-07-18', 25000, 16100, 82.00, '2026-07-18', 'NORMAL'),
('CL-ALM-E2-N1', 'VT-ALM', 'Engine #2 N1 Fan Assembly', 'PN-LEAP-FAN-01', '2023-07-18', 25000, 16100, 80.00, '2026-07-18', 'NORMAL'),
('CL-ALM-BRAKE', 'VT-ALM', 'Carbon Brake Stack', 'PN-2612577-3', '2025-10-10', 8000, 4200, 75.00, '2026-06-10', 'NORMAL'),
-- VT-ALK components
('CL-ALK-E1-N1', 'VT-ALK', 'Engine #1 N1 Fan Assembly', 'PN-GE-FAN-01', '2023-05-25', 25000, 19600, 72.00, '2026-05-25', 'WATCH'),
('CL-ALK-E2-N1', 'VT-ALK', 'Engine #2 N1 Fan Assembly', 'PN-GE-FAN-01', '2023-05-25', 25000, 19600, 70.00, '2026-05-25', 'WATCH'),
('CL-ALK-BLEED', 'VT-ALK', 'Engine Bleed Valve', 'PN-393C200-3', '2026-01-20', 10000, 2200, 95.00, '2027-01-20', 'NORMAL'),
-- VT-ANB components
('CL-ANB-E1-N1', 'VT-ANB', 'Engine #1 N1 Fan Assembly', 'PN-LEAP-FAN-01', '2024-12-08', 25000, 6500, 94.00, '2027-06-08', 'NORMAL'),
('CL-ANB-E2-N1', 'VT-ANB', 'Engine #2 N1 Fan Assembly', 'PN-LEAP-FAN-01', '2024-12-08', 25000, 6500, 93.00, '2027-06-08', 'NORMAL'),
('CL-ANB-WXR', 'VT-ANB', 'Weather Radar', 'PN-WXR-2100', '2026-02-18', 12000, 1200, 98.00, '2027-02-18', 'NORMAL'),
-- VT-ALC components
('CL-ALC-E1-N1', 'VT-ALC', 'Engine #1 N1 Fan Assembly', 'PN-GE90-FB-101', '2022-07-01', 25000, 21300, 66.00, '2026-07-01', 'WATCH'),
('CL-ALC-E2-N1', 'VT-ALC', 'Engine #2 N1 Fan Assembly', 'PN-GE90-FB-101', '2022-07-01', 25000, 21300, 68.00, '2026-07-01', 'WATCH'),
-- VT-AND components
('CL-AND-E1-N1', 'VT-AND', 'Engine #1 N1 Fan Assembly', 'PN-TWB-FAN-01', '2024-10-15', 25000, 10200, 89.00, '2026-10-15', 'NORMAL'),
('CL-AND-E2-N1', 'VT-AND', 'Engine #2 N1 Fan Assembly', 'PN-TWB-FAN-01', '2024-10-15', 25000, 10200, 88.00, '2026-10-15', 'NORMAL'),
-- VT-ANF components
('CL-ANF-E1-N1', 'VT-ANF', 'Engine #1 N1 Fan Assembly', 'PN-GE-FAN-01', '2023-08-03', 25000, 18100, 75.00, '2026-08-03', 'NORMAL'),
('CL-ANF-E2-N1', 'VT-ANF', 'Engine #2 N1 Fan Assembly', 'PN-GE-FAN-01', '2023-08-03', 25000, 18100, 74.00, '2026-08-03', 'NORMAL'),
-- VT-ANH components
('CL-ANH-E1-N1', 'VT-ANH', 'Engine #1 N1 Fan Assembly', 'PN-LEAP-FAN-01', '2024-09-11', 25000, 10400, 87.00, '2026-09-11', 'NORMAL'),
('CL-ANH-E2-N1', 'VT-ANH', 'Engine #2 N1 Fan Assembly', 'PN-LEAP-FAN-01', '2024-09-11', 25000, 10400, 86.00, '2026-09-11', 'NORMAL'),
-- VT-ANK components
('CL-ANK-E1-N1', 'VT-ANK', 'Engine #1 N1 Fan Assembly', 'PN-GE90-FB-101', '2022-06-20', 25000, 20700, 68.00, '2026-06-20', 'WATCH'),
('CL-ANK-E2-N1', 'VT-ANK', 'Engine #2 N1 Fan Assembly', 'PN-GE90-FB-101', '2022-06-20', 25000, 20700, 70.00, '2026-06-20', 'WATCH'),
-- VT-ANR components
('CL-ANR-E1-N1', 'VT-ANR', 'Engine #1 N1 Fan Assembly', 'PN-TWB-FAN-01', '2025-02-14', 25000, 5800, 95.00, '2027-02-14', 'NORMAL'),
('CL-ANR-E2-N1', 'VT-ANR', 'Engine #2 N1 Fan Assembly', 'PN-TWB-FAN-01', '2025-02-14', 25000, 5800, 94.00, '2027-02-14', 'NORMAL');

-- ============================================================
-- 6. FLIGHT SCHEDULE (next 3 days)
-- ============================================================
CREATE TABLE flight_schedule (
    flight_id VARCHAR(15) PRIMARY KEY,
    flight_number VARCHAR(10) NOT NULL,
    aircraft_reg VARCHAR(10) NOT NULL REFERENCES aircraft_fleet(aircraft_reg),
    origin VARCHAR(5) NOT NULL,
    destination VARCHAR(5) NOT NULL,
    departure TIMESTAMP NOT NULL,
    arrival TIMESTAMP NOT NULL,
    status VARCHAR(15) NOT NULL DEFAULT 'SCHEDULED'
);

INSERT INTO flight_schedule VALUES
-- VT-ALJ flights (based DEL) — has an overnight gap tonight for maintenance
('FL-001', 'AI-101', 'VT-ALJ', 'DEL', 'BOM', NOW()::date + INTERVAL '6 hours', NOW()::date + INTERVAL '8 hours 15 minutes', 'SCHEDULED'),
('FL-002', 'AI-102', 'VT-ALJ', 'BOM', 'DEL', NOW()::date + INTERVAL '9 hours 30 minutes', NOW()::date + INTERVAL '11 hours 45 minutes', 'SCHEDULED'),
('FL-003', 'AI-173', 'VT-ALJ', 'DEL', 'LHR', NOW()::date + INTERVAL '1 day' + INTERVAL '21 hours', NOW()::date + INTERVAL '2 days' + INTERVAL '5 hours 30 minutes', 'SCHEDULED'),
('FL-004', 'AI-174', 'VT-ALJ', 'LHR', 'DEL', NOW()::date + INTERVAL '2 days' + INTERVAL '10 hours', NOW()::date + INTERVAL '2 days' + INTERVAL '22 hours', 'SCHEDULED'),
-- Maintenance window: after FL-002 arrives at ~11:45 today until FL-003 departs at 21:00 tomorrow = ~33 hour gap at DEL
-- But more importantly: tonight after FL-002 to next morning = 10+ hour overnight window
-- VT-ANA flights
('FL-005', 'AI-803', 'VT-ANA', 'DEL', 'BLR', NOW()::date + INTERVAL '7 hours', NOW()::date + INTERVAL '9 hours 45 minutes', 'SCHEDULED'),
('FL-006', 'AI-804', 'VT-ANA', 'BLR', 'DEL', NOW()::date + INTERVAL '11 hours', NOW()::date + INTERVAL '13 hours 45 minutes', 'SCHEDULED'),
('FL-007', 'AI-865', 'VT-ANA', 'DEL', 'MAA', NOW()::date + INTERVAL '1 day' + INTERVAL '5 hours 30 minutes', NOW()::date + INTERVAL '1 day' + INTERVAL '8 hours 15 minutes', 'SCHEDULED'),
('FL-008', 'AI-866', 'VT-ANA', 'MAA', 'DEL', NOW()::date + INTERVAL '1 day' + INTERVAL '9 hours 30 minutes', NOW()::date + INTERVAL '1 day' + INTERVAL '12 hours 15 minutes', 'SCHEDULED'),
-- VT-ALQ flights (based BOM)
('FL-009', 'AI-131', 'VT-ALQ', 'BOM', 'DEL', NOW()::date + INTERVAL '5 hours 30 minutes', NOW()::date + INTERVAL '7 hours 45 minutes', 'SCHEDULED'),
('FL-010', 'AI-132', 'VT-ALQ', 'DEL', 'BOM', NOW()::date + INTERVAL '9 hours', NOW()::date + INTERVAL '11 hours 15 minutes', 'SCHEDULED'),
-- VT-ANE flights
('FL-011', 'AI-111', 'VT-ANE', 'DEL', 'SIN', NOW()::date + INTERVAL '1 day' + INTERVAL '1 hour', NOW()::date + INTERVAL '1 day' + INTERVAL '7 hours 30 minutes', 'SCHEDULED'),
('FL-012', 'AI-112', 'VT-ANE', 'SIN', 'DEL', NOW()::date + INTERVAL '1 day' + INTERVAL '22 hours', NOW()::date + INTERVAL '2 days' + INTERVAL '4 hours 30 minutes', 'SCHEDULED'),
-- VT-ANP flights (based BLR) — the hydraulic issue aircraft
('FL-013', 'AI-501', 'VT-ANP', 'BLR', 'DEL', NOW()::date + INTERVAL '8 hours', NOW()::date + INTERVAL '10 hours 45 minutes', 'SCHEDULED'),
('FL-014', 'AI-502', 'VT-ANP', 'DEL', 'BLR', NOW()::date + INTERVAL '12 hours', NOW()::date + INTERVAL '14 hours 45 minutes', 'SCHEDULED'),
('FL-015', 'AI-503', 'VT-ANP', 'BLR', 'HYD', NOW()::date + INTERVAL '1 day' + INTERVAL '6 hours', NOW()::date + INTERVAL '1 day' + INTERVAL '7 hours 30 minutes', 'SCHEDULED'),
-- VT-ALK flights
('FL-016', 'AI-143', 'VT-ALK', 'DEL', 'JFK', NOW()::date + INTERVAL '2 hours', NOW()::date + INTERVAL '18 hours', 'SCHEDULED'),
('FL-017', 'AI-144', 'VT-ALK', 'JFK', 'DEL', NOW()::date + INTERVAL '1 day' + INTERVAL '22 hours', NOW()::date + INTERVAL '2 days' + INTERVAL '12 hours', 'SCHEDULED'),
-- VT-ALM flights (based BOM)
('FL-018', 'AI-617', 'VT-ALM', 'BOM', 'MAA', NOW()::date + INTERVAL '6 hours 30 minutes', NOW()::date + INTERVAL '8 hours 15 minutes', 'SCHEDULED'),
('FL-019', 'AI-618', 'VT-ALM', 'MAA', 'BOM', NOW()::date + INTERVAL '9 hours 30 minutes', NOW()::date + INTERVAL '11 hours 15 minutes', 'SCHEDULED'),
-- VT-ANR flights (based MAA)
('FL-020', 'AI-543', 'VT-ANR', 'MAA', 'DEL', NOW()::date + INTERVAL '7 hours 30 minutes', NOW()::date + INTERVAL '10 hours 15 minutes', 'SCHEDULED');

-- ============================================================
-- 7. HANGAR AVAILABILITY
-- ============================================================
CREATE TABLE hangar_availability (
    hangar_id VARCHAR(15) PRIMARY KEY,
    station VARCHAR(5) NOT NULL,
    hangar_type VARCHAR(20) NOT NULL,
    capacity INTEGER NOT NULL,
    current_occupancy INTEGER NOT NULL DEFAULT 0,
    available_from TIMESTAMP NOT NULL,
    available_until TIMESTAMP NOT NULL
);

INSERT INTO hangar_availability VALUES
-- DEL hangars
('HGR-DEL-L1', 'DEL', 'LINE_MAINTENANCE', 3, 1, NOW()::date, NOW()::date + INTERVAL '7 days'),
('HGR-DEL-L2', 'DEL', 'LINE_MAINTENANCE', 2, 0, NOW()::date, NOW()::date + INTERVAL '7 days'),
('HGR-DEL-H1', 'DEL', 'HEAVY_CHECK', 1, 1, NOW()::date, NOW()::date + INTERVAL '30 days'),
('HGR-DEL-ES', 'DEL', 'ENGINE_SHOP', 1, 0, NOW()::date + INTERVAL '1 day', NOW()::date + INTERVAL '14 days'),
-- BOM hangars
('HGR-BOM-L1', 'BOM', 'LINE_MAINTENANCE', 2, 0, NOW()::date, NOW()::date + INTERVAL '7 days'),
('HGR-BOM-H1', 'BOM', 'HEAVY_CHECK', 1, 0, NOW()::date + INTERVAL '3 days', NOW()::date + INTERVAL '30 days'),
('HGR-BOM-ES', 'BOM', 'ENGINE_SHOP', 1, 0, NOW()::date + INTERVAL '2 days', NOW()::date + INTERVAL '14 days'),
-- BLR hangars
('HGR-BLR-L1', 'BLR', 'LINE_MAINTENANCE', 2, 1, NOW()::date, NOW()::date + INTERVAL '7 days'),
('HGR-BLR-H1', 'BLR', 'HEAVY_CHECK', 1, 0, NOW()::date + INTERVAL '5 days', NOW()::date + INTERVAL '30 days'),
-- MAA hangars
('HGR-MAA-L1', 'MAA', 'LINE_MAINTENANCE', 1, 0, NOW()::date, NOW()::date + INTERVAL '7 days'),
-- HYD hangars
('HGR-HYD-L1', 'HYD', 'LINE_MAINTENANCE', 1, 0, NOW()::date, NOW()::date + INTERVAL '7 days');

-- ============================================================
-- 8. ANOMALY ALERTS
-- ============================================================
CREATE TABLE anomaly_alerts (
    alert_id VARCHAR(20) PRIMARY KEY,
    aircraft_reg VARCHAR(10) NOT NULL REFERENCES aircraft_fleet(aircraft_reg),
    sensor_type VARCHAR(30) NOT NULL,
    engine_position VARCHAR(10) NOT NULL,
    severity VARCHAR(10) NOT NULL,
    anomaly_score DECIMAL(4,3) NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    predicted_failure_date DATE,
    status VARCHAR(15) NOT NULL DEFAULT 'NEW',
    description TEXT NOT NULL
);

INSERT INTO anomaly_alerts VALUES
('ALT-2026-0047', 'VT-ALJ', 'ENGINE_VIBRATION_N2', 'ENGINE_2', 'CRITICAL', 0.930, NOW() - INTERVAL '6 hours', (NOW() + INTERVAL '3 days')::date, 'NEW', 'CRITICAL: Engine #2 N2 vibration trending 26.7% above normal limit (3.80 mm/s vs 3.0 mm/s max). Consistent upward trend over 7 days correlating with rising oil temperature (+12C above limit) and EGT (+20C above limit). Pattern consistent with N2 turbine bearing degradation. Oil analysis confirms elevated Fe/Cr. Predicted failure within 72 hours. IMMEDIATE ACTION REQUIRED.'),
('ALT-2026-0048', 'VT-ALJ', 'OIL_TEMP', 'ENGINE_2', 'HIGH', 0.890, NOW() - INTERVAL '5 hours', (NOW() + INTERVAL '4 days')::date, 'NEW', 'Engine #2 oil temperature at 112C, exceeding 100C limit. 31.8% increase over 7 days. Correlates with N2 bearing degradation pattern. Cross-reference with ALT-2026-0047.'),
('ALT-2026-0049', 'VT-ALJ', 'EGT', 'ENGINE_2', 'HIGH', 0.880, NOW() - INTERVAL '4 hours', (NOW() + INTERVAL '5 days')::date, 'NEW', 'Engine #2 EGT at 920C, exceeding 900C limit. Steady increase consistent with bearing-induced friction. Cross-reference with ALT-2026-0047.'),
('ALT-2026-0050', 'VT-ANP', 'HYDRAULIC_PRESSURE', 'ENGINE_1', 'HIGH', 0.880, NOW() - INTERVAL '3 hours', (NOW() + INTERVAL '5 days')::date, 'NEW', 'Hydraulic System B pressure at 2200 PSI, 18.8% below minimum (2800 PSI). Declining trend over 3 days. Leak detected at pump case drain fitting. Temporary repair insufficient. Full pump seal replacement required.'),
('ALT-2026-0041', 'VT-ALQ', 'ENGINE_VIBRATION_N1', 'ENGINE_1', 'LOW', 0.350, NOW() - INTERVAL '2 days', NULL, 'ACKNOWLEDGED', 'Minor N1 vibration uptick at 1.41 mm/s. Within normal limits but trending slightly upward. Monitor.'),
('ALT-2026-0039', 'VT-ALK', 'ENGINE_VIBRATION_N1', 'ENGINE_1', 'MEDIUM', 0.450, NOW() - INTERVAL '5 days', NULL, 'ACKNOWLEDGED', 'N1 vibration elevated at 1.31 mm/s. Engine approaching 20000 hour mark. Schedule inspection at next convenient maintenance window.');

-- ============================================================
-- INDEXES for performance
-- ============================================================
CREATE INDEX idx_telemetry_aircraft ON sensor_telemetry(aircraft_reg, timestamp);
CREATE INDEX idx_telemetry_sensor ON sensor_telemetry(sensor_type, engine_position);
CREATE INDEX idx_maintenance_aircraft ON maintenance_history(aircraft_reg, start_date);
CREATE INDEX idx_lifecycle_aircraft ON component_lifecycle(aircraft_reg, status);
CREATE INDEX idx_alerts_status ON anomaly_alerts(status, severity);
CREATE INDEX idx_flights_aircraft ON flight_schedule(aircraft_reg, departure);
CREATE INDEX idx_hangar_station ON hangar_availability(station, hangar_type);

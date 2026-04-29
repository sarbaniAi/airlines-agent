-- ============================================================
-- Air India Pre-Flight Readiness & Dispatch Agent
-- Lakebase Seed Data
-- ============================================================

-- Drop tables if they exist (for re-seeding)
DROP TABLE IF EXISTS mel_items CASCADE;
DROP TABLE IF EXISTS aircraft_certificates CASCADE;
DROP TABLE IF EXISTS weather_conditions CASCADE;
DROP TABLE IF EXISTS regulatory_requirements CASCADE;
DROP TABLE IF EXISTS flight_schedule CASCADE;
DROP TABLE IF EXISTS crew_roster CASCADE;
DROP TABLE IF EXISTS aircraft_fleet CASCADE;

-- ============================================================
-- 1. AIRCRAFT FLEET
-- ============================================================
CREATE TABLE aircraft_fleet (
    aircraft_reg VARCHAR(10) PRIMARY KEY,
    aircraft_type VARCHAR(50) NOT NULL,
    model_variant VARCHAR(50),
    total_flight_hours INTEGER NOT NULL,
    last_c_check_date DATE,
    next_c_check_due DATE,
    base_airport VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'SERVICEABLE'
);

INSERT INTO aircraft_fleet VALUES
('VT-ALJ', 'Boeing 787-9', 'Dreamliner', 28450, '2025-11-15', '2026-11-15', 'DEL', 'SERVICEABLE'),
('VT-ALK', 'Boeing 787-9', 'Dreamliner', 31200, '2025-09-20', '2026-09-20', 'DEL', 'SERVICEABLE'),
('VT-ALL', 'Boeing 787-9', 'Dreamliner', 19800, '2026-01-10', '2027-01-10', 'BOM', 'SERVICEABLE'),
('VT-ALQ', 'Boeing 777-300ER', NULL, 42100, '2025-08-05', '2026-08-05', 'DEL', 'SERVICEABLE'),
('VT-ALR', 'Boeing 777-300ER', NULL, 38900, '2025-12-01', '2026-12-01', 'DEL', 'SERVICEABLE'),
('VT-ANA', 'Airbus A350-900', 'XWB', 8200, '2026-02-15', '2027-02-15', 'DEL', 'SERVICEABLE'),
('VT-ANB', 'Airbus A350-900', 'XWB', 7500, '2026-03-01', '2027-03-01', 'BOM', 'SERVICEABLE'),
('VT-EXA', 'Airbus A321neo', 'LR', 12400, '2025-10-20', '2026-10-20', 'DEL', 'SERVICEABLE'),
('VT-EXB', 'Airbus A321neo', 'LR', 11800, '2025-11-05', '2026-11-05', 'DEL', 'SERVICEABLE'),
('VT-EXC', 'Airbus A321neo', NULL, 15600, '2025-07-15', '2026-07-15', 'BOM', 'SERVICEABLE'),
('VT-EXD', 'Airbus A320neo', NULL, 22300, '2025-06-10', '2026-06-10', 'BLR', 'IN_MAINTENANCE'),
('VT-EXE', 'Airbus A320neo', NULL, 20100, '2025-09-25', '2026-09-25', 'BLR', 'SERVICEABLE'),
('VT-ALS', 'Boeing 777-200LR', NULL, 35600, '2025-10-10', '2026-10-10', 'DEL', 'SERVICEABLE'),
('VT-ALT', 'Boeing 787-8', 'Dreamliner', 26700, '2025-12-20', '2026-12-20', 'BOM', 'AOG'),
('VT-EXF', 'Airbus A321neo', NULL, 9800, '2026-01-25', '2027-01-25', 'DEL', 'SERVICEABLE');

-- ============================================================
-- 2. AIRCRAFT CERTIFICATES
-- ============================================================
CREATE TABLE aircraft_certificates (
    cert_id SERIAL PRIMARY KEY,
    aircraft_reg VARCHAR(10) REFERENCES aircraft_fleet(aircraft_reg),
    cert_type VARCHAR(30) NOT NULL,
    cert_number VARCHAR(50) NOT NULL,
    issuing_authority VARCHAR(20) NOT NULL,
    issue_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'VALID'
);

-- VT-ALQ certificates (KEY DEMO: Expired Canada COA)
INSERT INTO aircraft_certificates (aircraft_reg, cert_type, cert_number, issuing_authority, issue_date, expiry_date, status) VALUES
('VT-ALQ', 'AIRWORTHINESS', 'AW-2024-ALQ-001', 'DGCA', '2024-06-15', '2027-06-15', 'VALID'),
('VT-ALQ', 'RVSM', 'RVSM-ALQ-2024', 'DGCA', '2024-03-01', '2027-03-01', 'VALID'),
('VT-ALQ', 'ETOPS_180', 'ETOPS180-ALQ-2024', 'DGCA', '2024-04-10', '2027-04-10', 'VALID'),
('VT-ALQ', 'NOISE', 'NC-ALQ-2024-IN', 'DGCA', '2024-01-20', '2027-01-20', 'VALID'),
('VT-ALQ', 'INSURANCE', 'INS-ALQ-2026', 'DGCA', '2026-01-01', '2027-01-01', 'VALID'),
('VT-ALQ', 'RADIO_STATION', 'RS-ALQ-2024', 'DGCA', '2024-05-01', '2027-05-01', 'VALID'),
('VT-ALQ', 'COA_CANADA', 'COA-CA-ALQ-2024', 'TCCA', '2024-04-15', '2026-04-15', 'EXPIRED'),
('VT-ALQ', 'COA_UK', 'COA-UK-ALQ-2024', 'CAA_UK', '2024-06-01', '2027-06-01', 'VALID'),
('VT-ALQ', 'COA_USA', 'COA-US-ALQ-2024', 'FAA', '2024-05-20', '2027-05-20', 'VALID');

-- VT-ANA certificates (ETOPS expiring soon — but valid Canada COA)
INSERT INTO aircraft_certificates (aircraft_reg, cert_type, cert_number, issuing_authority, issue_date, expiry_date, status) VALUES
('VT-ANA', 'AIRWORTHINESS', 'AW-2025-ANA-001', 'DGCA', '2025-08-01', '2028-08-01', 'VALID'),
('VT-ANA', 'RVSM', 'RVSM-ANA-2025', 'DGCA', '2025-06-15', '2028-06-15', 'VALID'),
('VT-ANA', 'ETOPS_180', 'ETOPS180-ANA-2025', 'DGCA', '2025-05-10', '2026-05-10', 'EXPIRING_SOON'),
('VT-ANA', 'NOISE', 'NC-ANA-2025-IN', 'DGCA', '2025-03-01', '2028-03-01', 'VALID'),
('VT-ANA', 'INSURANCE', 'INS-ANA-2026', 'DGCA', '2026-01-01', '2027-01-01', 'VALID'),
('VT-ANA', 'RADIO_STATION', 'RS-ANA-2025', 'DGCA', '2025-04-01', '2028-04-01', 'VALID'),
('VT-ANA', 'COA_CANADA', 'COA-CA-ANA-2025', 'TCCA', '2025-07-01', '2027-07-01', 'VALID'),
('VT-ANA', 'COA_UK', 'COA-UK-ANA-2025', 'CAA_UK', '2025-08-15', '2028-08-15', 'VALID'),
('VT-ANA', 'COA_USA', 'COA-US-ANA-2025', 'FAA', '2025-06-20', '2028-06-20', 'VALID');

-- VT-ALJ certificates
INSERT INTO aircraft_certificates (aircraft_reg, cert_type, cert_number, issuing_authority, issue_date, expiry_date, status) VALUES
('VT-ALJ', 'AIRWORTHINESS', 'AW-2024-ALJ-001', 'DGCA', '2024-07-01', '2027-07-01', 'VALID'),
('VT-ALJ', 'RVSM', 'RVSM-ALJ-2024', 'DGCA', '2024-04-15', '2027-04-15', 'VALID'),
('VT-ALJ', 'ETOPS_180', 'ETOPS180-ALJ-2024', 'DGCA', '2024-06-20', '2027-06-20', 'VALID'),
('VT-ALJ', 'COA_UK', 'COA-UK-ALJ-2024', 'CAA_UK', '2024-08-01', '2027-08-01', 'VALID');

-- VT-ALR certificates
INSERT INTO aircraft_certificates (aircraft_reg, cert_type, cert_number, issuing_authority, issue_date, expiry_date, status) VALUES
('VT-ALR', 'AIRWORTHINESS', 'AW-2024-ALR-001', 'DGCA', '2024-09-01', '2027-09-01', 'VALID'),
('VT-ALR', 'RVSM', 'RVSM-ALR-2024', 'DGCA', '2024-07-10', '2027-07-10', 'VALID'),
('VT-ALR', 'ETOPS_180', 'ETOPS180-ALR-2024', 'DGCA', '2024-08-15', '2027-08-15', 'VALID'),
('VT-ALR', 'COA_USA', 'COA-US-ALR-2024', 'FAA', '2024-09-20', '2027-09-20', 'VALID');

-- VT-EXA certificates
INSERT INTO aircraft_certificates (aircraft_reg, cert_type, cert_number, issuing_authority, issue_date, expiry_date, status) VALUES
('VT-EXA', 'AIRWORTHINESS', 'AW-2025-EXA-001', 'DGCA', '2025-02-01', '2028-02-01', 'VALID'),
('VT-EXA', 'RVSM', 'RVSM-EXA-2025', 'DGCA', '2025-01-15', '2028-01-15', 'VALID');

-- ============================================================
-- 3. MEL ITEMS (Minimum Equipment List)
-- ============================================================
CREATE TABLE mel_items (
    mel_id SERIAL PRIMARY KEY,
    aircraft_reg VARCHAR(10) REFERENCES aircraft_fleet(aircraft_reg),
    item_code VARCHAR(20) NOT NULL,
    ata_chapter VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(5) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    deferral_date DATE NOT NULL,
    expiry_date DATE
);

-- VT-ALQ MEL items (KEY DEMO: Category A item expiring tomorrow)
INSERT INTO mel_items (aircraft_reg, item_code, ata_chapter, description, category, status, deferral_date, expiry_date) VALUES
('VT-ALQ', '21-51-01', 'ATA-21 Air Conditioning', 'Pack valve #2 intermittent fault — operates on single pack', 'A', 'DEFERRED', CURRENT_DATE - INTERVAL '2 days', CURRENT_DATE + INTERVAL '1 day'),
('VT-ALQ', '34-11-02', 'ATA-34 Navigation', 'Weather radar tilt mechanism sluggish in manual mode', 'C', 'DEFERRED', '2026-03-15', '2026-07-13'),
('VT-ALQ', '29-11-01', 'ATA-29 Hydraulic Power', 'Hydraulic system B quantity indicator fluctuation', 'B', 'DEFERRED', '2026-04-20', '2026-04-30'),
('VT-ALQ', '33-12-01', 'ATA-33 Lights', 'Logo light #1 (left) inoperative', 'D', 'DEFERRED', '2026-02-10', NULL);

-- VT-ANA MEL items
INSERT INTO mel_items (aircraft_reg, item_code, ata_chapter, description, category, status, deferral_date, expiry_date) VALUES
('VT-ANA', '26-11-01', 'ATA-26 Fire Protection', 'APU fire detection loop B intermittent', 'B', 'DEFERRED', '2026-04-22', '2026-05-02'),
('VT-ANA', '32-41-01', 'ATA-32 Landing Gear', 'Nose gear steering shimmy dampener seepage noted', 'C', 'DEFERRED', '2026-03-01', '2026-06-29');

-- VT-ALJ MEL items
INSERT INTO mel_items (aircraft_reg, item_code, ata_chapter, description, category, status, deferral_date, expiry_date) VALUES
('VT-ALJ', '23-11-01', 'ATA-23 Communications', 'VHF Radio #3 inoperative', 'C', 'DEFERRED', '2026-02-20', '2026-06-20'),
('VT-ALJ', '35-11-01', 'ATA-35 Oxygen', 'Crew oxygen pressure low indication on gauge (bottle checked OK)', 'B', 'DEFERRED', '2026-04-25', '2026-05-05'),
('VT-ALJ', '49-11-01', 'ATA-49 APU', 'APU bleed air valve slow to respond', 'C', 'DEFERRED', '2026-03-10', '2026-07-08');

-- VT-ALK MEL items
INSERT INTO mel_items (aircraft_reg, item_code, ata_chapter, description, category, status, deferral_date, expiry_date) VALUES
('VT-ALK', '27-51-01', 'ATA-27 Flight Controls', 'Spoiler panel #4 slow retraction', 'B', 'DEFERRED', '2026-04-18', '2026-04-28'),
('VT-ALK', '22-11-01', 'ATA-22 Auto Flight', 'Autothrottle intermittent disconnect', 'A', 'DEFERRED', CURRENT_DATE - INTERVAL '1 day', CURRENT_DATE + INTERVAL '2 days');

-- VT-EXA MEL items
INSERT INTO mel_items (aircraft_reg, item_code, ata_chapter, description, category, status, deferral_date, expiry_date) VALUES
('VT-EXA', '36-11-01', 'ATA-36 Pneumatics', 'Bleed air pre-cooler outlet temp slightly elevated', 'C', 'DEFERRED', '2026-04-01', '2026-07-30'),
('VT-EXA', '24-21-01', 'ATA-24 Electrical Power', 'Generator #1 BPCU minor fault logged', 'B', 'DEFERRED', '2026-04-20', '2026-04-30');

-- VT-ALR MEL items
INSERT INTO mel_items (aircraft_reg, item_code, ata_chapter, description, category, status, deferral_date, expiry_date) VALUES
('VT-ALR', '28-21-01', 'ATA-28 Fuel', 'Centre tank fuel pump #1 low pressure indication', 'B', 'DEFERRED', '2026-04-22', '2026-05-02'),
('VT-ALR', '31-31-01', 'ATA-31 Instruments', 'Standby altimeter barometric knob stiff', 'C', 'DEFERRED', '2026-03-15', '2026-07-13');

-- VT-EXB MEL items
INSERT INTO mel_items (aircraft_reg, item_code, ata_chapter, description, category, status, deferral_date, expiry_date) VALUES
('VT-EXB', '73-11-01', 'ATA-73 Engine Fuel', 'Engine #2 fuel flow indicator reads 2% high', 'C', 'DEFERRED', '2026-04-10', '2026-08-08'),
('VT-EXB', '30-21-01', 'ATA-30 Ice/Rain Protection', 'Windshield rain repellent system inoperative', 'C', 'DEFERRED', '2026-04-05', '2026-08-03');

-- Rectified items (for history)
INSERT INTO mel_items (aircraft_reg, item_code, ata_chapter, description, category, status, deferral_date, expiry_date) VALUES
('VT-ALQ', '25-21-01', 'ATA-25 Equipment', 'Galley oven #3 inoperative', 'D', 'RECTIFIED', '2026-03-01', NULL),
('VT-ANA', '38-11-01', 'ATA-38 Water/Waste', 'Aft lavatory water heater inoperative', 'D', 'RECTIFIED', '2026-02-15', NULL),
('VT-ALJ', '44-11-01', 'ATA-44 Cabin Systems', 'IFE screen seat 22A inoperative', 'D', 'RECTIFIED', '2026-01-20', NULL);

-- ============================================================
-- 4. CREW ROSTER
-- ============================================================
CREATE TABLE crew_roster (
    crew_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    rank VARCHAR(30) NOT NULL,
    license_type VARCHAR(30),
    base_airport VARCHAR(10) NOT NULL,
    duty_hours_last_7d DECIMAL(5,1) NOT NULL,
    duty_hours_last_28d DECIMAL(5,1) NOT NULL,
    rest_hours_since_last_duty DECIMAL(5,1) NOT NULL,
    fatigue_risk_score DECIMAL(4,1) NOT NULL,
    medical_expiry DATE NOT NULL,
    route_qualifications TEXT[]
);

INSERT INTO crew_roster VALUES
-- Captains
('CPT-001', 'Capt. Vikram Sharma', 'CAPTAIN', 'ATPL', 'DEL', 38.5, 142.0, 16.0, 22.0, '2027-03-15', ARRAY['NAM', 'EUR', 'APAC', 'ETOPS', 'CAT_IIIB', 'RVSM', 'PBN']),
('CPT-002', 'Capt. Priya Menon', 'CAPTAIN', 'ATPL', 'DEL', 42.0, 155.0, 14.0, 30.0, '2026-12-01', ARRAY['NAM', 'EUR', 'APAC', 'ETOPS', 'CAT_IIIA', 'RVSM']),
('CPT-003', 'Capt. Rajesh Iyer', 'CAPTAIN', 'ATPL', 'BOM', 35.0, 130.0, 18.0, 18.0, '2027-06-20', ARRAY['EUR', 'APAC', 'ETOPS', 'CAT_IIIB', 'RVSM', 'PBN']),
('CPT-004', 'Capt. Ananya Singh', 'CAPTAIN', 'ATPL', 'DEL', 40.0, 148.0, 13.5, 28.0, '2027-01-10', ARRAY['NAM', 'EUR', 'ETOPS', 'CAT_IIIA', 'RVSM']),
('CPT-005', 'Capt. Suresh Nair', 'CAPTAIN', 'ATPL', 'DEL', 44.0, 160.0, 12.5, 35.0, '2026-04-20', ARRAY['NAM', 'EUR', 'APAC', 'ETOPS', 'CAT_IIIB', 'RVSM', 'PBN']),
('CPT-006', 'Capt. Deepa Kulkarni', 'CAPTAIN', 'ATPL', 'BOM', 30.0, 120.0, 20.0, 15.0, '2027-09-01', ARRAY['APAC', 'EUR', 'ETOPS', 'CAT_IIIA', 'RVSM']),
('CPT-007', 'Capt. Ravi Patel', 'CAPTAIN', 'ATPL', 'BLR', 28.0, 110.0, 22.0, 12.0, '2027-04-15', ARRAY['APAC', 'DOM', 'CAT_IIIA', 'RVSM']),

-- First Officers
('FO-001', 'FO Arjun Kapoor', 'FIRST_OFFICER', 'CPL', 'DEL', 54.0, 170.0, 10.5, 62.0, '2027-02-28', ARRAY['NAM', 'EUR', 'ETOPS', 'RVSM']),
('FO-002', 'FO Neha Gupta', 'FIRST_OFFICER', 'CPL', 'DEL', 36.0, 138.0, 15.0, 24.0, '2027-05-15', ARRAY['NAM', 'EUR', 'APAC', 'ETOPS', 'RVSM']),
('FO-003', 'FO Karthik Raman', 'FIRST_OFFICER', 'CPL', 'BOM', 40.0, 145.0, 14.0, 28.0, '2027-01-20', ARRAY['EUR', 'APAC', 'ETOPS', 'RVSM']),
('FO-004', 'FO Isha Mehta', 'FIRST_OFFICER', 'CPL', 'DEL', 32.0, 125.0, 18.0, 20.0, '2027-07-10', ARRAY['NAM', 'EUR', 'ETOPS', 'RVSM', 'PBN']),
('FO-005', 'FO Aditya Joshi', 'FIRST_OFFICER', 'CPL', 'DEL', 45.0, 155.0, 13.0, 38.0, '2027-03-01', ARRAY['NAM', 'APAC', 'ETOPS', 'RVSM']),
('FO-006', 'FO Sanya Reddy', 'FIRST_OFFICER', 'CPL', 'BLR', 28.0, 108.0, 20.0, 16.0, '2027-08-15', ARRAY['APAC', 'DOM', 'RVSM']),

-- Senior First Officers
('SFO-001', 'SFO Amit Verma', 'SENIOR_FIRST_OFFICER', 'CPL', 'DEL', 38.0, 140.0, 16.5, 25.0, '2027-04-20', ARRAY['NAM', 'EUR', 'APAC', 'ETOPS', 'RVSM', 'PBN']),
('SFO-002', 'SFO Pooja Deshmukh', 'SENIOR_FIRST_OFFICER', 'CPL', 'BOM', 34.0, 132.0, 17.0, 22.0, '2027-06-01', ARRAY['EUR', 'APAC', 'ETOPS', 'RVSM']),

-- Cabin Crew Leads
('CCL-001', 'Meera Khanna', 'CABIN_CREW_LEAD', NULL, 'DEL', 42.0, 150.0, 14.0, 26.0, '2027-02-15', ARRAY['NAM', 'EUR', 'APAC', 'WIDEBODY']),
('CCL-002', 'Rohit Saxena', 'CABIN_CREW_LEAD', NULL, 'DEL', 38.0, 140.0, 16.0, 20.0, '2027-05-20', ARRAY['NAM', 'EUR', 'WIDEBODY']),
('CCL-003', 'Sneha Pillai', 'CABIN_CREW_LEAD', NULL, 'BOM', 36.0, 135.0, 15.0, 22.0, '2027-03-10', ARRAY['EUR', 'APAC', 'WIDEBODY']),
('CCL-004', 'Vivek Choudhary', 'CABIN_CREW_LEAD', NULL, 'DEL', 40.0, 145.0, 13.0, 30.0, '2027-01-01', ARRAY['NAM', 'EUR', 'APAC', 'WIDEBODY']),
('CCL-005', 'Divya Krishnan', 'CABIN_CREW_LEAD', NULL, 'BLR', 30.0, 118.0, 18.0, 15.0, '2027-07-01', ARRAY['APAC', 'DOM', 'NARROWBODY']),

-- Additional crew
('FO-007', 'FO Manish Tiwari', 'FIRST_OFFICER', 'CPL', 'DEL', 48.0, 162.0, 11.0, 45.0, '2027-04-01', ARRAY['NAM', 'EUR', 'ETOPS', 'RVSM']),
('CPT-008', 'Capt. Farhan Ahmed', 'CAPTAIN', 'ATPL', 'DEL', 25.0, 100.0, 24.0, 10.0, '2027-08-20', ARRAY['NAM', 'EUR', 'APAC', 'ETOPS', 'CAT_IIIB', 'RVSM', 'PBN']),
('FO-008', 'FO Tanvi Bhat', 'FIRST_OFFICER', 'CPL', 'BOM', 34.0, 128.0, 16.0, 20.0, '2027-06-15', ARRAY['APAC', 'EUR', 'ETOPS', 'RVSM']),
('CCL-006', 'Anjali Shetty', 'CABIN_CREW_LEAD', NULL, 'BOM', 32.0, 122.0, 17.0, 18.0, '2027-05-01', ARRAY['APAC', 'EUR', 'WIDEBODY']);

-- ============================================================
-- 5. FLIGHT SCHEDULE (today's flights)
-- ============================================================
CREATE TABLE flight_schedule (
    flight_id VARCHAR(20) PRIMARY KEY,
    flight_number VARCHAR(10) NOT NULL,
    origin VARCHAR(10) NOT NULL,
    destination VARCHAR(10) NOT NULL,
    scheduled_departure TIMESTAMP NOT NULL,
    scheduled_arrival TIMESTAMP NOT NULL,
    aircraft_reg VARCHAR(10) REFERENCES aircraft_fleet(aircraft_reg),
    captain_id VARCHAR(20) REFERENCES crew_roster(crew_id),
    first_officer_id VARCHAR(20) REFERENCES crew_roster(crew_id),
    pax_count INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'SCHEDULED'
);

INSERT INTO flight_schedule VALUES
-- KEY DEMO FLIGHT: AI-302 DEL -> YYZ (triggers multiple issues)
('AI-302', 'AI302', 'DEL', 'YYZ', CURRENT_DATE + INTERVAL '14 hours 30 minutes', CURRENT_DATE + INTERVAL '29 hours', 'VT-ALQ', 'CPT-001', 'FO-001', 298, 'SCHEDULED'),
-- Other flights for today
('AI-176', 'AI176', 'DEL', 'LHR', CURRENT_DATE + INTERVAL '9 hours', CURRENT_DATE + INTERVAL '18 hours 30 minutes', 'VT-ALJ', 'CPT-002', 'FO-002', 256, 'SCHEDULED'),
('AI-101', 'AI101', 'DEL', 'JFK', CURRENT_DATE + INTERVAL '22 hours', CURRENT_DATE + INTERVAL '38 hours', 'VT-ANA', 'CPT-004', 'SFO-001', 310, 'SCHEDULED'),
('AI-127', 'AI127', 'BOM', 'SIN', CURRENT_DATE + INTERVAL '7 hours 30 minutes', CURRENT_DATE + INTERVAL '13 hours', 'VT-ALL', 'CPT-003', 'FO-003', 224, 'SCHEDULED'),
('AI-680', 'AI680', 'DEL', 'BOM', CURRENT_DATE + INTERVAL '6 hours', CURRENT_DATE + INTERVAL '8 hours 15 minutes', 'VT-EXA', 'CPT-007', 'FO-006', 180, 'SCHEDULED'),
('AI-505', 'AI505', 'BLR', 'DEL', CURRENT_DATE + INTERVAL '8 hours', CURRENT_DATE + INTERVAL '10 hours 45 minutes', 'VT-EXE', 'CPT-006', 'FO-008', 174, 'SCHEDULED'),
('AI-191', 'AI191', 'DEL', 'SFO', CURRENT_DATE + INTERVAL '3 hours', CURRENT_DATE + INTERVAL '20 hours', 'VT-ALR', 'CPT-008', 'FO-004', 286, 'BOARDING'),
('AI-864', 'AI864', 'BOM', 'LHR', CURRENT_DATE + INTERVAL '2 hours', CURRENT_DATE + INTERVAL '11 hours 30 minutes', 'VT-ANB', 'CPT-006', 'SFO-002', 268, 'DEPARTED'),
('AI-946', 'AI946', 'DEL', 'BLR', CURRENT_DATE + INTERVAL '10 hours 30 minutes', CURRENT_DATE + INTERVAL '13 hours 15 minutes', 'VT-EXB', 'CPT-005', 'FO-005', 182, 'SCHEDULED'),
('AI-308', 'AI308', 'DEL', 'YVR', CURRENT_DATE + INTERVAL '16 hours', CURRENT_DATE + INTERVAL '32 hours', 'VT-ALS', 'CPT-001', 'FO-007', 275, 'SCHEDULED');

-- ============================================================
-- 6. WEATHER CONDITIONS
-- ============================================================
CREATE TABLE weather_conditions (
    weather_id SERIAL PRIMARY KEY,
    airport_code VARCHAR(10) NOT NULL,
    observation_time TIMESTAMP NOT NULL,
    temperature_c DECIMAL(4,1) NOT NULL,
    visibility_km DECIMAL(5,1) NOT NULL,
    wind_speed_kts INTEGER NOT NULL,
    wind_direction INTEGER NOT NULL,
    ceiling_ft INTEGER,
    conditions VARCHAR(20) NOT NULL,
    metar_raw TEXT NOT NULL,
    severity VARCHAR(10) NOT NULL DEFAULT 'GREEN'
);

INSERT INTO weather_conditions (airport_code, observation_time, temperature_c, visibility_km, wind_speed_kts, wind_direction, ceiling_ft, conditions, metar_raw, severity) VALUES
('DEL', CURRENT_TIMESTAMP, 34.0, 10.0, 8, 270, 25000, 'CAVOK', 'METAR VIDP ' || TO_CHAR(CURRENT_TIMESTAMP, 'DDHHnn') || 'Z 27008KT CAVOK 34/18 Q1008 NOSIG', 'GREEN'),
('BOM', CURRENT_TIMESTAMP, 32.0, 8.0, 12, 240, 4500, 'SCT', 'METAR VABB ' || TO_CHAR(CURRENT_TIMESTAMP, 'DDHHnn') || 'Z 24012KT 8000 SCT045 32/24 Q1006 NOSIG', 'GREEN'),
('YYZ', CURRENT_TIMESTAMP, -2.0, 2.5, 18, 320, 800, 'SN', 'METAR CYYZ ' || TO_CHAR(CURRENT_TIMESTAMP, 'DDHHnn') || 'Z 32018G28KT 2500 -SN BKN008 OVC015 M02/M05 A2968 RMK SN2SC5 SLP054', 'AMBER'),
('LHR', CURRENT_TIMESTAMP, 12.0, 10.0, 14, 250, 3500, 'SCT', 'METAR EGLL ' || TO_CHAR(CURRENT_TIMESTAMP, 'DDHHnn') || 'Z 25014KT 9999 SCT035 12/06 Q1022 NOSIG', 'GREEN'),
('SIN', CURRENT_TIMESTAMP, 30.0, 6.0, 6, 180, 5000, 'SCT', 'METAR WSSS ' || TO_CHAR(CURRENT_TIMESTAMP, 'DDHHnn') || 'Z 18006KT 6000 SCT050 30/25 Q1010 NOSIG', 'GREEN'),
('BLR', CURRENT_TIMESTAMP, 28.0, 10.0, 10, 200, 20000, 'CAVOK', 'METAR VOBL ' || TO_CHAR(CURRENT_TIMESTAMP, 'DDHHnn') || 'Z 20010KT CAVOK 28/16 Q1012 NOSIG', 'GREEN'),
('JFK', CURRENT_TIMESTAMP, 15.0, 10.0, 10, 210, 8000, 'SCT', 'METAR KJFK ' || TO_CHAR(CURRENT_TIMESTAMP, 'DDHHnn') || 'Z 21010KT 9999 SCT080 15/08 A3012 NOSIG', 'GREEN'),
('SFO', CURRENT_TIMESTAMP, 14.0, 10.0, 16, 290, 4000, 'SCT', 'METAR KSFO ' || TO_CHAR(CURRENT_TIMESTAMP, 'DDHHnn') || 'Z 29016KT 9999 SCT040 14/08 A3008 NOSIG', 'GREEN'),
('YVR', CURRENT_TIMESTAMP, 8.0, 5.0, 12, 180, 2500, 'BKN', 'METAR CYVR ' || TO_CHAR(CURRENT_TIMESTAMP, 'DDHHnn') || 'Z 18012KT 5000 -RA BKN025 08/05 A2992 NOSIG', 'GREEN');

-- ============================================================
-- 7. REGULATORY REQUIREMENTS
-- ============================================================
CREATE TABLE regulatory_requirements (
    req_id SERIAL PRIMARY KEY,
    destination_country VARCHAR(50) NOT NULL,
    requirement_type VARCHAR(20) NOT NULL,
    description TEXT NOT NULL,
    mandatory BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO regulatory_requirements (destination_country, requirement_type, description, mandatory) VALUES
-- Canada
('Canada', 'COA', 'Canadian Operating Authorization (COA) issued by TCCA required for all foreign carriers operating to/from Canada', TRUE),
('Canada', 'RVSM', 'RVSM approval required for North Atlantic airspace operations', TRUE),
('Canada', 'ETOPS', 'ETOPS-180 approval required for overwater segments exceeding 60 minutes from diversion airport', TRUE),
('Canada', 'PBN', 'PBN (Performance Based Navigation) capability required for Canadian RNAV routes', TRUE),
('Canada', 'NOISE', 'ICAO Chapter 4 noise certification required for operations at YYZ/YVR', FALSE),

-- United Kingdom
('United Kingdom', 'COA', 'UK Third Country Operator (TCO) authorization required post-Brexit', TRUE),
('United Kingdom', 'RVSM', 'RVSM approval required for European airspace', TRUE),
('United Kingdom', 'ETOPS', 'ETOPS approval required for overwater segments', TRUE),
('United Kingdom', 'NOISE', 'Chapter 4 noise certification required', TRUE),

-- United States
('United States', 'COA', 'FAA Part 129 Foreign Air Carrier permit required', TRUE),
('United States', 'RVSM', 'RVSM approval for domestic and oceanic airspace', TRUE),
('United States', 'ETOPS', 'ETOPS-180 for Pacific/Atlantic overwater segments', TRUE),
('United States', 'PBN', 'PBN capability required for US RNAV/RNP approaches', FALSE),

-- Singapore
('Singapore', 'COA', 'CAAS Air Operator Permit recognition', TRUE),
('Singapore', 'RVSM', 'RVSM approval for South East Asian airspace', TRUE),

-- India (domestic)
('India', 'COA', 'DGCA Air Operator Certificate — home carrier', TRUE),
('India', 'RVSM', 'RVSM approval for Indian domestic airspace above FL290', TRUE);

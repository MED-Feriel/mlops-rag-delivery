-- Migration 001 — Schéma plateforme de livraison

CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    order_number    VARCHAR(20)  UNIQUE NOT NULL,
    customer_name   VARCHAR(100) NOT NULL,
    customer_email  VARCHAR(150),
    customer_address TEXT        NOT NULL,
    city            VARCHAR(100),
    status          VARCHAR(20)  DEFAULT 'pending'
                    CHECK (status IN ('pending','confirmed','in_transit','delivered','failed','cancelled')),
    total_amount    DECIMAL(10,2),
    created_at      TIMESTAMP    DEFAULT NOW(),
    estimated_delivery TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drivers (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(100) NOT NULL,
    phone           VARCHAR(20),
    vehicle_type    VARCHAR(50)  CHECK (vehicle_type IN ('vélo','scooter','voiture','camionnette','moto')),
    rating          DECIMAL(3,2) DEFAULT 5.00,
    is_active       BOOLEAN      DEFAULT TRUE,
    created_at      TIMESTAMP    DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deliveries (
    id              SERIAL PRIMARY KEY,
    order_id        INTEGER      NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    driver_id       INTEGER      REFERENCES drivers(id),
    pickup_time     TIMESTAMP,
    delivery_time   TIMESTAMP,
    actual_delivery TIMESTAMP,
    distance_km     DECIMAL(8,2),
    duration_min    INTEGER,
    status          VARCHAR(20)  DEFAULT 'assigned'
                    CHECK (status IN ('assigned','picked_up','in_transit','delivered','failed','returned')),
    created_at      TIMESTAMP    DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS incidents (
    id              SERIAL PRIMARY KEY,
    delivery_id     INTEGER      NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
    incident_type   VARCHAR(50)  NOT NULL
                    CHECK (incident_type IN ('late_delivery','package_damaged','package_lost',
                                            'address_not_found','customer_absent','vehicle_breakdown',
                                            'weather_delay','refused_delivery','other')),
    description     TEXT         NOT NULL,
    severity        VARCHAR(10)  DEFAULT 'medium'
                    CHECK (severity IN ('low','medium','high','critical')),
    status          VARCHAR(20)  DEFAULT 'open'
                    CHECK (status IN ('open','in_progress','resolved','closed')),
    reported_at     TIMESTAMP    DEFAULT NOW(),
    resolved_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS delivery_logs (
    id              SERIAL PRIMARY KEY,
    delivery_id     INTEGER      NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
    event_type      VARCHAR(50)  NOT NULL,
    message         TEXT         NOT NULL,
    location_lat    DECIMAL(10,8),
    location_lng    DECIMAL(11,8),
    logged_at       TIMESTAMP    DEFAULT NOW()
);

-- Index
CREATE INDEX IF NOT EXISTS idx_orders_status       ON orders(status);
CREATE INDEX IF NOT EXISTS idx_deliveries_order_id ON deliveries(order_id);
CREATE INDEX IF NOT EXISTS idx_incidents_severity  ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_logs_delivery_id    ON delivery_logs(delivery_id);

DO $$ BEGIN
    RAISE NOTICE '✅ Migration 001 appliquée';
END $$;

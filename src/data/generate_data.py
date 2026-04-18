"""
Génération de données synthétiques — Sprint 5 MLOPS-104
Cible : 1000+ enregistrements dans delivery_db
"""

import os
import sys
import random
from datetime import datetime, timedelta

import psycopg2
from faker import Faker
from dotenv import load_dotenv

load_dotenv()

fake = Faker("fr_FR")
random.seed(42)

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "delivery_db"),
    "user": os.getenv("POSTGRES_USER", "raguser"),
    "password": os.getenv("POSTGRES_PASSWORD", "ragpassword"),
}

VEHICLE_TYPES = ["vélo", "scooter", "voiture", "camionnette", "moto"]
ORDER_STATUSES = [
    "pending",
    "confirmed",
    "in_transit",
    "delivered",
    "delivered",
    "delivered",
    "failed",
    "cancelled",
]
DELIV_STATUSES = [
    "assigned",
    "picked_up",
    "in_transit",
    "delivered",
    "delivered",
    "failed",
    "returned",
]
INCIDENT_TYPES = [
    "late_delivery",
    "package_damaged",
    "package_lost",
    "address_not_found",
    "customer_absent",
    "vehicle_breakdown",
    "weather_delay",
    "refused_delivery",
    "other",
]
SEVERITIES = ["low", "low", "medium", "medium", "high", "critical"]
CITIES = [
    "Alger",
    "Oran",
    "Constantine",
    "Annaba",
    "Blida",
    "Tlemcen",
    "Sétif",
    "Batna",
    "Béjaïa",
    "Sidi Bel Abbès",
]


def random_date(days_back=180):
    start = datetime.now() - timedelta(days=days_back)
    return start + timedelta(seconds=random.randint(0, days_back * 86400))


def generate_drivers(cur, n=50):
    print(f"  → {n} chauffeurs...")
    for _ in range(n):
        cur.execute(
            """
            INSERT INTO drivers (full_name, phone, vehicle_type, rating, is_active)
            VALUES (%s, %s, %s, %s, %s)
        """,
            (
                fake.name(),
                fake.phone_number(),
                random.choice(VEHICLE_TYPES),
                round(random.uniform(3.0, 5.0), 2),
                random.random() > 0.1,
            ),
        )
    print(f"  ✅ {n} chauffeurs créés")


def generate_orders(cur, n=1000):
    print(f"  → {n} commandes...")
    for i in range(n):
        created = random_date(180)
        cur.execute(
            """
            INSERT INTO orders
              (order_number, customer_name, customer_email, customer_address,
               city, status, total_amount, created_at, estimated_delivery)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
            (
                f"ORD-{i+1:05d}",
                fake.name(),
                fake.email(),
                fake.street_address(),
                random.choice(CITIES),
                random.choice(ORDER_STATUSES),
                round(random.uniform(500, 50000), 2),
                created,
                created + timedelta(hours=random.randint(2, 72)),
            ),
        )
    print(f"  ✅ {n} commandes créées")


def generate_deliveries(cur):
    print("  → Livraisons...")
    cur.execute("SELECT id, created_at, status FROM orders")
    orders = cur.fetchall()
    cur.execute("SELECT id FROM drivers")
    driver_ids = [r[0] for r in cur.fetchall()]

    count = 0
    for order_id, created_at, order_status in orders:
        if order_status in ("cancelled", "pending"):
            continue
        pickup = created_at + timedelta(minutes=random.randint(30, 180))
        planned = pickup + timedelta(minutes=random.randint(20, 120))
        actual = (
            planned + timedelta(minutes=random.randint(-30, 60))
            if order_status == "delivered"
            else None
        )
        cur.execute(
            """
            INSERT INTO deliveries
              (order_id, driver_id, pickup_time, delivery_time,
               actual_delivery, distance_km, duration_min, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
            (
                order_id,
                random.choice(driver_ids),
                pickup,
                planned,
                actual,
                round(random.uniform(0.5, 45.0), 2),
                random.randint(10, 180),
                random.choice(DELIV_STATUSES),
            ),
        )
        count += 1
    print(f"  ✅ {count} livraisons créées")


def generate_incidents(cur, rate=0.3):
    print(f"  → Incidents (taux {int(rate*100)}%)...")
    cur.execute("SELECT id, created_at FROM deliveries")
    deliveries = cur.fetchall()
    targets = random.sample(deliveries, k=int(len(deliveries) * rate))

    for delivery_id, created_at in targets:
        reported = created_at + timedelta(minutes=random.randint(5, 120))
        resolved = (
            reported + timedelta(hours=random.randint(1, 48))
            if random.random() > 0.3
            else None
        )
        cur.execute(
            """
            INSERT INTO incidents
              (delivery_id, incident_type, description, severity, status, reported_at, resolved_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
            (
                delivery_id,
                random.choice(INCIDENT_TYPES),
                fake.sentence(nb_words=random.randint(8, 20)),
                random.choice(SEVERITIES),
                "resolved" if resolved else "open",
                reported,
                resolved,
            ),
        )
    print(f"  ✅ {len(targets)} incidents créés")


def generate_logs(cur):
    print("  → Logs de suivi...")
    cur.execute("SELECT id, created_at FROM deliveries")
    deliveries = cur.fetchall()
    EVENT_TYPES = [
        "status_change",
        "location_update",
        "driver_note",
        "customer_contact",
        "system_event",
    ]
    count = 0
    for delivery_id, created_at in deliveries:
        for j in range(random.randint(1, 6)):
            cur.execute(
                """
                INSERT INTO delivery_logs
                  (delivery_id, event_type, message, location_lat, location_lng, logged_at)
                VALUES (%s,%s,%s,%s,%s,%s)
            """,
                (
                    delivery_id,
                    random.choice(EVENT_TYPES),
                    fake.sentence(nb_words=random.randint(5, 15)),
                    round(random.uniform(33.0, 37.0), 8),
                    round(random.uniform(-2.0, 8.0), 8),
                    created_at + timedelta(minutes=j * random.randint(5, 30)),
                ),
            )
            count += 1
    print(f"  ✅ {count} logs créés")


def verify(cur):
    tables = ["orders", "drivers", "deliveries", "incidents", "delivery_logs"]
    print("\n📊 Vérification :")
    print("─" * 40)
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        n = cur.fetchone()[0]
        print(f"  {'✅' if n > 0 else '❌'} {t:<20} : {n:>6} enregistrements")
    print("\n📈 Statuts commandes :")
    cur.execute(
        "SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY COUNT(*) DESC"
    )
    for row in cur.fetchall():
        print(f"  • {row[0]:<15} : {row[1]}")


def main():
    print("🚀 Génération des données synthétiques\n")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        cur = conn.cursor()
        print("✅ Connexion PostgreSQL OK\n")
    except Exception as e:
        print(f"❌ Connexion échouée : {e}")
        sys.exit(1)

    try:
        generate_drivers(cur)
        conn.commit()
        generate_orders(cur)
        conn.commit()
        generate_deliveries(cur)
        conn.commit()
        generate_incidents(cur)
        conn.commit()
        generate_logs(cur)
        conn.commit()
        verify(cur)
        print("\n✅ Terminé avec succès !")
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Erreur : {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

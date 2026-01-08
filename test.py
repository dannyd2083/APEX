import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME"),
        sslmode="require",
        connect_timeout=30
    )
    print("✓ Connection successful!")
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    print(f"Connected to: {cursor.fetchone()[0]}")
    conn.close()
except Exception as e:
    print(f"✗ Connection failed: {e}")
    print("\nTrying without SSL verification...")
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            dbname=os.getenv("DB_NAME"),
            sslmode="prefer"
        )
        print("✓ Connection successful with relaxed SSL!")
        conn.close()
    except Exception as e2:
        print(f"✗ Still failed: {e2}")
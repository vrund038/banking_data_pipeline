import boto3
from kafka import KafkaConsumer
import json
import pandas as pd
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

TOPICS = [
    "banking_server.public.customers",
    "banking_server.public.accounts",
    "banking_server.public.transactions",
]

consumer = KafkaConsumer(
    *TOPICS,
    bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP"),
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    group_id=os.getenv("KAFKA_GROUP"),
    value_deserializer=lambda x: json.loads(x.decode("utf-8")),
)

s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv("MINIO_ENDPOINT"),
    aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"),
)

bucket = os.getenv("MINIO_BUCKET")

# Create bucket if not exists
existing = [b["Name"] for b in s3.list_buckets()["Buckets"]]
if bucket not in existing:
    s3.create_bucket(Bucket=bucket)
    print(f"Created bucket: {bucket}")

print(" Connected to Kafka. Listening for messages...")

batch_size = 10   # 🔥 LOWERED for safety
buffer = {t: [] for t in TOPICS}

def write_to_minio(table, records):
    if not records:
        return

    df = pd.DataFrame(records)

    date_str = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%H%M%S%f")

    local_file = f"{table}_{ts}.parquet"
    s3_key = f"{table}/date={date_str}/{local_file}"

    df.to_parquet(local_file, index=False)  # uses pyarrow if available

    s3.upload_file(local_file, bucket, s3_key)
    os.remove(local_file)

    print(f" Uploaded {len(records)} rows -> s3://{bucket}/{s3_key}")


for msg in consumer:
    topic = msg.topic
    event = msg.value

    payload = event.get("payload")
    if not payload:
        continue

    after = payload.get("after")
    if after is None:
        continue  # ignore deletes / heartbeats

    buffer[topic].append(after)
    print(f"[{topic}] row received")

    # 🔥 FLUSH IMMEDIATELY IF SMALL STREAM
    if len(buffer[topic]) >= batch_size:
        write_to_minio(topic.split(".")[-1], buffer[topic])
        buffer[topic].clear()

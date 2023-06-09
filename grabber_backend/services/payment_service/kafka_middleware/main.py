from datetime import datetime
import logging
import json
from time import sleep

from confluent_kafka import Consumer, Producer, KafkaError

from grabber_backend.config.kafka import (
    KAFKA_BOOTSTRAP_SERVERS,
    AUTO_OFFSET_RESET,
    PAYMENT_CONSUMER_GROUP_ID,
)
from grabber_backend.config.database import DATABASE_CONNECTION_STRING
from grabber_backend.database_controller.database_handler import DatabaseHandler


logging.basicConfig(level=logging.INFO)

MAX_RETRIES = 6
RETRY_COOLDOWN = 10


class KafkaClient:
    AGENT_NAME = "payment_service"

    def __init__(self, bootstrap_servers):
        logging.info(f"Initializing {self.AGENT_NAME}...")
        self.database_handler = DatabaseHandler(DATABASE_CONNECTION_STRING)
        for retry in range(MAX_RETRIES):
            try:
                logging.info(f"Connecting to Kafka... {retry} attempt")
                sleep(RETRY_COOLDOWN)
                self.producer = Producer({"bootstrap.servers": bootstrap_servers})
                self.consumer = Consumer(
                    {
                        "bootstrap.servers": bootstrap_servers,
                        "group.id": PAYMENT_CONSUMER_GROUP_ID,
                        "auto.offset.reset": AUTO_OFFSET_RESET,
                    }
                )
                break
            except Exception as e:
                logging.error(f"Error initializing {self.AGENT_NAME}: {e}")
        else:
            raise Exception("Error initializing Kafka client")

    def delivery_report(self, err, msg):
        if err is not None:
            logging.error("Message delivery failed: {}".format(err))
        else:
            logging.info(
                "Message delivered to {} [{}]".format(msg.topic(), msg.partition())
            )

    def produce(self, topic_messages):
        for topic, message in topic_messages.items():
            produced_message = {
                "timestamp": datetime.now().timestamp(),
                "sender": self.AGENT_NAME,
                "message": message,
            }
            self.producer.produce(
                topic,
                self.encode_message(produced_message),
                callback=self.delivery_report,
            )
        self.producer.flush()

    def consume(self, topics):
        self.consumer.subscribe(topics)
        logging.info(f"Waiting for message")

        while True:
            msg = self.consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    print(msg.error())
                    break

            msg_value = json.loads(msg.value().decode("utf-8"))

            if msg_value.get("sender") == self.AGENT_NAME:
                continue

            logging.info(
                'Received message from topic "{}": {}'.format(
                    msg.topic(), msg.value().decode("utf-8")
                )
            )

            self.proccess(msg.topic(), msg_value)

    def close(self):
        self.consumer.close()

    def encode_message(self, message):
        return json.dumps(message).encode("utf-8")

    def proccess(self, topic, message_data):
        message = message_data.get("message")

        if topic == "order-status":
            logging.info(message)
            status = message.get("status")
            order = message.get("order_id")

            if status == "awaiting_payment":
                logging.info("Waiting for payment")
                sleep(3)
                logging.info("Payment received")
                status = "pending"

                messages_to_send = {
                    "order-status": (
                        {
                            "order_id": order,
                            "status": status,
                        }
                    )
                }
                kafka_client.produce(messages_to_send)

        else:
            logging.error(f"Unknown topic: {topic}")


if __name__ == "__main__":
    kafka_client = KafkaClient(KAFKA_BOOTSTRAP_SERVERS)

    topics = ["order-status"]
    kafka_client.consume(topics)

    kafka_client.close()

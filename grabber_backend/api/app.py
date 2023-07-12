from time import sleep
from typing import Optional, List
import logging

from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
from confluent_kafka import Producer
from sqlalchemy import text

from grabber_backend.config.kafka import KAFKA_BOOTSTRAP_SERVERS
from grabber_backend.config.database import DATABASE_CONNECTION_STRING
from grabber_backend.database_controller.database_handler import DatabaseHandler
from grabber_backend.database_controller.user import UserDatabaseHandler
from grabber_backend.database_controller.models import User
from grabber_backend.database_controller.product import ProductDatabaseHandler
from grabber_backend.database_controller.position import PositionDatabaseHandler
from grabber_backend.database_controller.models import Product, Position


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MAX_RETRIES = 5

for retry in range(MAX_RETRIES):
    try:
        sleep(5)
        logger.info("Starting Kafka producer")
        conf = {"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS}
        producer = Producer(conf)
        break
    except Exception as e:
        logger.error(f"Failed to start Kafka producer: {e}, trying again... {retry}")
else:
    logger.error("Failed to start Kafka producer, exiting...")
    exit(1)


class Order(BaseModel):
    id: Optional[int]
    user: str
    order_items: list
    total_price: float
    payment_method: str


class User(BaseModel):
    firebase_uid: str
    email: str
    store_name: str
    machine_serial_number: str
    phone_number: str


class UserUpdate(BaseModel):
    email: str = None
    store_name: str = None
    machine_serial_number: str = None
    phone_number: str = None

class ProductPosition(BaseModel):
    product_name: str
    product_description: str
    product_price: float
    peso: float
    size: str
    modified_by_user: str
    position_x: int
    position_y: int
    product_amount: int


app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


def produce_message(order: Order):
    # Convert Order to JSON and produce to Kafka
    logger.info("Sending order to Kafka")
    producer.produce("create-order", order.json())
    logger.info("Order sent to Kafka")
    producer.flush()


@app.post("/orders/")
async def create_order(order: Order, background_tasks: BackgroundTasks):
    background_tasks.add_task(produce_message, order)
    return {"status": "Order sent"}


@app.get("/orders/")
async def get_orders():
    # TODO: Implement actual database query

    # TODO: Define possible status for order - Must be (awaiting payment, pending, processing, ready to get, delivered)
    # make them as they are here but in snake_case - (awaiting_payment, pending, processing, ready_to_get, delivered)

    # TODO: Insert proper dating format

    # TODO: order_items are missing description
    return {
        "orders": [
            {
                "id": 1,
                "user": "bobross",
                "order_items": [
                    {
                        "id": 1,
                        "name": "Caixa de Papelão",
                        "price": 10.0,
                        "quantity": 2,
                        "position_x": 0,
                        "position_y": 1,
                        "size": "M",
                        "weight": 0.5,
                    },
                    {
                        "id": 2,
                        "name": "Livro: Python for Dummies",
                        "price": 20.0,
                        "quantity": 1,
                        "position_x": 0,
                        "position_y": 0,
                        "size": "M",
                        "weight": 0.3,
                    },
                ],
                "total_price": 40.0,
                "payment_method": "pix",
                "status": "pending",
                "date": 1688922791,
            },
            {
                "id": 2,
                "user": "johndoe",
                "order_items": [
                    {
                        "id": 3,
                        "name": "Controle Logitech",
                        "price": 30.0,
                        "quantity": 1,
                        "position_x": 1,
                        "position_y": 0,
                        "size": "P",
                        "weight": 0.2,
                    },
                    {
                        "id": 4,
                        "name": "Mouse Bluetooth",
                        "price": 40.0,
                        "quantity": 3,
                        "position_x": 0,
                        "position_y": 1,
                        "size": "M",
                        "weight": 0.3,
                    },
                ],
                "total_price": 150.0,
                "payment_method": "pix",
                "status": "delivered",
                "date": 1594314791,
            },
            {
                "id": 2,
                "user": "johndoe",
                "order_items": [
                    {
                        "id": 5,
                        "name": "Licor Baileys",
                        "price": 100.0,
                        "quantity": 6,
                        "position_x": 0,
                        "position_y": 2,
                        "size": "G",
                        "weight": 1.0,
                    },
                    {
                        "id": 4,
                        "name": "Mouse Bluetooth",
                        "price": 40.0,
                        "quantity": 1,
                        "position_x": 2,
                        "position_y": 2,
                        "size": "P",
                        "weight": 0.3,
                    },
                ],
                "total_price": 640.0,
                "payment_method": "pix",
                "status": "canceled",
                "date": 1594833191,
            },
        ]
    }


@app.post("/users/", status_code=status.HTTP_201_CREATED)
async def create_user(user: User):
    db_handler = DatabaseHandler(DATABASE_CONNECTION_STRING)
    logger.info(f"Creating user: {user}")
    try:
        session = db_handler.create_session()
        user_db_handler = UserDatabaseHandler(session)
        status = user_db_handler.insert_user(user)
        logger.info(f"User created: {user}")

    except Exception as e:
        logger.error(f"Failed to create/update user: {e}")
        raise HTTPException(status_code=500, detail=f"user creation failed - {e}")

    finally:
        logger.info(f"Closing database session")
        db_handler.close_session(session)

    logger.info(f"Sending response back to client")
    if status == "failed":
        raise HTTPException(status_code=409, detail="user creation failed")
    return {"message": "user created"}


# TODO - This has to be a patch request
# TODO - Instead of username we must pass the uid from the user
# TODO - We shouldn't pass the whole user to this endpoint just the properties we want to change


@app.patch("/users/{user_id}", status_code=204)
async def update_user(user_id: str, user: UserUpdate):
    logger.info(f"Updating user: {user}")
    db_handler = DatabaseHandler(DATABASE_CONNECTION_STRING)

    try:
        logger.info(f"Creating database session")
        session = db_handler.create_session()
        user_db_handler = UserDatabaseHandler(session)
        status = user_db_handler.update_user(user_id, user)
        logger.info(f"User updated: {user}")

    except Exception as e:
        logger.error(f"Failed to update user: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user")

    finally:
        db_handler.close_session(session)
    logger.info(f"Sending response back to client")
    if status == "failed":
        raise HTTPException(status_code=409, detail="User update failed")
    return {"message": "User updated"}


@app.get("/users/{user_id}", response_model=UserUpdate)
async def get_user(user_id: str):
    logger.info(f"Fetching user with user_id: {user_id}")
    db_handler = DatabaseHandler(DATABASE_CONNECTION_STRING)

    try:
        logger.info(f"Creating database session")
        session = db_handler.create_session()
        user_db_handler = UserDatabaseHandler(session)
        user = user_db_handler.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    except Exception as e:
        logger.error(f"Failed to fetch user: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user")

    finally:
        db_handler.close_session(session)
    logger.info(f"Sending response back to client")
    if isinstance(user, dict):
        return UserUpdate(**user)
    else:
        return user

@app.get("/availablePositions/")
async def get_available_positions():
    db_handler = DatabaseHandler(DATABASE_CONNECTION_STRING)
    available_positions = []    
    try:
        logger.info(f"Creating database session")
        session = db_handler.create_session()
        position_db_handler = PositionDatabaseHandler(session)
        available_positions = position_db_handler.get_available_positions()
    except Exception as e:
        logger.error(f"Failed to update user: {e}")
        raise HTTPException(status_code=500, detail="Failed to get available positions")
    finally:
        db_handler.close_session(session)
    logger.info(f"Sending response back to client")
    if status == "failed":
        raise HTTPException(status_code=409, detail="user update failed")
    return {"available_positions": available_positions}
    

@app.get("/products/")
async def get_product_position_list():
    db_handler = DatabaseHandler(DATABASE_CONNECTION_STRING)
    filled_positions = []
    try:
        session = db_handler.create_session()
        product_db_handler = ProductDatabaseHandler(session)

        filled_positions = product_db_handler.get_products()
    except Exception as e:
        logger.error(f"Failed to get products: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get product - {e}"
        )
    finally:
        logger.info(f"Closing database session")
        db_handler.close_session(session)
    return {"products": filled_positions}



@app.post("/products/", status_code=201)
async def create_product(product: ProductPosition):
    db_handler = DatabaseHandler(DATABASE_CONNECTION_STRING)
    logger.info(f"Creating product: {product}")
    try:
        session = db_handler.create_session()
        product_db_handler = ProductDatabaseHandler(session)

        status = product_db_handler.insert_product(product)
        logger.info(f"Product created: {product}")

    except Exception as e:
        logger.error(f"Failed to create/update product: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create/update product - {e}"
        )

    finally:
        logger.info(f"Closing database session")
        db_handler.close_session(session)

    logger.info(f"Sending response back to client")
    return {"status": f"{status}"}


@app.delete("/products/{product_id}")
async def delete_product(product_id: int):
    db_handler = DatabaseHandler(DATABASE_CONNECTION_STRING)
    logger.info(f"Deleting product with ID: {product_id}")
    try:
        session = db_handler.create_session()
        product_db_handler = ProductDatabaseHandler(session)

        status = product_db_handler.delete_product(product_id)
        logger.info(f"Product deleted with ID: {product_id}")

    except Exception as e:
        logger.error(f"Failed to delete product: {e}")
        return {"status": "Failed to delete product"}, 500

    finally:
        logger.info(f"Closing database session")
        db_handler.close_session(session)

    logger.info(f"Sending response back to client")
    return {"status": f"{status}"}


@app.put("/products/{product_id}")
async def update_product(product_id: int, updated_product: ProductPosition):
    db_handler = DatabaseHandler(DATABASE_CONNECTION_STRING)
    logger.info(f"Updating product with ID: {product_id}")
    try:
        session = db_handler.create_session()
        product_db_handler = ProductDatabaseHandler(session)

        status = product_db_handler.update_product(product_id, updated_product)
        logger.info(f"Product updated with ID: {product_id}")

    except Exception as e:
        logger.error(f"Failed to update product: {e}")
        return {"status": "Failed to update product"}, 500

    finally:
        logger.info(f"Closing database session")
        db_handler.close_session(session)

    logger.info(f"Sending response back to client")
    return {"status": f"{status}"}

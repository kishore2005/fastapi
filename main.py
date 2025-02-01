from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlitecloud
import logging
from datetime import datetime
from typing import Optional, Dict, List
import time
import os
import requests
import telegram
from telegram.ext import ApplicationBuilder, ContextTypes
import base64

# Configure logging
logging.basicConfig(level=logging.INFO)

# Vercel requires the app to be named "app"
app = FastAPI()
DATABASE_URL = "sqlitecloud://ce3yvllesk.sqlite.cloud:8860/newgass?apikey=kOt8yvfwRbBFka2FXT1Q1ybJKaDEtzTya3SWEGzFbvE"

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class Product(BaseModel):
    id: int
    name: str
    price: float
    image: str

class BookingDetails(BaseModel):
    name: str
    mobile: str
    address: str
    product_id: int

class BookingDetailsWithImage(BaseModel):
    name: str
    mobile: str
    address: str
    imageUrl: str

class UserBookingsRequest(BaseModel):
    mobile: str

class ImageUpload(BaseModel):
    image: str

# Retry mechanism for database connection
def connect_to_database(retries=5, delay=5):
    for i in range(retries):
        try:
            logging.info(f"Attempting to connect to the database (Attempt {i + 1}/{retries})")
            conn = sqlitecloud.connect(DATABASE_URL)
            cursor = conn.cursor()
            logging.info("Database connection successful")
            return conn, cursor
        except sqlitecloud.exceptions.SQLiteCloudException as e:
            logging.error(f"Database connection failed: {e}")
            if i < retries - 1:
                logging.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logging.error("All retries failed. Could not connect to the database.")
                raise

# Ensure the connection is properly closed after creating tables
conn, cursor = connect_to_database()
# Create the products table if it doesn't exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    image TEXT NOT NULL
)
''')

# Create the bookings table if it doesn't exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    mobile TEXT NOT NULL,
    address TEXT NOT NULL,
    product_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    product_price REAL NOT NULL,
    booking_time TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products (id)
)
''')

# Create the images table if it doesn't exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    mobile TEXT NOT NULL,
    address TEXT NOT NULL,
    imageUrl TEXT NOT NULL,
    upload_time TEXT NOT NULL
)
''')

conn.commit()
conn.close()

# Remove the create product endpoint
# @app.post("/products")
# async def create_product(product: Product):
#     # Insert new product into the database
#     cursor.execute('''
#     INSERT INTO products (id, name, price, image) VALUES (?, ?, ?, ?)
#     ''', (product.id, product.name, product.price, product.image))
#     conn.commit()
#     return {"message": "Product created successfully"}

@app.get("/products", response_model=List[Product])
async def fetch_products():
    try:
        logging.info("Fetching products")
        conn, cursor = connect_to_database()
        cursor.execute('SELECT id, image, name, price FROM products WHERE id < 11')
        products = cursor.fetchall()
        conn.close()
        product_list = []
        for product in products:
            id, image, name, price = product
            product_list.append({"id": id, "image": image, "name": name, "price": price})
        logging.info(f"Fetched products: {product_list}")
        return product_list
    except Exception as e:
        logging.error(f"Error fetching products: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/bookings/{booking_id}")
async def get_booking(booking_id: int):
    try:
        conn, cursor = connect_to_database()
        cursor.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        booking = cursor.fetchone()
        conn.close()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        booking_details = {
            "id": booking[0],
            "name": booking[1],
            "mobile": booking[2],
            "address": booking[3],
            "product_id": booking[4],
            "product_name": booking[5],
            "product_price": booking[6],
            "booking_time": booking[7]
        }
        return booking_details
    except Exception as e:
        logging.error(f"Error fetching booking: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

TELEGRAM_BOT_TOKEN = '7311171550:AAGXZ6fQWsPO30_FRZl3MCgXssvRaYFgiQM'
TELEGRAM_CHAT_IDS = ['5408718071', '6987911258']  # List of chat IDs including the new one

def send_telegram_message(message: str, chat_ids: List[str], retries=3, delay=5):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in chat_ids:
        for attempt in range(retries):
            try:
                payload = {
                    "chat_id": chat_id,
                    "text": message
                }
                logging.info(f"Sending Telegram message to {chat_id} with payload: {payload}")
                response = requests.post(url, json=payload)
                response.raise_for_status()
                logging.info(f"Message sent successfully to {chat_id}")
                break
            except requests.exceptions.RequestException as e:
                logging.error(f"Failed to send Telegram message to {chat_id}: {e}")
                if attempt < retries - 1:
                    logging.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logging.error(f"All retries failed for chat_id {chat_id}")

async def send_booking_details_to_telegram(details: BookingDetailsWithImage, product_name: str, product_price: float, booking_time: str):
    message = f"New booking received:\nName: {details.name}\nMobile: {details.mobile}\nAddress: {details.address}\nProduct: {product_name}\nPrice: {product_price}\nTime: {booking_time}\nImage: {details.imageUrl}"
    send_telegram_message(message, TELEGRAM_CHAT_IDS)

@app.post("/book")
async def book_product(details: BookingDetailsWithImage):
    try:
        conn, cursor = connect_to_database()
        cursor.execute("SELECT name, price FROM products WHERE id = ?", (details.product_id,))
        product = cursor.fetchone()
        if not product:
            conn.close()
            raise HTTPException(status_code=404, detail="Product not found")

        booking_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
        INSERT INTO bookings (name, mobile, address, product_id, product_name, product_price, booking_time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (details.name, details.mobile, details.address, details.product_id, product[0], product[1], booking_time))
        conn.commit()
        booking_id = cursor.lastrowid
        conn.close()

        # Send Telegram message
        await send_booking_details_to_telegram(details, product[0], product[1], booking_time)

        return {"message": "Booking successful", "booking_id": booking_id}
    except Exception as e:
        logging.error(f"Error booking product: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/book_product")
async def book_product(details: BookingDetailsWithImage):
    try:
        conn, cursor = connect_to_database()
        cursor.execute("SELECT name, price FROM products WHERE id = ?", (details.product_id,))
        product = cursor.fetchone()
        if not product:
            conn.close()
            raise HTTPException(status_code=404, detail="Product not found")

        booking_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
        INSERT INTO bookings (name, mobile, address, product_id, product_name, product_price, booking_time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (details.name, details.mobile, details.address, details.product_id, product[0], product[1], booking_time))
        conn.commit()
        booking_id = cursor.lastrowid
        conn.close()

        # Send Telegram message
        await send_booking_details_to_telegram(details, product[0], product[1], booking_time)

        return {"message": "Booking successful", "booking_id": booking_id}
    except Exception as e:
        logging.error(f"Error booking product: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/book_with_image")
async def book_with_image(details: BookingDetailsWithImage):
    try:
        booking_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Save image details to the database
        conn, cursor = connect_to_database()
        cursor.execute('''
        INSERT INTO images (name, mobile, address, imageUrl, upload_time)
        VALUES (?, ?, ?, ?, ?)
        ''', (details.name, details.mobile, details.address, details.imageUrl, booking_time))
        conn.commit()
        conn.close()

        # Send Telegram message
        await send_booking_details_to_telegram(details, "N/A", 0.0, booking_time)

        return {"message": "Booking sucessfull"}
    except Exception as e:
        logging.error(f"Error booking product: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/user_bookings", response_model=List[Dict])
async def get_user_bookings(request: UserBookingsRequest):
    try:
        conn, cursor = connect_to_database()
        cursor.execute('''
        SELECT bookings.*, products.image FROM bookings
        JOIN products ON bookings.product_id = products.id
        WHERE bookings.mobile = ?
        ORDER BY bookings.id DESC  
        ''', (request.mobile,))
        bookings = cursor.fetchall()
        conn.close()
        booking_list = []
        for booking in bookings:
            booking_list.append({
                "id": booking[0],
                "name": booking[1],
                "mobile": booking[2],
                "address": booking[3],
                "product_id": booking[4],
                "product_name": booking[5],
                "product_price": booking[6],
                "booking_time": booking[7],
                "product_image": booking[8]
            })
        return booking_list
    except Exception as e:
        logging.error(f"Error fetching user bookings: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/orders", response_model=List[Dict])
async def fetch_all_orders():
    try:
        conn, cursor = connect_to_database()
        cursor.execute('''
        SELECT bookings.*, products.image FROM bookings
        JOIN products ON bookings.product_id = products.id
        ORDER BY bookings.id DESC  
        ''')
        orders = cursor.fetchall()
        conn.close()
        order_list = []
        for order in orders:
            order_list.append({
                "id": order[0],
                "name": order[1],
                "mobile": order[2],
                "address": order[3],
                "product_id": order[4],
                "product_name": order[5],
                "product_price": order[6],
                "booking_time": order[7],
                "product_image": order[8]
            })
        return order_list
    except Exception as e:
        logging.error(f"Error fetching orders: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/upload_image")
async def upload_image(image: ImageUpload):
    try:
        base64_image = image.image
        logging.info(f"Received base64 image: {base64_image[:100]}...")  # Print the first 100 characters for brevity
        # You can now save the base64_image to your database or use it as needed
        return {"message": "Image uploaded successfully", "base64_image": base64_image}  # Return the full base64 string
    except Exception as e:
        logging.error(f"Error uploading image: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

def get_chat_id():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        response = requests.get(url)
        response.raise_for_status()
        updates = response.json()
        logging.info(f"Updates: {updates}")
        if updates["result"]:
            chat_id = updates["result"][-1]["message"]["chat"]["id"]
            logging.info(f"Chat ID: {chat_id}")
            return chat_id
        else:
            logging.error("No updates found. Send a message to the bot to get the chat ID.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to get chat ID: {e}")

# Test sending a message to yourself
def test_send_message():
    chat_id = get_chat_id()
    if chat_id:
        message = "Test message from bot"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message
        }
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            logging.info(f"Message sent successfully: {response.json()}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send message: {e}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    test_send_message()
    uvicorn.run(app, host="0.0.0.0", port=port)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlitecloud
import logging
from datetime import datetime
from typing import Optional, Dict, List
import time
import os

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

class UserBookingsRequest(BaseModel):
    mobile: str

# Retry mechanism for database connection
def connect_to_database(retries=5, delay=5):
    for i in range(retries):
        try:
            conn = sqlitecloud.connect(DATABASE_URL)
            cursor = conn.cursor()
            return conn, cursor
        except sqlitecloud.exceptions.SQLiteCloudException as e:
            logging.error(f"Database connection failed: {e}")
            if i < retries - 1:
                time.sleep(delay)
            else:
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

@app.post("/book")
async def book_product(details: BookingDetails):
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
        return {"message": "Booking successful", "booking_id": booking_id}
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

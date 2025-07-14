import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlitecloud
import logging
from typing import Optional, Dict, List
import base64
import requests
from datetime import datetime, timedelta
import statistics

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="Product Management API",
    description="A comprehensive API for managing products, customers, orders, and analytics",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration - Use environment variables in production
DATABASE_URL = os.getenv("DATABASE_URL", "sqlitecloud://ce3yvllesk.g4.sqlite.cloud:8860/my-app?apikey=kOt8yvfwRbBFka2FXT1Q1ybJKaDEtzTya3SWEGzFbvE")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "43dbf9c00d857313ec47281400a87ca7")
IMGBB_API_URL = "https://api.imgbb.com/1/upload"

# Get port from environment variable (for deployment platforms)
PORT = int(os.getenv("PORT", 8000))

# Pydantic models
class ProductCreate(BaseModel):
    name: str
    sell_price: Optional[float] = None
    cost_price: Optional[float] = None
    description: Optional[str] = None
    image_base64: Optional[str] = None

class Product(BaseModel):
    id: int
    name: str
    sell_price: Optional[float]
    cost_price: Optional[float]
    description: Optional[str]
    image_url: Optional[str]
    created_at: Optional[str]

class CustomerCreate(BaseModel):
    name: str
    phone_number: str
    address: Optional[str] = None
    product_id: Optional[int] = None

class Customer(BaseModel):
    id: int
    name: str
    phone_number: str
    address: Optional[str]
    product_id: Optional[int]
    created_at: Optional[str]
    last_sold_price: Optional[float]
    product_name: Optional[str]

class OrderCreate(BaseModel):
    customer_id: int
    product_id: int
    custom_price: Optional[float] = None

class OrderStatusUpdate(BaseModel):
    status: str

class Order(BaseModel):
    id: int
    customer_id: int
    product_id: int
    status: str
    created_at: Optional[str]
    custom_price: Optional[float]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    product_name: Optional[str]

class CustomerPrediction(BaseModel):
    customer_id: int
    customer_name: str
    customer_phone: str
    total_orders: int
    average_days_between_orders: float
    last_order_date: str
    predicted_next_order_date: str
    confidence_level: str

class DailySalesReport(BaseModel):
    date: str
    total_orders: int
    total_revenue: float
    total_profit: float
    delivered_orders: int
    pending_orders: int

class MonthlySalesReport(BaseModel):
    month: str
    year: int
    total_orders: int
    total_revenue: float
    total_profit: float
    delivered_orders: int
    pending_orders: int
    daily_breakdown: List[DailySalesReport]

def create_tables():
    """Initialize database tables"""
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Create products table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sell_price REAL,
            cost_price REAL,
            description TEXT,
            image_url TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create customers table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            address TEXT,
            product_id INTEGER,
            last_sold_price REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
        ''')
        
        # Create orders table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            custom_price REAL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
        ''')
        
        conn.commit()
        logging.info("Database tables created successfully")
        
    except Exception as e:
        logging.error(f"Error creating database tables: {e}")
        raise
    finally:
        conn.close()

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logging.info("Starting Product Management API...")
    create_tables()
    logging.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logging.info("Shutting down Product Management API...")

@app.get("/health")
def health_check():
    """Health check endpoint for deployment platforms"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Product Management API", 
        "version": "1.0.0", 
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }

def upload_image_to_imgbb(base64_image: str) -> Optional[str]:
    """Upload base64 image to ImgBB and return URL"""
    try:
        data = {
            'key': IMGBB_API_KEY,
            'image': base64_image,
            'name': f'product_{int(datetime.now().timestamp())}'
        }
        
        response = requests.post(IMGBB_API_URL, data=data)
        result = response.json()
        
        if result.get('success'):
            return result['data']['url']
        else:
            logging.error(f"ImgBB upload failed: {result}")
            return None
    except Exception as e:
        logging.error(f"Error uploading to ImgBB: {e}")
        return None

@app.post("/products/")
def create_product(product: ProductCreate):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Upload image if provided
        image_url = None
        if product.image_base64:
            image_url = upload_image_to_imgbb(product.image_base64)
        
        cursor.execute('''
        INSERT INTO products (name, sell_price, cost_price, description, image_url)
        VALUES (?, ?, ?, ?, ?)
        ''', (product.name, product.sell_price, product.cost_price, product.description, image_url))
        
        conn.commit()
        product_id = cursor.lastrowid
        logging.info(f"Product created with ID: {product_id}")
        
        # Get the created product
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "sell_price": row[2],
                "cost_price": row[3],
                "description": row[4],
                "image_url": row[5],
                "created_at": row[6]
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create product")
            
    except Exception as e:
        logging.error(f"Error creating product: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.get("/products/")
def get_products():
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY created_at DESC")
        products = cursor.fetchall()
        logging.info(f"Fetched {len(products)} products")
        return [{"id": p[0], "name": p[1], "sell_price": p[2], "cost_price": p[3], "description": p[4], "image_url": p[5], "created_at": p[6]} for p in products]
    except Exception as e:
        logging.error(f"Error fetching products: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.get("/products/{product_id}")
def get_product(product_id: int):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()
        
        if product:
            return {"id": product[0], "name": product[1], "sell_price": product[2], "cost_price": product[3], "description": product[4], "image_url": product[5], "created_at": product[6]}
        else:
            raise HTTPException(status_code=404, detail="Product not found")
    except Exception as e:
        logging.error(f"Error fetching product: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.put("/products/{product_id}")
def update_product(product_id: int, product_data: dict):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if product exists
        cursor.execute("SELECT id FROM products WHERE id = ?", (product_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Update product
        cursor.execute('''
        UPDATE products 
        SET name = ?, sell_price = ?, cost_price = ?, description = ?
        WHERE id = ?
        ''', (
            product_data.get('name'),
            product_data.get('sell_price'),
            product_data.get('cost_price'),
            product_data.get('description'),
            product_id
        ))
        
        conn.commit()
        logging.info(f"Product {product_id} updated successfully")
        return {"message": "Product updated successfully"}
        
    except Exception as e:
        logging.error(f"Error updating product: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.delete("/products/{product_id}")
def delete_product(product_id: int):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if product exists
        cursor.execute("SELECT id FROM products WHERE id = ?", (product_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Delete product
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        logging.info(f"Product {product_id} deleted successfully")
        return {"message": "Product deleted successfully"}
        
    except Exception as e:
        logging.error(f"Error deleting product: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.post("/customers/")
def create_customer(customer: CustomerCreate):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO customers (name, phone_number, address, product_id)
        VALUES (?, ?, ?, ?)
        ''', (customer.name, customer.phone_number, customer.address, customer.product_id))
        
        conn.commit()
        customer_id = cursor.lastrowid
        logging.info(f"Customer created with ID: {customer_id}")
        
        # Get the created customer with product name
        cursor.execute('''
        SELECT c.id, c.name, c.phone_number, c.address, c.product_id, 
               c.created_at, c.last_sold_price, p.name as product_name 
        FROM customers c 
        LEFT JOIN products p ON c.product_id = p.id 
        WHERE c.id = ?
        ''', (customer_id,))
        row = cursor.fetchone()
        
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "phone_number": row[2],
                "address": row[3],
                "product_id": row[4],
                "created_at": row[5],
                "last_sold_price": row[6],
                "product_name": row[7]
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create customer")
            
    except Exception as e:
        logging.error(f"Error creating customer: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.get("/customers/")
def get_customers():
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute('''
        SELECT c.id, c.name, c.phone_number, c.address, c.product_id, 
               c.created_at, c.last_sold_price, p.name as product_name 
        FROM customers c 
        LEFT JOIN products p ON c.product_id = p.id 
        ORDER BY c.created_at DESC
        ''')
        customers = cursor.fetchall()
        logging.info(f"Fetched {len(customers)} customers")
        return [{"id": c[0], "name": c[1], "phone_number": c[2], "address": c[3], "product_id": c[4], "created_at": c[5], "last_sold_price": c[6], "product_name": c[7]} for c in customers]
    except Exception as e:
        logging.error(f"Error fetching customers: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute('''
        SELECT c.id, c.name, c.phone_number, c.address, c.product_id, 
               c.created_at, c.last_sold_price, p.name as product_name 
        FROM customers c 
        LEFT JOIN products p ON c.product_id = p.id 
        WHERE c.id = ?
        ''', (customer_id,))
        customer = cursor.fetchone()
        
        if customer:
            return {"id": customer[0], "name": customer[1], "phone_number": customer[2], "address": customer[3], "product_id": customer[4], "created_at": customer[5], "last_sold_price": customer[6], "product_name": customer[7]}
        else:
            raise HTTPException(status_code=404, detail="Customer not found")
    except Exception as e:
        logging.error(f"Error fetching customer: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.put("/customers/{customer_id}")
def update_customer(customer_id: int, customer_data: dict):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if customer exists
        cursor.execute("SELECT id FROM customers WHERE id = ?", (customer_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Update customer
        cursor.execute('''
        UPDATE customers 
        SET name = ?, phone_number = ?, address = ?, product_id = ?
        WHERE id = ?
        ''', (
            customer_data.get('name'),
            customer_data.get('phone_number'),
            customer_data.get('address'),
            customer_data.get('product_id'),
            customer_id
        ))
        
        conn.commit()
        logging.info(f"Customer {customer_id} updated successfully")
        return {"message": "Customer updated successfully"}
        
    except Exception as e:
        logging.error(f"Error updating customer: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: int):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if customer exists
        cursor.execute("SELECT id FROM customers WHERE id = ?", (customer_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Check if customer has orders
        cursor.execute("SELECT COUNT(*) FROM orders WHERE customer_id = ?", (customer_id,))
        order_count = cursor.fetchone()[0]
        
        if order_count > 0:
            raise HTTPException(status_code=400, detail="Cannot delete customer with existing orders")
        
        # Delete customer
        cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        conn.commit()
        logging.info(f"Customer {customer_id} deleted successfully")
        return {"message": "Customer deleted successfully"}
        
    except Exception as e:
        logging.error(f"Error deleting customer: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.post("/orders/")
def create_order(order: OrderCreate):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if customer and product exist
        cursor.execute("SELECT name, phone_number FROM customers WHERE id = ?", (order.customer_id,))
        customer = cursor.fetchone()
        if not customer:
            raise HTTPException(status_code=400, detail="Customer not found")
        
        cursor.execute("SELECT name, sell_price FROM products WHERE id = ?", (order.product_id,))
        product = cursor.fetchone()
        if not product:
            raise HTTPException(status_code=400, detail="Product not found")
        
        # Use custom_price if provided, otherwise use product's sell_price
        final_price = order.custom_price if order.custom_price is not None else product[1]
        
        cursor.execute('''
        INSERT INTO orders (customer_id, product_id, custom_price, status)
        VALUES (?, ?, ?, 'pending')
        ''', (order.customer_id, order.product_id, final_price))
        
        conn.commit()
        order_id = cursor.lastrowid
        logging.info(f"Order created with ID: {order_id}")
        
        # Update customer's last_sold_price
        cursor.execute("UPDATE customers SET last_sold_price = ? WHERE id = ?", (final_price, order.customer_id))
        conn.commit()
        
        # Get the created order
        cursor.execute('''
        SELECT o.id, o.customer_id, o.product_id, o.status, o.created_at, o.custom_price,
               c.name as customer_name, c.phone_number as customer_phone, p.name as product_name
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        JOIN products p ON o.product_id = p.id
        WHERE o.id = ?
        ''', (order_id,))
        row = cursor.fetchone()
        
        if row:
            return {
                "id": row[0],
                "customer_id": row[1],
                "product_id": row[2],
                "status": row[3],
                "created_at": row[4],
                "custom_price": row[5],
                "customer_name": row[6],
                "customer_phone": row[7],
                "product_name": row[8]
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create order")
            
    except Exception as e:
        logging.error(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.get("/orders/")
def get_orders():
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute('''
        SELECT o.id, o.customer_id, o.product_id, o.status, o.created_at, o.custom_price,
               c.name as customer_name, c.phone_number as customer_phone, p.name as product_name
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        JOIN products p ON o.product_id = p.id
        ORDER BY o.created_at DESC
        ''')
        orders = cursor.fetchall()
        logging.info(f"Fetched {len(orders)} orders")
        return [{"id": o[0], "customer_id": o[1], "product_id": o[2], "status": o[3], "created_at": o[4], "custom_price": o[5], "customer_name": o[6], "customer_phone": o[7], "product_name": o[8]} for o in orders]
    except Exception as e:
        logging.error(f"Error fetching orders: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.put("/orders/{order_id}/status")
def update_order_status(order_id: int, status_update: OrderStatusUpdate):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if order exists
        cursor.execute("SELECT id FROM orders WHERE id = ?", (order_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Update order status
        cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (status_update.status, order_id))
        conn.commit()
        logging.info(f"Order {order_id} status updated to {status_update.status}")
        return {"message": "Order status updated successfully"}
        
    except Exception as e:
        logging.error(f"Error updating order status: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.delete("/orders/{order_id}")
def delete_order(order_id: int):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if order exists
        cursor.execute("SELECT id FROM orders WHERE id = ?", (order_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Delete the order
        cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()
        logging.info(f"Order {order_id} deleted successfully")
        return {"message": "Order deleted successfully"}
        
    except Exception as e:
        logging.error(f"Error deleting order: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.get("/predictions/customer-orders")
def get_customer_order_predictions():
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Get customers with 2+ orders
        cursor.execute('''
        SELECT 
            c.id,
            c.name,
            c.phone_number,
            COUNT(o.id) as total_orders,
            GROUP_CONCAT(o.created_at ORDER BY o.created_at) as order_dates
        FROM customers c
        JOIN orders o ON c.id = o.customer_id
        GROUP BY c.id, c.name, c.phone_number
        HAVING COUNT(o.id) >= 2
        ORDER BY total_orders DESC
        ''')
        
        customers_data = cursor.fetchall()
        predictions = []
        
        for customer in customers_data:
            customer_id, name, phone, total_orders, order_dates_str = customer
            
            # Parse order dates
            order_dates = [datetime.strptime(date.strip(), "%Y-%m-%d %H:%M:%S") for date in order_dates_str.split(',')]
            order_dates.sort()
            
            # Calculate days between orders
            days_between = []
            for i in range(1, len(order_dates)):
                diff = (order_dates[i] - order_dates[i-1]).days
                days_between.append(diff)
            
            # Calculate average days between orders
            avg_days = statistics.mean(days_between)
            
            # Get last order date
            last_order = order_dates[-1]
            
            # Predict next order date
            predicted_date = last_order + timedelta(days=int(avg_days))
            
            # Calculate confidence level
            if len(days_between) >= 3:
                std_dev = statistics.stdev(days_between)
                coefficient_of_variation = std_dev / avg_days
                
                if coefficient_of_variation < 0.3:
                    confidence = "High"
                elif coefficient_of_variation < 0.6:
                    confidence = "Medium"
                else:
                    confidence = "Low"
            else:
                confidence = "Low"
            
            predictions.append({
                "customer_id": customer_id,
                "customer_name": name,
                "customer_phone": phone,
                "total_orders": total_orders,
                "average_days_between_orders": round(avg_days, 1),
                "last_order_date": last_order.strftime("%Y-%m-%d"),
                "predicted_next_order_date": predicted_date.strftime("%Y-%m-%d"),
                "confidence_level": confidence
            })
        
        return predictions
        
    except Exception as e:
        logging.error(f"Error getting predictions: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.get("/reports/summary")
def get_sales_summary():
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Get overall stats
        cursor.execute('''
        SELECT 
            COUNT(o.id) as total_orders,
            SUM(COALESCE(o.custom_price, p.sell_price, 0)) as total_revenue,
            SUM(COALESCE(o.custom_price, p.sell_price, 0) - COALESCE(p.cost_price, 0)) as total_profit,
            COUNT(CASE WHEN o.status = 'delivered' THEN 1 END) as delivered_orders,
            COUNT(CASE WHEN o.status = 'pending' THEN 1 END) as pending_orders
        FROM orders o
        JOIN products p ON o.product_id = p.id
        ''')
        
        summary = cursor.fetchone()
        logging.info(f"Generated sales summary")
        return {
            "total_orders": summary[0] or 0,
            "total_revenue": float(summary[1] or 0),
            "total_profit": float(summary[2] or 0),
            "delivered_orders": summary[3] or 0,
            "pending_orders": summary[4] or 0
        }
        
    except Exception as e:
        logging.error(f"Error getting sales summary: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.get("/reports/daily")
def get_daily_sales_report(days: int = 30):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Get daily sales data
        cursor.execute('''
        SELECT 
            DATE(o.created_at) as order_date,
            COUNT(o.id) as total_orders,
            SUM(COALESCE(o.custom_price, p.sell_price, 0)) as total_revenue,
            SUM(COALESCE(o.custom_price, p.sell_price, 0) - COALESCE(p.cost_price, 0)) as total_profit,
            SUM(CASE WHEN o.status = 'delivered' THEN 1 ELSE 0 END) as delivered_orders,
            SUM(CASE WHEN o.status = 'pending' THEN 1 ELSE 0 END) as pending_orders
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.created_at >= DATE('now', '-{} days')
        GROUP BY DATE(o.created_at)
        ORDER BY order_date DESC
        '''.format(days))
        
        daily_reports = []
        for row in cursor.fetchall():
            daily_reports.append({
                "date": row[0],
                "total_orders": row[1],
                "total_revenue": round(row[2] or 0, 2),
                "total_profit": round(row[3] or 0, 2),
                "delivered_orders": row[4],
                "pending_orders": row[5]
            })
        
        return daily_reports
        
    except Exception as e:
        logging.error(f"Error getting daily report: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

@app.get("/reports/monthly")
def get_monthly_sales_report(months: int = 12):
    try:
        conn = sqlitecloud.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Get monthly sales data
        cursor.execute('''
        SELECT 
            strftime('%Y-%m', o.created_at) as order_month,
            COUNT(o.id) as total_orders,
            SUM(COALESCE(o.custom_price, p.sell_price, 0)) as total_revenue,
            SUM(COALESCE(o.custom_price, p.sell_price, 0) - COALESCE(p.cost_price, 0)) as total_profit,
            SUM(CASE WHEN o.status = 'delivered' THEN 1 ELSE 0 END) as delivered_orders,
            SUM(CASE WHEN o.status = 'pending' THEN 1 ELSE 0 END) as pending_orders
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.created_at >= DATE('now', '-{} months')
        GROUP BY strftime('%Y-%m', o.created_at)
        ORDER BY order_month DESC
        '''.format(months))
        
        monthly_reports = []
        for row in cursor.fetchall():
            monthly_reports.append({
                "month": row[0],
                "total_orders": row[1],
                "total_revenue": round(row[2] or 0, 2),
                "total_profit": round(row[3] or 0, 2),
                "delivered_orders": row[4],
                "pending_orders": row[5]
            })
        
        return monthly_reports
        
    except Exception as e:
        logging.error(f"Error getting monthly report: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        conn.close()

# Production logging configuration
logging.getLogger('passlib').setLevel(logging.ERROR)
logging.getLogger('uvicorn').setLevel(logging.INFO)
logging.getLogger('fastapi').setLevel(logging.INFO)

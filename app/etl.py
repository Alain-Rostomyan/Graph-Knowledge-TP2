"""
ETL Script: Extract data from PostgreSQL, Transform, and Load into Neo4j

This script migrates relational data from PostgreSQL to a graph structure in Neo4j,
creating nodes for customers, products, orders, categories and relationships between them.
"""

import os
import time
from pathlib import Path
from typing import List, Any
import psycopg2
import pandas as pd
from neo4j import GraphDatabase


def wait_for_postgres(max_retries: int = 30, delay: int = 2) -> None:
    """
    Wait for PostgreSQL to be ready to accept connections.
    
    Args:
        max_retries: Maximum number of connection attempts
        delay: Delay in seconds between retries
    
    Raises:
        Exception: If PostgreSQL is not ready after max_retries
    """
    print("Waiting for PostgreSQL to be ready...")
    for i in range(max_retries):
        try:
            conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "postgres"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                user=os.getenv("POSTGRES_USER", "app"),
                password=os.getenv("POSTGRES_PASSWORD", "password"),
                database=os.getenv("POSTGRES_DB", "shop")
            )
            conn.close()
            print("✓ PostgreSQL is ready!")
            return
        except psycopg2.OperationalError:
            if i < max_retries - 1:
                print(f"  Attempt {i+1}/{max_retries}: PostgreSQL not ready, retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise Exception("PostgreSQL failed to become ready")


def wait_for_neo4j(max_retries: int = 30, delay: int = 2) -> None:
    """
    Wait for Neo4j to be ready to accept connections.
    
    Args:
        max_retries: Maximum number of connection attempts
        delay: Delay in seconds between retries
    
    Raises:
        Exception: If Neo4j is not ready after max_retries
    """
    print("Waiting for Neo4j to be ready...")
    uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    
    for i in range(max_retries):
        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            with driver.session() as session:
                session.run("RETURN 1")
            driver.close()
            print("✓ Neo4j is ready!")
            return
        except Exception as e:
            if i < max_retries - 1:
                print(f"  Attempt {i+1}/{max_retries}: Neo4j not ready, retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise Exception(f"Neo4j failed to become ready: {e}")


def run_cypher(driver: GraphDatabase.driver, query: str, parameters: dict = None) -> None:
    """
    Execute a single Cypher query.
    
    Args:
        driver: Neo4j driver instance
        query: Cypher query string to execute
        parameters: Optional parameters for the query
    """
    with driver.session() as session:
        session.run(query, parameters or {})


def run_cypher_file(driver: GraphDatabase.driver, file_path: Path) -> None:
    """
    Execute multiple Cypher statements from a file.
    
    Args:
        driver: Neo4j driver instance
        file_path: Path to the .cypher file containing queries
    """
    print(f"Running Cypher file: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by semicolon and filter out comments and empty lines
    statements = [
        stmt.strip() 
        for stmt in content.split(';') 
        if stmt.strip() and not stmt.strip().startswith('//')
    ]
    
    for statement in statements:
        if statement:
            print(f"  Executing: {statement[:60]}...")
            run_cypher(driver, statement)


def chunk(data: pd.DataFrame, size: int = 500) -> List[pd.DataFrame]:
    """
    Split a DataFrame into smaller chunks for batch processing.
    
    Args:
        data: DataFrame to split
        size: Size of each chunk
    
    Returns:
        List of DataFrame chunks
    """
    return [data[i:i + size] for i in range(0, len(data), size)]


def etl():
    """
    Main ETL function that migrates data from PostgreSQL to Neo4j.
    
    This function performs the complete Extract, Transform, Load process:
    1. Waits for both databases to be ready
    2. Sets up Neo4j schema using queries.cypher file
    3. Extracts data from PostgreSQL tables
    4. Transforms relational data into graph format
    5. Loads data into Neo4j with appropriate relationships
    
    The process creates the following graph structure:
    - Category nodes with name properties
    - Product nodes linked to categories via IN_CATEGORY relationships
    - Customer nodes with name and join_date properties
    - Order nodes linked to customers via PLACED relationships
    - Order-Product relationships via CONTAINS with quantity properties
    - Dynamic event relationships between customers and products
    """
    # Ensure dependencies are ready (useful when running in docker-compose)
    wait_for_postgres()
    wait_for_neo4j()

    # Get path to your Cypher schema file
    queries_path = Path(__file__).with_name("queries.cypher")

    # Connect to PostgreSQL
    print("\n--- Connecting to PostgreSQL ---")
    pg_conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER", "app"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        database=os.getenv("POSTGRES_DB", "shop")
    )
    
    # Connect to Neo4j
    print("--- Connecting to Neo4j ---")
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    
    try:
        # 1. Setup Neo4j schema
        print("\n--- Setting up Neo4j schema (constraints & indexes) ---")
        run_cypher_file(driver, queries_path)
        
        # 2. Clear existing data (optional - for idempotent ETL)
        print("\n--- Clearing existing Neo4j data ---")
        run_cypher(driver, "MATCH (n) DETACH DELETE n")
        
        # 3. Extract data from PostgreSQL
        print("\n--- Extracting data from PostgreSQL ---")
        
        # Extract categories
        df_categories = pd.read_sql("SELECT * FROM categories", pg_conn)
        print(f"  ✓ Extracted {len(df_categories)} categories")
        
        # Extract products
        df_products = pd.read_sql("SELECT * FROM products", pg_conn)
        print(f"  ✓ Extracted {len(df_products)} products")
        
        # Extract customers
        df_customers = pd.read_sql("SELECT * FROM customers", pg_conn)
        print(f"  ✓ Extracted {len(df_customers)} customers")
        
        # Extract orders
        df_orders = pd.read_sql("SELECT * FROM orders", pg_conn)
        print(f"  ✓ Extracted {len(df_orders)} orders")
        
        # Extract order items
        df_order_items = pd.read_sql("SELECT * FROM order_items", pg_conn)
        print(f"  ✓ Extracted {len(df_order_items)} order items")
        
        # Extract events
        df_events = pd.read_sql("SELECT * FROM events", pg_conn)
        print(f"  ✓ Extracted {len(df_events)} events")
        
        # 4. Load data into Neo4j
        print("\n--- Loading data into Neo4j ---")
        
        # Load Categories
        print("  Loading categories...")
        category_query = """
        UNWIND $batch AS row
        CREATE (c:Category {id: row.id, name: row.name})
        """
        for batch in chunk(df_categories):
            records = batch.to_dict('records')
            run_cypher(driver, category_query, {"batch": records})
        print(f"    ✓ Loaded {len(df_categories)} categories")
        
        # Load Products with relationships to Categories
        print("  Loading products...")
        product_query = """
        UNWIND $batch AS row
        CREATE (p:Product {
            id: row.id, 
            name: row.name, 
            price: row.price
        })
        WITH p, row
        MATCH (c:Category {id: row.category_id})
        CREATE (p)-[:IN_CATEGORY]->(c)
        """
        for batch in chunk(df_products):
            records = batch.to_dict('records')
            run_cypher(driver, product_query, {"batch": records})
        print(f"    ✓ Loaded {len(df_products)} products")
        
        # Load Customers
        print("  Loading customers...")
        customer_query = """
        UNWIND $batch AS row
        CREATE (c:Customer {
            id: row.id, 
            name: row.name, 
            join_date: date(row.join_date)
        })
        """
        for batch in chunk(df_customers):
            records = batch.to_dict('records')
            # Convert join_date to string for Neo4j
            for record in records:
                record['join_date'] = str(record['join_date'])
            run_cypher(driver, customer_query, {"batch": records})
        print(f"    ✓ Loaded {len(df_customers)} customers")
        
        # Load Orders with relationships to Customers
        print("  Loading orders...")
        order_query = """
        UNWIND $batch AS row
        CREATE (o:Order {
            id: row.id, 
            ts: datetime(row.ts)
        })
        WITH o, row
        MATCH (c:Customer {id: row.customer_id})
        CREATE (c)-[:PLACED]->(o)
        """
        for batch in chunk(df_orders):
            records = batch.to_dict('records')
            # Convert timestamp to ISO 8601 string format
            for record in records:
                # Convert pandas Timestamp to ISO format string
                record['ts'] = record['ts'].isoformat().replace('+00:00', 'Z')
            run_cypher(driver, order_query, {"batch": records})
        print(f"    ✓ Loaded {len(df_orders)} orders")
        
        # Load Order Items (relationships between Orders and Products)
        print("  Loading order items...")
        order_item_query = """
        UNWIND $batch AS row
        MATCH (o:Order {id: row.order_id})
        MATCH (p:Product {id: row.product_id})
        CREATE (o)-[:CONTAINS {quantity: row.quantity}]->(p)
        """
        for batch in chunk(df_order_items):
            records = batch.to_dict('records')
            run_cypher(driver, order_item_query, {"batch": records})
        print(f"    ✓ Loaded {len(df_order_items)} order items")
        
        # Load Events (dynamic relationships based on event_type)
        print("  Loading events...")
        for batch in chunk(df_events):
            records = batch.to_dict('records')
            for record in records:
                event_type = record['event_type'].upper()
                # Map event types to relationship types
                rel_type_map = {
                    'VIEW': 'VIEWED',
                    'CLICK': 'CLICKED',
                    'ADD_TO_CART': 'ADDED_TO_CART'
                }
                rel_type = rel_type_map.get(event_type, 'INTERACTED_WITH')
                
                # Convert timestamp to ISO 8601 format
                ts_iso = record['ts'].isoformat().replace('+00:00', 'Z')
                
                event_query = f"""
                MATCH (c:Customer {{id: $customer_id}})
                MATCH (p:Product {{id: $product_id}})
                CREATE (c)-[:{rel_type} {{
                    event_id: $event_id,
                    ts: datetime($ts)
                }}]->(p)
                """
                run_cypher(driver, event_query, {
                    "customer_id": record['customer_id'],
                    "product_id": record['product_id'],
                    "event_id": record['id'],
                    "ts": ts_iso
                })
        print(f"    ✓ Loaded {len(df_events)} events")
        
        # 5. Verify the data
        print("\n--- Verifying loaded data ---")
        with driver.session() as session:
            result = session.run("MATCH (c:Customer) RETURN count(c) AS count")
            print(f"  Customers in Neo4j: {result.single()['count']}")
            
            result = session.run("MATCH (p:Product) RETURN count(p) AS count")
            print(f"  Products in Neo4j: {result.single()['count']}")
            
            result = session.run("MATCH (o:Order) RETURN count(o) AS count")
            print(f"  Orders in Neo4j: {result.single()['count']}")
            
            result = session.run("MATCH (cat:Category) RETURN count(cat) AS count")
            print(f"  Categories in Neo4j: {result.single()['count']}")
            
            result = session.run("MATCH ()-[r]->() RETURN count(r) AS count")
            print(f"  Total relationships: {result.single()['count']}")
        
        print("\n✓ ETL done.")
        
    finally:
        # Clean up connections
        pg_conn.close()
        driver.close()


if __name__ == "__main__":
    etl()

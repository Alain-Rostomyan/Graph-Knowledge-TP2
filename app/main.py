"""
FastAPI Application for E-Commerce Recommendation Engine

This API provides endpoints for health checks and product recommendations
based on graph analytics from Neo4j.
"""

import os
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from neo4j import GraphDatabase


# Initialize FastAPI app
app = FastAPI(
    title="E-Commerce Recommendation API",
    description="Graph-based product recommendation engine using Neo4j",
    version="1.0.0"
)


# Neo4j connection configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def get_neo4j_driver():
    """Get Neo4j driver instance."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "E-Commerce Recommendation API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "recommendations_collaborative": "/recs/collaborative/{customer_id}",
            "recommendations_similar": "/recs/similar/{product_id}",
            "recommendations_category": "/recs/category/{category_id}",
            "recommendations_trending": "/recs/trending",
            "graph_stats": "/stats"
        }
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify API and Neo4j connectivity.
    
    Returns:
        dict: Status of the service and Neo4j connection
    """
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            result = session.run("RETURN 1 AS test")
            result.single()
        driver.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/stats")
async def graph_stats():
    """
    Get statistics about the graph database.
    
    Returns:
        dict: Count of nodes and relationships in the graph
    """
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            # Count nodes by type
            customers = session.run("MATCH (c:Customer) RETURN count(c) AS count").single()["count"]
            products = session.run("MATCH (p:Product) RETURN count(p) AS count").single()["count"]
            orders = session.run("MATCH (o:Order) RETURN count(o) AS count").single()["count"]
            categories = session.run("MATCH (cat:Category) RETURN count(cat) AS count").single()["count"]
            
            # Count relationships
            total_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"]
            
        driver.close()
        
        return {
            "nodes": {
                "customers": customers,
                "products": products,
                "orders": orders,
                "categories": categories,
                "total": customers + products + orders + categories
            },
            "relationships": {
                "total": total_rels
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/recs/collaborative/{customer_id}")
async def collaborative_recommendations(
    customer_id: str,
    limit: int = Query(default=5, ge=1, le=20)
):
    """
    Get collaborative filtering recommendations based on similar customers' purchases.
    
    Strategy: Find customers who bought similar products, then recommend products
    they bought that the target customer hasn't purchased yet.
    
    Args:
        customer_id: ID of the customer to get recommendations for
        limit: Maximum number of recommendations to return
    
    Returns:
        dict: List of recommended products
    """
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            query = """
            MATCH (target:Customer {id: $customer_id})-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product)
            WITH target, collect(p) AS targetProducts
            
            MATCH (other:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product)
            WHERE other <> target AND p IN targetProducts
            WITH target, other, targetProducts, count(p) AS commonProducts
            ORDER BY commonProducts DESC
            LIMIT 10
            
            MATCH (other)-[:PLACED]->(:Order)-[:CONTAINS]->(rec:Product)
            WHERE NOT rec IN targetProducts
            WITH rec, count(DISTINCT other) AS score
            ORDER BY score DESC
            LIMIT $limit
            
            RETURN rec.id AS product_id, rec.name AS product_name, rec.price AS price, score
            """
            
            result = session.run(query, customer_id=customer_id, limit=limit)
            recommendations = [
                {
                    "product_id": record["product_id"],
                    "product_name": record["product_name"],
                    "price": float(record["price"]),
                    "score": record["score"]
                }
                for record in result
            ]
        
        driver.close()
        
        return {
            "customer_id": customer_id,
            "strategy": "collaborative_filtering",
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/recs/similar/{product_id}")
async def similar_product_recommendations(
    product_id: str,
    limit: int = Query(default=5, ge=1, le=20)
):
    """
    Get recommendations for similar products based on co-occurrence in orders.
    
    Strategy: Find products that are frequently bought together with the target product.
    
    Args:
        product_id: ID of the product to find similar products for
        limit: Maximum number of recommendations to return
    
    Returns:
        dict: List of similar products
    """
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            query = """
            MATCH (p:Product {id: $product_id})<-[:CONTAINS]-(:Order)-[:CONTAINS]->(rec:Product)
            WHERE rec <> p
            WITH rec, count(*) AS co_occurrence
            ORDER BY co_occurrence DESC
            LIMIT $limit
            
            MATCH (rec)-[:IN_CATEGORY]->(cat:Category)
            RETURN rec.id AS product_id, rec.name AS product_name, 
                   rec.price AS price, cat.name AS category, co_occurrence AS score
            """
            
            result = session.run(query, product_id=product_id, limit=limit)
            recommendations = [
                {
                    "product_id": record["product_id"],
                    "product_name": record["product_name"],
                    "price": float(record["price"]),
                    "category": record["category"],
                    "score": record["score"]
                }
                for record in result
            ]
        
        driver.close()
        
        return {
            "product_id": product_id,
            "strategy": "product_similarity",
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/recs/category/{category_id}")
async def category_recommendations(
    category_id: str,
    limit: int = Query(default=5, ge=1, le=20)
):
    """
    Get popular products from a specific category.
    
    Strategy: Find products in the category ranked by order frequency.
    
    Args:
        category_id: ID of the category
        limit: Maximum number of recommendations to return
    
    Returns:
        dict: List of popular products in the category
    """
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            query = """
            MATCH (cat:Category {id: $category_id})<-[:IN_CATEGORY]-(p:Product)
            OPTIONAL MATCH (p)<-[:CONTAINS]-(o:Order)
            WITH p, count(DISTINCT o) AS order_count
            ORDER BY order_count DESC
            LIMIT $limit
            
            RETURN p.id AS product_id, p.name AS product_name, 
                   p.price AS price, order_count AS score
            """
            
            result = session.run(query, category_id=category_id, limit=limit)
            recommendations = [
                {
                    "product_id": record["product_id"],
                    "product_name": record["product_name"],
                    "price": float(record["price"]),
                    "score": record["score"]
                }
                for record in result
            ]
        
        driver.close()
        
        return {
            "category_id": category_id,
            "strategy": "category_popularity",
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/recs/trending")
async def trending_recommendations(
    limit: int = Query(default=5, ge=1, le=20)
):
    """
    Get trending products based on recent events (views, clicks, add to cart).
    
    Strategy: Find products with the most interactions across all event types.
    
    Args:
        limit: Maximum number of recommendations to return
    
    Returns:
        dict: List of trending products
    """
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            query = """
            MATCH (c:Customer)-[r]->(p:Product)
            WHERE type(r) IN ['VIEWED', 'CLICKED', 'ADDED_TO_CART']
            WITH p, count(r) AS interaction_count
            ORDER BY interaction_count DESC
            LIMIT $limit
            
            MATCH (p)-[:IN_CATEGORY]->(cat:Category)
            RETURN p.id AS product_id, p.name AS product_name, 
                   p.price AS price, cat.name AS category, interaction_count AS score
            """
            
            result = session.run(query, limit=limit)
            recommendations = [
                {
                    "product_id": record["product_id"],
                    "product_name": record["product_name"],
                    "price": float(record["price"]),
                    "category": record["category"],
                    "score": record["score"]
                }
                for record in result
            ]
        
        driver.close()
        
        return {
            "strategy": "trending",
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/customers")
async def list_customers():
    """
    List all customers in the database.
    
    Returns:
        dict: List of customers with their details
    """
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            query = """
            MATCH (c:Customer)
            OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
            WITH c, count(DISTINCT o) AS order_count
            RETURN c.id AS customer_id, c.name AS name, 
                   c.join_date AS join_date, order_count
            ORDER BY c.name
            """
            
            result = session.run(query)
            customers = [
                {
                    "customer_id": record["customer_id"],
                    "name": record["name"],
                    "join_date": str(record["join_date"]),
                    "order_count": record["order_count"]
                }
                for record in result
            ]
        
        driver.close()
        
        return {"customers": customers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/products")
async def list_products():
    """
    List all products in the database.
    
    Returns:
        dict: List of products with their details
    """
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            query = """
            MATCH (p:Product)-[:IN_CATEGORY]->(cat:Category)
            OPTIONAL MATCH (p)<-[:CONTAINS]-(o:Order)
            WITH p, cat, count(DISTINCT o) AS order_count
            RETURN p.id AS product_id, p.name AS name, 
                   p.price AS price, cat.name AS category, order_count
            ORDER BY p.name
            """
            
            result = session.run(query)
            products = [
                {
                    "product_id": record["product_id"],
                    "name": record["name"],
                    "price": float(record["price"]),
                    "category": record["category"],
                    "order_count": record["order_count"]
                }
                for record in result
            ]
        
        driver.close()
        
        return {"products": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

// Schema Setup: Constraints and Indexes
// These ensure data integrity and query performance in Neo4j

// Create constraints for unique IDs
CREATE CONSTRAINT customer_id IF NOT EXISTS FOR (c:Customer) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT order_id IF NOT EXISTS FOR (o:Order) REQUIRE o.id IS UNIQUE;
CREATE CONSTRAINT category_id IF NOT EXISTS FOR (cat:Category) REQUIRE cat.id IS UNIQUE;

// Create indexes for better query performance
CREATE INDEX customer_name IF NOT EXISTS FOR (c:Customer) ON (c.name);
CREATE INDEX product_name IF NOT EXISTS FOR (p:Product) ON (p.name);
CREATE INDEX category_name IF NOT EXISTS FOR (cat:Category) ON (cat.name);
CREATE INDEX order_timestamp IF NOT EXISTS FOR (o:Order) ON (o.ts);

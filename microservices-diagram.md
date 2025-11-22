# Microservices Diagram

This document outlines the flowchart and details of the microservices architecture employed in the application. The diagram provides a high-level view of the interactions between different services.

## Flowchart

```mermaid
flowchart LR
    A[User Interface] --> B[API Gateway]
    B --> C[Service A]
    B --> D[Service B]
    C --> E[Database A]
    D --> F[Database B]
    D --> G[Service C]
    G --> H[Database C]
```

## Microservice Details

1. **Service A**: Responsible for managing user data and interactions.
   - **Endpoints**: `/users`, `/login`
   - **Database**: Database A (Relational)

2. **Service B**: Handles product information and inventory management.
   - **Endpoints**: `/products`, `/inventory`
   - **Database**: Database B (NoSQL)

3. **Service C**: Provides order processing and management functionalities.
   - **Endpoints**: `/orders`, `/checkout`
   - **Database**: Database C (Relational)
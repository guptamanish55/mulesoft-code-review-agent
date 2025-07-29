# 🛒 E-Commerce Integration Platform - MuleSoft Demo Project

## 📋 **Project Overview**

This is a **comprehensive, enterprise-grade MuleSoft project** designed to showcase the full capabilities of **Mule Guardian Code Review Agent**. The project implements a complete e-commerce integration platform with multiple APIs, external system integrations, file processing, and comprehensive testing.

## 🏗️ **Architecture Overview**

### **API Layer**
- **Customer API** (`/api/v1/customers`) - Complete CRUD operations for customer management
- **Order API** (`/api/v1/orders`) - Order processing, status management, and business rules
- **Product API** - Product catalog management (referenced in integrations)

### **Integration Layer**
- **CRM Synchronization** - Automated customer data sync with external CRM systems
- **File Processing** - Bulk order import from CSV files
- **JMS Messaging** - Order status notifications and event processing
- **Email Notifications** - Customer communication workflows

### **Data Layer**
- **MySQL Database** - Primary data storage for customers, orders, and products
- **Object Store** - Session and cache management
- **File System** - Document and file processing

## 📁 **Project Structure**

```
sample_demo_project/
├── pom.xml                           # Maven configuration with dependencies
├── src/
│   ├── main/
│   │   ├── mule/
│   │   │   ├── global-config.xml     # Global configurations and connections
│   │   │   ├── customer-api.xml      # Customer REST API flows
│   │   │   ├── order-api.xml         # Order REST API flows  
│   │   │   ├── integration-flows.xml # CRM sync, file processing, JMS
│   │   │   └── api-gateway.xml       # Legacy API gateway (demo violations)
│   │   └── resources/
│   │       ├── config.properties     # Application configuration
│   │       ├── application-types.xml # Data type definitions
│   │       └── log4j2.xml           # Logging configuration
│   └── test/
│       └── munit/
│           ├── customer-api-test.xml # Customer API MUnit tests
│           └── order-api-test.xml    # Order API MUnit tests
└── target/                          # Build output directory
```

## 🔧 **Key Features Demonstrated**

### **✅ API Development Best Practices**
- RESTful endpoint design with proper HTTP methods
- Request/response validation and transformation
- Error handling and status code management
- Business rule validation and enforcement

### **✅ Integration Patterns**
- **Scheduled Synchronization** - CRM customer data sync every 5 minutes
- **File-based Integration** - CSV order import with error handling
- **Event-driven Architecture** - JMS messaging for order notifications
- **External API Integration** - CRM system and payment gateway connections

### **✅ Data Management**
- Database operations (Create, Read, Update, Delete)
- Transaction management and data consistency
- Connection pooling and performance optimization
- Data transformation and mapping

### **✅ Testing & Quality Assurance**
- **MUnit Test Suites** for all major flows
- Mock configurations for external dependencies
- Positive and negative test scenarios
- Error condition testing and validation

## 🚨 **Intentional Violations for Demo**

This project contains **50+ intentional code violations** across multiple categories to demonstrate Mule Guardian's detection capabilities:

### **🔐 Security Violations**
- Hardcoded credentials in configuration files
- Sensitive data exposure in API responses (SSN, credit card numbers)
- Missing TLS/SSL configurations
- Inadequate input validation and sanitization
- SQL injection vulnerabilities in dynamic queries

### **📊 Code Quality Issues**
- Inconsistent naming conventions (`getCustomers` vs `get-customers-flow`)
- Missing error handling in critical flows
- Hardcoded business rules and configuration values
- Inadequate logging and monitoring
- Missing input validation and business rule checks

### **🏗️ Architecture Problems**
- Missing global error handlers
- Improper configuration management
- Lack of connection pooling
- Missing retry and circuit breaker patterns
- Inadequate transaction boundaries

### **🧪 Testing Deficiencies**
- Incomplete test coverage
- Missing negative test scenarios  
- Ignored critical test cases
- Inadequate mock configurations
- Missing integration and performance tests

### **📝 Documentation & Maintenance**
- Missing or inadequate documentation
- Outdated dependency versions
- Missing required Maven plugins
- Improper logging configurations
- Lack of monitoring and alerting setup

## 🚀 **Quick Start Guide**

### **Prerequisites**
- Java 11 or higher
- Maven 3.6+
- Anypoint Studio 7.x (optional)
- MySQL 8.0+ (for database operations)

### **Setup Instructions**

1. **Clone and Navigate**
   ```bash
   cd sample_demo_project
   ```

2. **Configure Database**
   ```sql
   CREATE DATABASE ecommerce_db;
   CREATE TABLE customers (
       customer_id VARCHAR(50) PRIMARY KEY,
       first_name VARCHAR(100),
       last_name VARCHAR(100),
       email VARCHAR(200),
       phone VARCHAR(20),
       ssn VARCHAR(11),
       credit_score INT,
       status VARCHAR(20),
       created_date DATETIME,
       modified_date DATETIME
   );
   
   CREATE TABLE orders (
       order_id VARCHAR(50) PRIMARY KEY,
       customer_id VARCHAR(50),
       status VARCHAR(20),
       total_amount DECIMAL(10,2),
       credit_card_number VARCHAR(20),
       credit_card_cvv VARCHAR(4),
       credit_card_expiry VARCHAR(7),
       billing_address TEXT,
       shipping_address TEXT,
       items TEXT,
       created_date DATETIME,
       modified_date DATETIME,
       processing_flags VARCHAR(200),
       internal_notes TEXT
   );
   ```

3. **Update Configuration**
   Edit `src/main/resources/config.properties`:
   ```properties
   database.host=localhost
   database.port=3306
   database.name=ecommerce_db
   database.username=your_username
   database.password=your_password
   ```

4. **Build and Run**
   ```bash
   mvn clean compile
   mvn mule:run
   ```

### **Test the APIs**

**Get Customers:**
```bash
curl -X GET http://localhost:8081/api/v1/customers
```

**Create Customer:**
```bash
curl -X POST http://localhost:8081/api/v1/customers \
  -H "Content-Type: application/json" \
  -d '{
    "firstName": "John",
    "lastName": "Doe", 
    "email": "john.doe@example.com",
    "phone": "555-0123"
  }'
```

**Create Order:**
```bash
curl -X POST http://localhost:8081/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customerId": "CUST-123",
    "totalAmount": 99.99,
    "paymentInfo": {
      "creditCardNumber": "4111111111111111",
      "cvv": "123",
      "expiry": "12/25"
    },
    "items": [
      {"productId": "PROD-001", "quantity": 2, "price": 49.99}
    ]
  }'
```

## 📊 **Mule Guardian Analysis Results**

When you run **Mule Guardian Code Review Agent** on this project, you should expect:

### **Expected Violation Counts**
- **🔴 HIGH Priority:** 15-20 violations (security, SQL injection, sensitive data)
- **🟡 MEDIUM Priority:** 20-25 violations (error handling, validation, architecture)  
- **🟢 LOW Priority:** 15-20 violations (naming, documentation, best practices)

### **Categories Covered**
- **Security** (30% of violations)
- **Code Quality** (25% of violations)
- **Error Handling** (20% of violations)
- **Naming Conventions** (15% of violations)
- **Project Structure** (10% of violations)

### **Key Highlights from Analysis**
- **Compliance Score:** ~65-70% (intentionally low for demo)
- **Critical Issues:** Hardcoded credentials, SQL injection risks
- **Improvement Areas:** Error handling, input validation, security practices
- **Best Practices:** RESTful design, proper data transformation

## 🧪 **Running MUnit Tests**

Execute the comprehensive test suite:

```bash
# Run all tests
mvn test

# Run specific test suite
mvn test -Dtest=customer-api-test.xml

# Run tests with coverage
mvn clean test jacoco:report
```

### **Test Coverage Areas**
- ✅ Customer API CRUD operations
- ✅ Order creation and status management  
- ✅ Input validation and error scenarios
- ✅ Database interaction mocking
- ✅ HTTP response validation
- ⚠️ Security testing (intentionally limited)
- ⚠️ Integration testing (mocked dependencies)

## 📈 **CI/CD Integration**

This project is designed to work seamlessly with **Mule Guardian GitHub Actions integration**:

1. **Automated Code Review** - Every pull request triggers analysis
2. **Quality Gates** - Configurable compliance thresholds  
3. **Report Generation** - HTML, JSON, and PDF formats
4. **Artifact Storage** - Reports stored for historical tracking

## 🎯 **Learning Objectives**

This comprehensive demo project helps you understand:

1. **Real-world MuleSoft Architecture** - Multi-layered, enterprise-scale design
2. **Common Violation Patterns** - What to avoid in production code
3. **Best Practice Implementation** - Proper API design and integration patterns
4. **Testing Strategy** - Comprehensive MUnit testing approach
5. **Code Review Process** - How static analysis improves code quality

## 🔧 **Advanced Configuration**

### **External System Integration** 
The project includes mock integrations for:
- **CRM System** (Salesforce-style API)
- **Payment Gateway** (Stripe-style processing)
- **Email Service** (SMTP integration)
- **File Processing** (CSV import/export)

### **Monitoring & Observability**
- Comprehensive logging with Log4j2
- Application metrics and health checks
- Error tracking and alerting
- Performance monitoring hooks

---

## 📚 **Additional Resources**

- [MuleSoft Documentation](https://docs.mulesoft.com/)
- [MUnit Testing Guide](https://docs.mulesoft.com/munit/)
- [Anypoint Exchange](https://www.mulesoft.com/exchange/)
- [MuleSoft Best Practices](https://docs.mulesoft.com/mule-runtime/latest/mule-app-dev-practices)

---

**🎉 This project provides a comprehensive foundation for demonstrating enterprise-grade MuleSoft development and the power of automated code review with Mule Guardian!** 
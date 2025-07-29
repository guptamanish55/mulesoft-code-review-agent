# Customer Management API - Clean Sample Project

## Overview
This is a **clean, well-architected MuleSoft application** that demonstrates **best practices** and **high code quality**. This project is designed to achieve **75%+ compliance** when analyzed by Mule Guardian Code Review Agent.

## Project Structure
```
sample_clean_project/
├── pom.xml                          # Maven configuration with latest versions
├── src/
│   ├── main/
│   │   ├── mule/
│   │   │   ├── global-config.xml    # Global configurations with security
│   │   │   └── customer-api.xml     # Clean REST API implementation
│   │   └── resources/
│   │       └── config.properties    # Secure configuration properties
│   └── test/
│       └── munit/
│           └── customer-api-test.xml # Comprehensive MUnit tests
└── README.md                        # Project documentation
```

## Key Features
### ✅ **Security Best Practices**
- TLS/HTTPS enabled by default
- Secure property encryption using `${secure::}` syntax
- No hardcoded credentials or sensitive data
- Proper input validation and sanitization

### ✅ **Error Handling Excellence**
- Global error handler implementation
- Comprehensive error coverage (connectivity, timeout, validation)
- Proper HTTP status codes and error responses
- Detailed logging without exposing sensitive information

### ✅ **Database Integration**
- Connection pooling configuration
- Parameterized queries (SQL injection prevention)
- Proper transaction handling
- Database connection reuse

### ✅ **Code Quality Standards**
- Consistent naming conventions
- Comprehensive documentation
- Proper flow organization and sub-flows
- Clean separation of concerns

### ✅ **Testing Coverage**
- MUnit test cases for all major scenarios
- Proper mocking of external dependencies
- Validation of both success and error cases
- Comprehensive assertions

## API Endpoints
- `GET /api/customers` - Retrieve all customers (with pagination)
- `GET /api/customers/{id}` - Retrieve customer by ID
- `POST /api/customers` - Create new customer
- `PUT /api/customers/{id}` - Update existing customer
- `DELETE /api/customers/{id}` - Soft delete customer

## Expected Mule Guardian Analysis Results
This clean project is designed to demonstrate **high-quality MuleSoft development**:

### **Target Compliance Score: 77-80%**
- **Expected Violations: ~20-23 total**
  - **HIGH Priority: 0** ✅
  - **MEDIUM Priority: 0-1** ✅ 
  - **LOW Priority: 20-23** (minor style/optimization suggestions)

### **Violation Categories:**
- **Security: 0 violations** ✅ (All credentials secured, HTTPS enabled)
- **Error Handling: 0 violations** ✅ (Comprehensive error handling)
- **Code Quality: 20-23 violations** (Minor style improvements)
- **Naming Conventions: 0 violations** ✅ (Consistent naming)

## Quality Gate Status
✅ **PASS** - This project will **pass the 75% quality gate** threshold, demonstrating that well-architected MuleSoft applications can achieve high compliance scores.

## Quick Start

### Prerequisites
- Mule Runtime 4.6.0+
- MySQL Database
- Java 11+
- Maven 3.8+

### Configuration
1. Update `config.properties` with your environment-specific values
2. Configure secure properties for sensitive data
3. Set up database connection details
4. Configure TLS certificates

### Running the Application
```bash
mvn clean package
mvn mule:run
```

### Testing
```bash
mvn test
```

## Integration with Mule Guardian
This project serves as a **positive example** for Mule Guardian analysis:

1. **Upload to GitHub** in the `clean-sample` branch
2. **Run GitHub Actions** workflow
3. **Observe 77-80% compliance** score
4. **Quality gate PASSES** (above 75% threshold)
5. **Download detailed report** showing minimal violations

## Comparison with Sample Demo Project
| Metric | Clean Project | Demo Project | Improvement |
|--------|---------------|--------------|-------------|
| Total Violations | ~22 | 31 | -29% |
| HIGH Priority | 0 | 2 | -100% |
| Security Issues | 0 | 1 | -100% |
| Compliance Score | ~78% | 64% | +22% |
| Quality Gate | ✅ PASS | ❌ FAIL | PASS |

## Key Differences from Demo Project
### ✅ **Improvements Made:**
- **Secured all credentials** using `${secure::}` properties
- **Implemented global error handler** for comprehensive error coverage
- **Added input validation** for all API endpoints
- **Used parameterized queries** to prevent SQL injection
- **Enabled HTTPS/TLS** for secure communication
- **Added connection pooling** for database optimization
- **Comprehensive MUnit tests** with proper assertions
- **Clean code organization** with proper sub-flows
- **Consistent naming conventions** throughout
- **No hardcoded values** or magic numbers

This project demonstrates that following MuleSoft best practices results in **high-quality, maintainable code** that easily passes enterprise quality standards.

---
*This project is part of the Mule Guardian Code Review demonstration suite, showcasing both problematic and exemplary MuleSoft development practices.* 
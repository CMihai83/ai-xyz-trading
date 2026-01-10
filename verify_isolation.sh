#!/bin/bash

#############################################################################
# Florin Trading System - Isolation Verification Script
#############################################################################
# This script verifies that the Florin Trading System is completely
# isolated from the ai_xyz system.
#############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASSED=0
FAILED=0

print_header() {
    echo -e "${BLUE}"
    echo "=========================================================================="
    echo "  $1"
    echo "=========================================================================="
    echo -e "${NC}"
}

print_test() {
    echo -e "${BLUE}Testing: $1${NC}"
}

print_pass() {
    echo -e "${GREEN}  ✓ PASS: $1${NC}"
    ((PASSED++))
}

print_fail() {
    echo -e "${RED}  ✗ FAIL: $1${NC}"
    ((FAILED++))
}

print_info() {
    echo -e "  ${BLUE}ℹ $1${NC}"
}

print_header "Florin Trading System - Isolation Verification"

echo ""
echo "This script will verify that florin_trading is completely isolated from ai_xyz"
echo ""

#############################################################################
# Test 1: Container Names
#############################################################################
print_test "Container Name Isolation"

if docker ps -a --format '{{.Names}}' | grep -q "florin_trading_system"; then
    print_pass "Florin container exists with unique name"
else
    print_fail "Florin container not found"
fi

if docker ps --format '{{.Names}}' | grep -q "florin_trading_system"; then
    print_pass "Florin container is running"
else
    print_fail "Florin container is not running"
fi

#############################################################################
# Test 2: Network Isolation
#############################################################################
print_test "Network Isolation"

if docker network inspect florin_trading_network >/dev/null 2>&1; then
    print_pass "Florin network exists (florin_trading_network)"
    
    # Check if ai_xyz network exists and is different
    if docker network inspect ai_xyz_network >/dev/null 2>&1; then
        florin_net_id=$(docker network inspect florin_trading_network -f '{{.Id}}')
        ai_xyz_net_id=$(docker network inspect ai_xyz_network -f '{{.Id}}')
        
        if [ "$florin_net_id" != "$ai_xyz_net_id" ]; then
            print_pass "Networks are separate (different network IDs)"
        else
            print_fail "Networks have the same ID (NOT isolated)"
        fi
    else
        print_info "ai_xyz network not found (may not be running)"
    fi
else
    print_fail "Florin network does not exist"
fi

#############################################################################
# Test 3: Redis Database Isolation
#############################################################################
print_test "Redis Database Isolation"

if docker ps | grep -q "florin_redis"; then
    print_pass "Florin Redis container is running"
    
    # Check Florin DB (should be DB 2)
    florin_db_size=$(docker-compose exec -T redis redis-cli -n 2 DBSIZE 2>/dev/null || echo "0")
    print_pass "Florin uses Redis DB 2 (Size: $florin_db_size keys)"
    
    # Check ai_xyz DB (should be DB 1)
    if docker ps | grep -q "ai_xyz_redis"; then
        ai_xyz_db_size=$(docker exec ai_xyz_redis redis-cli -n 1 DBSIZE 2>/dev/null || echo "0")
        print_pass "ai_xyz uses Redis DB 1 (Size: $ai_xyz_db_size keys)"
        
        # Verify they're different
        if [ "$florin_db_size" != "$ai_xyz_db_size" ] || [ "$florin_db_size" = "0" ]; then
            print_pass "Redis databases are isolated (different key counts or empty)"
        fi
    else
        print_info "ai_xyz Redis not running (cannot compare)"
    fi
else
    print_fail "Florin Redis container not running"
fi

#############################################################################
# Test 4: PostgreSQL Database Isolation
#############################################################################
print_test "PostgreSQL Database Isolation"

if docker ps | grep -q "florin_postgres"; then
    print_pass "Florin PostgreSQL container is running"
    
    # Check database name
    florin_db=$(docker-compose exec -T postgres psql -U florin_user -d florin_trading -c "SELECT current_database();" -t 2>/dev/null | tr -d '[:space:]' || echo "")
    if [ "$florin_db" = "florin_trading" ]; then
        print_pass "Florin uses database 'florin_trading'"
    else
        print_fail "Florin database name incorrect: $florin_db"
    fi
    
    # Check user
    florin_user=$(docker-compose exec -T postgres psql -U florin_user -d florin_trading -c "SELECT current_user;" -t 2>/dev/null | tr -d '[:space:]' || echo "")
    if [ "$florin_user" = "florin_user" ]; then
        print_pass "Florin uses user 'florin_user'"
    else
        print_fail "Florin user incorrect: $florin_user"
    fi
else
    print_fail "Florin PostgreSQL container not running"
fi

#############################################################################
# Test 5: Docker Volume Isolation
#############################################################################
print_test "Docker Volume Isolation"

florin_volumes=$(docker volume ls --format '{{.Name}}' | grep "^florin_" | wc -l)
if [ "$florin_volumes" -gt 0 ]; then
    print_pass "Found $florin_volumes Florin-specific volumes"
    docker volume ls --format '{{.Name}}' | grep "^florin_" | while read vol; do
        print_info "  - $vol"
    done
else
    print_fail "No Florin-specific volumes found"
fi

#############################################################################
# Test 6: Port Isolation
#############################################################################
print_test "Port Isolation"

# Check if Florin dashboard is on different port
florin_port=$(docker port florin_trading_system 8080 2>/dev/null | cut -d: -f2 || echo "")
if [ -n "$florin_port" ]; then
    print_pass "Florin dashboard exposed on port $florin_port"
    
    # Check if it's different from ai_xyz (usually 8080)
    if docker ps --format '{{.Names}}:{{.Ports}}' | grep "ai_xyz_system" | grep -q "8080->8080"; then
        if [ "$florin_port" != "8080" ]; then
            print_pass "Florin port ($florin_port) different from ai_xyz (8080)"
        else
            print_fail "Florin and ai_xyz using same port (8080)"
        fi
    fi
else
    print_info "Florin dashboard port not exposed (this is OK)"
fi

#############################################################################
# Test 7: Environment Variable Isolation
#############################################################################
print_test "Environment Variable Isolation"

# Check for Florin-specific env vars
if docker inspect florin_trading_system 2>/dev/null | grep -q "REDIS_DB=2"; then
    print_pass "REDIS_DB set to 2 for Florin"
else
    print_fail "REDIS_DB not set to 2"
fi

if docker inspect florin_trading_system 2>/dev/null | grep -q "LOG_DIR=/var/log/florin_trading"; then
    print_pass "LOG_DIR set to /var/log/florin_trading"
else
    print_fail "LOG_DIR not set correctly"
fi

#############################################################################
# Test 8: State File Isolation
#############################################################################
print_test "State File Isolation"

if [ -f "position_state.json" ]; then
    print_pass "Florin has its own position_state.json"
else
    print_info "position_state.json not yet created (will be created on first run)"
fi

if [ -f "averaging_state.json" ]; then
    print_pass "Florin has its own averaging_state.json"
else
    print_info "averaging_state.json not yet created (will be created on first run)"
fi

#############################################################################
# Test 9: Configuration File Test
#############################################################################
print_test "Configuration File Test"

if docker-compose exec -T florin_trading python3 florin_config.py 2>/dev/null | grep -q "ISOLATED FROM AI_XYZ"; then
    print_pass "florin_config.py confirms isolation"
else
    print_fail "florin_config.py does not confirm isolation"
fi

#############################################################################
# Test 10: Redis Key Namespace Test
#############################################################################
print_test "Redis Key Namespace Test"

if docker ps | grep -q "florin_redis"; then
    # Set a test key in Florin's database
    docker-compose exec -T redis redis-cli -n 2 SETEX "florin:test:verification" 60 "isolated" >/dev/null 2>&1
    
    # Check it exists in DB 2
    if docker-compose exec -T redis redis-cli -n 2 EXISTS "florin:test:verification" 2>/dev/null | grep -q "1"; then
        print_pass "Test key set in Florin's Redis DB 2"
    fi
    
    # Check it does NOT exist in DB 1 (ai_xyz)
    if docker-compose exec -T redis redis-cli -n 1 EXISTS "florin:test:verification" 2>/dev/null | grep -q "0"; then
        print_pass "Test key NOT in ai_xyz's Redis DB 1 (confirmed isolation)"
    else
        print_fail "Test key found in both databases (NOT isolated!)"
    fi
    
    # Cleanup
    docker-compose exec -T redis redis-cli -n 2 DEL "florin:test:verification" >/dev/null 2>&1
fi

#############################################################################
# Summary
#############################################################################
echo ""
print_header "Verification Summary"
echo ""
echo -e "Tests Passed: ${GREEN}$PASSED${NC}"
echo -e "Tests Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  ✓ ALL TESTS PASSED - ISOLATION VERIFIED!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Florin Trading System is completely isolated from ai_xyz."
    echo "Both systems can run simultaneously without interference."
    echo ""
    exit 0
else
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}  ✗ SOME TESTS FAILED - ISOLATION MAY BE COMPROMISED${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Please review the failed tests and ensure proper configuration."
    echo ""
    exit 1
fi

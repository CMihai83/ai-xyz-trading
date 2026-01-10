#!/bin/bash

#############################################################################
# Florin Trading System - Quick Start Script
#############################################################################
# This script helps you get started with the Florin Trading System
# 
# Usage:
#   ./start_florin.sh              # Interactive setup
#   ./start_florin.sh --quick      # Skip checks, start immediately
#   ./start_florin.sh --stop       # Stop the system
#   ./start_florin.sh --restart    # Restart the system
#   ./start_florin.sh --logs       # View logs
#   ./start_florin.sh --status     # Check status
#############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

#############################################################################
# Helper Functions
#############################################################################

print_header() {
    echo -e "${BLUE}"
    echo "=========================================================================="
    echo "  $1"
    echo "=========================================================================="
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

#############################################################################
# Check Functions
#############################################################################

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        echo "Please install Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    print_success "Docker is installed"
}

check_docker_compose() {
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed"
        echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
        exit 1
    fi
    print_success "Docker Compose is installed"
}

check_env_file() {
    if [ ! -f .env ]; then
        print_warning ".env file not found"
        
        if [ -f .env.example ]; then
            echo ""
            read -p "Would you like to create .env from .env.example? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                cp .env.example .env
                print_success "Created .env file"
                print_warning "Please edit .env and add your API credentials"
                echo ""
                echo "Required variables:"
                echo "  - FLORIN_BITGET_API_KEY"
                echo "  - FLORIN_BITGET_API_SECRET"
                echo "  - FLORIN_BITGET_API_PASSPHRASE"
                echo ""
                read -p "Press Enter to open .env in nano editor..." 
                nano .env
            else
                print_error "Cannot continue without .env file"
                exit 1
            fi
        else
            print_error ".env.example not found"
            exit 1
        fi
    else
        print_success ".env file exists"
        
        # Check if API keys are configured
        if grep -q "your_api_key_here" .env; then
            print_warning "API keys not configured in .env"
            echo ""
            read -p "Would you like to edit .env now? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                nano .env
            fi
        fi
    fi
}

check_port_available() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        print_warning "Port $port is already in use"
        return 1
    else
        print_success "Port $port is available"
        return 0
    fi
}

check_ai_xyz_running() {
    if docker ps | grep -q "ai_xyz_system"; then
        print_info "ai_xyz system is running (this is OK - systems are isolated)"
        return 0
    else
        print_info "ai_xyz system is not running"
        return 1
    fi
}

#############################################################################
# Main Functions
#############################################################################

do_start() {
    print_header "Starting Florin Trading System"
    
    # Check if already running
    if docker ps | grep -q "florin_trading_system"; then
        print_warning "Florin Trading System is already running"
        read -p "Would you like to restart it? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            do_restart
        fi
        return
    fi
    
    # Build and start
    print_info "Building Docker images..."
    docker-compose build
    
    print_info "Starting services..."
    docker-compose up -d
    
    # Wait for services to be healthy
    print_info "Waiting for services to start..."
    sleep 5
    
    # Check status
    if docker ps | grep -q "florin_trading_system.*Up"; then
        print_success "Florin Trading System is running!"
        echo ""
        print_info "View logs with: docker-compose logs -f florin_trading"
        print_info "Check status with: docker-compose ps"
        print_info "Stop with: docker-compose down"
        echo ""
        
        read -p "Would you like to view the logs now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker-compose logs -f florin_trading
        fi
    else
        print_error "Failed to start Florin Trading System"
        print_info "Check logs with: docker-compose logs"
    fi
}

do_stop() {
    print_header "Stopping Florin Trading System"
    
    if ! docker ps | grep -q "florin_trading_system"; then
        print_warning "Florin Trading System is not running"
        return
    fi
    
    docker-compose down
    print_success "Florin Trading System stopped"
}

do_restart() {
    print_header "Restarting Florin Trading System"
    do_stop
    sleep 2
    do_start
}

do_logs() {
    print_header "Florin Trading System Logs"
    docker-compose logs -f florin_trading
}

do_status() {
    print_header "Florin Trading System Status"
    
    echo ""
    echo "Docker Containers:"
    docker-compose ps
    
    echo ""
    echo "Resource Usage:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
        florin_trading_system florin_redis florin_postgres 2>/dev/null || \
        echo "Services not running"
    
    echo ""
    if docker ps | grep -q "florin_trading_system"; then
        print_success "Florin Trading System is RUNNING"
        
        # Check Redis connection
        if docker-compose exec -T redis redis-cli -n 2 ping > /dev/null 2>&1; then
            print_success "Redis DB 2 is accessible"
        else
            print_error "Redis DB 2 connection failed"
        fi
        
        # Check PostgreSQL
        if docker-compose exec -T postgres pg_isready -U florin_user > /dev/null 2>&1; then
            print_success "PostgreSQL is ready"
        else
            print_error "PostgreSQL connection failed"
        fi
    else
        print_error "Florin Trading System is NOT RUNNING"
    fi
    
    # Check isolation
    echo ""
    print_info "Checking isolation from ai_xyz..."
    if docker ps | grep -q "ai_xyz_system"; then
        print_info "ai_xyz is running - checking network isolation..."
        if docker network inspect florin_trading_network > /dev/null 2>&1 && \
           docker network inspect ai_xyz_network > /dev/null 2>&1; then
            print_success "Networks are isolated (florin_trading_network ≠ ai_xyz_network)"
        fi
    fi
}

show_help() {
    echo "Florin Trading System - Quick Start Script"
    echo ""
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  (none)         Interactive setup and start"
    echo "  --quick        Skip checks and start immediately"
    echo "  --start        Start the system"
    echo "  --stop         Stop the system"
    echo "  --restart      Restart the system"
    echo "  --logs         View logs (follow mode)"
    echo "  --status       Check system status"
    echo "  --help         Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                # Interactive setup"
    echo "  $0 --quick        # Quick start"
    echo "  $0 --logs         # View logs"
    echo "  $0 --status       # Check status"
    echo ""
}

#############################################################################
# Main Script
#############################################################################

case "${1:-}" in
    --quick)
        do_start
        ;;
    --start)
        do_start
        ;;
    --stop)
        do_stop
        ;;
    --restart)
        do_restart
        ;;
    --logs)
        do_logs
        ;;
    --status)
        do_status
        ;;
    --help)
        show_help
        ;;
    *)
        # Interactive mode
        print_header "Florin Trading System - Setup & Start"
        
        echo ""
        print_info "Performing pre-flight checks..."
        echo ""
        
        check_docker
        check_docker_compose
        check_env_file
        check_port_available 8081
        check_ai_xyz_running
        
        echo ""
        print_success "All checks passed!"
        echo ""
        
        read -p "Would you like to start the Florin Trading System now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            do_start
        else
            print_info "You can start the system later with: $0 --start"
        fi
        ;;
esac

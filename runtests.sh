#!/usr/bin/env bash

# Django-auditlog test runner
# Runs tests against multiple database backends using tox
# postgres / mysql run via docker
# sqlite (default) runs against local database file
# Based on django-import-export test runner

set -e

# Docker compose command detection
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    echo "❌ Docker Compose not found. Please install Docker Desktop or docker-compose."
    exit 1
fi

# Parse command line arguments
SELECTED_DB=""
TOX_ARGS=""

# Process arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --db)
            SELECTED_DB="$2"
            shift 2
            ;;
        --help|-h)
            echo "Django-auditlog test runner"
            echo ""
            echo "Usage: $0 [OPTIONS] [TOX_ARGS...]"
            echo ""
            echo "Options:"
            echo "  --db BACKEND    Run tests only for specific database backend"
            echo "                  Options: sqlite, postgres, mysql, all (default)"
            echo "  --help, -h      Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                    # Run tests on all database backends"
            echo "  $0 --db sqlite        # Run tests only on SQLite"
            echo "  $0 --db postgres      # Run tests only on PostgreSQL"
            echo "  $0 --db mysql         # Run tests only on MySQL"
            echo "  $0 -e py311-django50  # Pass tox arguments"
            exit 0
            ;;
        *)
            TOX_ARGS="$TOX_ARGS $1"
            shift
            ;;
    esac
done

# Default to all databases if not specified
if [[ -z "$SELECTED_DB" ]]; then
    SELECTED_DB="all"
fi

# Hardcoded database configurations (following django-import-export pattern)
export TEST_DB_HOST=localhost

# PostgreSQL configuration
export AUDITLOG_POSTGRESQL_USER=postgres
export AUDITLOG_POSTGRESQL_PASSWORD=postgres
export AUDITLOG_POSTGRESQL_DB=auditlog_test
export AUDITLOG_POSTGRESQL_PORT=5432

# MySQL configuration  
export AUDITLOG_MYSQL_USER=mysqluser
export AUDITLOG_MYSQL_PASSWORD=mysqlpass
export AUDITLOG_MYSQL_DB=auditlog_test
export AUDITLOG_MYSQL_PORT=3306

echo "🚀 Starting Django-auditlog test suite"
echo "======================================="
echo "Database backend(s): $SELECTED_DB"
echo ""

# Start database containers if needed
if [[ "$SELECTED_DB" == "all" || "$SELECTED_DB" == "postgres" || "$SELECTED_DB" == "mysql" ]]; then
    echo "📦 Starting database containers..."
    $COMPOSE_CMD up -d

    # Wait for PostgreSQL to be ready
    if [[ "$SELECTED_DB" == "all" || "$SELECTED_DB" == "postgres" ]]; then
        echo "⏳ Waiting for PostgreSQL to be ready..."
        for i in {1..30}; do
          if $COMPOSE_CMD exec postgres pg_isready -U postgres -d auditlog_test >/dev/null 2>&1; then
            echo "✅ PostgreSQL is ready!"
            break
          fi
          if [ $i -eq 30 ]; then
            echo "❌ PostgreSQL failed to start after 30 attempts"
            $COMPOSE_CMD down -v
            exit 1
          fi
          echo "   PostgreSQL is unavailable - sleeping (attempt $i/30)"
          sleep 2
        done
    fi

    # Wait for MySQL to be ready
    if [[ "$SELECTED_DB" == "all" || "$SELECTED_DB" == "mysql" ]]; then
        echo "⏳ Waiting for MySQL to be ready..."
        for i in {1..30}; do
          if $COMPOSE_CMD exec mysql mysqladmin ping -h 127.0.0.1 -u mysqluser --password=mysqlpass >/dev/null 2>&1; then
            echo "✅ MySQL is ready!"
            break
          fi
          if [ $i -eq 30 ]; then
            echo "❌ MySQL failed to start after 30 attempts"
            $COMPOSE_CMD down -v
            exit 1
          fi
          echo "   MySQL is unavailable - sleeping (attempt $i/30)"
          sleep 2
        done
    fi
fi

# Test with SQLite (default)
if [[ "$SELECTED_DB" == "all" || "$SELECTED_DB" == "sqlite" ]]; then
    echo ""
    echo "🧪 Running tests with SQLite..."
    echo "==============================="
    unset AUDITLOG_TEST_TYPE
    unset TEST_DB_HOST TEST_DB_USER TEST_DB_PASS TEST_DB_NAME TEST_DB_PORT
    tox $TOX_ARGS
fi

# Test with PostgreSQL
if [[ "$SELECTED_DB" == "all" || "$SELECTED_DB" == "postgres" ]]; then
    echo ""
    echo "🐘 Running tests with PostgreSQL..."
    echo "==================================="
    export AUDITLOG_TEST_TYPE=postgres
    export TEST_DB_HOST=localhost
    export TEST_DB_USER=$AUDITLOG_POSTGRESQL_USER
    export TEST_DB_PASS=$AUDITLOG_POSTGRESQL_PASSWORD
    export TEST_DB_NAME=$AUDITLOG_POSTGRESQL_DB
    export TEST_DB_PORT=$AUDITLOG_POSTGRESQL_PORT
    tox $TOX_ARGS
fi

# Test with MySQL
if [[ "$SELECTED_DB" == "all" || "$SELECTED_DB" == "mysql" ]]; then
    echo ""
    echo "🐬 Running tests with MySQL..."
    echo "=============================="
    export AUDITLOG_TEST_TYPE=mysql
    export TEST_DB_HOST=localhost
    export TEST_DB_USER=$AUDITLOG_MYSQL_USER
    export TEST_DB_PASS=$AUDITLOG_MYSQL_PASSWORD
    export TEST_DB_NAME=$AUDITLOG_MYSQL_DB
    export TEST_DB_PORT=$AUDITLOG_MYSQL_PORT
    tox $TOX_ARGS
fi

# Cleanup
if [[ "$SELECTED_DB" == "all" || "$SELECTED_DB" == "postgres" || "$SELECTED_DB" == "mysql" ]]; then
    echo ""
    echo "🧹 Cleaning up database containers..."
    $COMPOSE_CMD down -v
fi

echo ""
echo "✅ All tests completed successfully!"
echo "===================================="
#!/bin/bash
#
# AI-XYZ System Cleanup Script
# Removes duplicate services and organizes codebase
# Backs up files before deletion for safety
#

echo "🧹 AI-XYZ SYSTEM CLEANUP"
echo "========================"
echo "Creating backup before cleanup..."

# Create backup directory
BACKUP_DIR="/root/ai_xyz/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
mkdir -p "$BACKUP_DIR/tests"
mkdir -p "$BACKUP_DIR/old_services"

# Move duplicate trading systems to backup
echo "Moving duplicate trading systems..."
for file in live_trading_system.py seamless_trading_system.py fully_integrated_trading_system.py compliant_trading_system.py simple_trading_system.py continuous_trading.py; do
    if [ -f "$file" ]; then
        mv "$file" "$BACKUP_DIR/old_services/" 2>/dev/null && echo "  Moved: $file"
    fi
done

# Move old test files to backup
echo "Moving old test files..."
for file in compliance_test_suite.py comprehensive_compliance_test.py full_system_integration_test.py high_leverage_test.py live_bitget_test.py live_compliance_test.py; do
    if [ -f "$file" ]; then
        mv "$file" "$BACKUP_DIR/tests/" 2>/dev/null && echo "  Moved: $file"
    fi
done

# Keep only essential files in main directory
echo ""
echo "Organizing essential files..."
ESSENTIAL_FILES=(
    "autonomous_sync.py"
    "surplus_dump_manager.py"
    "momentum_guardian.py"
    "kelly_criterion_sizer.py"
    "smart_leverage_manager.py"
    "unified_trading_engine.py"
    "market_scanner.py"
    "runtime_config.json"
    "position_state.json"
    ".env"
    "cicd_integration.py"
    "test_scenario_generator.py"
    "edge_case_tester.py"
    "production_testing_service.py"
)

# Count files
TOTAL_BEFORE=$(ls -1 *.py 2>/dev/null | wc -l)

# Clean up Python cache
echo "Cleaning Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

# Final count
TOTAL_AFTER=$(ls -1 *.py 2>/dev/null | wc -l)
BACKUP_COUNT=$(find "$BACKUP_DIR" -type f | wc -l)

echo ""
echo "📊 CLEANUP SUMMARY"
echo "=================="
echo "Files before: $TOTAL_BEFORE"
echo "Files after: $TOTAL_AFTER"
echo "Files backed up: $BACKUP_COUNT"
echo "Backup location: $BACKUP_DIR"
echo ""
echo "✅ Cleanup complete!"
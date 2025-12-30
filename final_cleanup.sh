#!/bin/bash
#
# FINAL AI-XYZ System Cleanup
# Removes all non-essential files keeping only core components
#

echo "🧹 FINAL AI-XYZ SYSTEM CLEANUP"
echo "=============================="

# Create final backup
BACKUP_DIR="/root/ai_xyz/final_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Files to remove (duplicates, tests, old versions)
TO_REMOVE=(
    # Old test files
    "test_*.py"
    "*_test.py"
    "*compliance*.py"
    "*bitget_test*.py"
    "*integration_test*.py"
    "backtest*.py"

    # Old services
    "enable_*.py"
    "continuous_*.py"
    "advance*.py"
    "opportunity_*.py"
    "pattern_*.py"
    "signal_*.py"
    "*adaptive_position*.py"
    "*enhanced_*.py"

    # Duplicate engines
    "*portfolio*.py"
    "*balanced*.py"
    "*neural*.py"
    "basic*.py"
    "auto_*.py"

    # Old monitoring
    "*health*.py"
    "*monitor*.py"
    "debugging*.py"
    "fix_*.py"
    "apply_*.py"

    # Misc duplicates
    "open_*.py"
    "run_*.py"
    "start_*.py"
    "manual_*.py"
    "simple_*.py"
    "enhanced_*.py"
    "improved_*.py"
    "new_*.py"
)

# Move files to backup
echo "Moving non-essential files to backup..."
for pattern in "${TO_REMOVE[@]}"; do
    for file in $pattern; do
        if [ -f "$file" ]; then
            mv "$file" "$BACKUP_DIR/" 2>/dev/null && echo "  Moved: $file"
        fi
    done
done

# Essential files to keep
echo ""
echo "Keeping essential files only..."
ESSENTIAL=(
    # Core Engine (7)
    "unified_trading_engine.py"
    "autonomous_sync.py"
    "surplus_dump_manager.py"
    "momentum_guardian.py"
    "kelly_criterion_sizer.py"
    "smart_leverage_manager.py"
    "redis_state_manager.py"

    # Intelligence (3)
    "unified_market_intelligence.py"
    "self_adjusting_opportunity_discovery.py"
    "adaptive_zone_transitions.py"

    # Automation (2)
    "trailing_surplus_dumps.py"
    "autonomous_operation_system.py"

    # Testing (4)
    "cicd_integration.py"
    "test_scenario_generator.py"
    "edge_case_tester.py"
    "production_testing_service.py"

    # Core files (1)
    "market_scanner.py"
)

# Count results
BEFORE_COUNT=$(find "$BACKUP_DIR" -name "*.py" | wc -l)
AFTER_COUNT=$(ls -1 *.py 2>/dev/null | wc -l)

echo ""
echo "📊 CLEANUP RESULTS"
echo "=================="
echo "Files removed: $BEFORE_COUNT"
echo "Files remaining: $AFTER_COUNT"
echo "Backup location: $BACKUP_DIR"
echo ""
echo "✅ System cleaned!"
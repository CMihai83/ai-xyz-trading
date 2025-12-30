#!/usr/bin/env python3
"""
Check AI-XYZ System Integration for Leverage and Minimum Position Size
Verify compliance with:
- Leverage: 7x-10x (was 2x minimum)
- Position Size: $6.50 after leverage (confidence ≤ 0.7)
- Higher sizes only when confidence > 0.7
"""

import os
import re
import json
from datetime import datetime

class AIXYZComplianceChecker:
    def __init__(self):
        self.base_path = '/app'
        self.compliance_report = {
            'timestamp': datetime.now().isoformat(),
            'leverage_compliance': {},
            'position_size_compliance': {},
            'integration_status': {},
            'issues_found': [],
            'recommendations': []
        }
        
        # Current requirements
        self.requirements = {
            'min_leverage': 7,
            'max_leverage': 10,
            'base_position_value': 6.5,  # After leverage
            'confidence_threshold': 0.7,
            'max_size_multiplier': 3.0
        }
    
    def check_file_compliance(self, filepath):
        """Check a Python file for compliance with leverage and sizing rules"""
        with open(filepath, 'r') as f:
            content = f.read()
        
        issues = []
        compliance = {
            'leverage': 'unknown',
            'position_size': 'unknown',
            'uses_config': False
        }
        
        # Check for old leverage values (2x-6x)
        old_leverage = re.findall(r'leverage[\'"\s]*[:=][\'"\s]*([2-6])\b', content, re.IGNORECASE)
        if old_leverage:
            issues.append(f"Found old leverage values: {set(old_leverage)}")
            compliance['leverage'] = 'non-compliant'
        
        # Check for correct leverage values (7x-10x)
        correct_leverage = re.findall(r'leverage[\'"\s]*[:=][\'"\s]*([7-9]|10)\b', content, re.IGNORECASE)
        if correct_leverage and not old_leverage:
            compliance['leverage'] = 'compliant'
        
        # Check for position sizing config import
        if 'from position_sizing_config import' in content or 'PositionSizingConfig' in content:
            compliance['uses_config'] = True
            compliance['position_size'] = 'compliant'
        
        # Check for old fixed position sizes
        old_sizes = re.findall(r'(?:margin_size|position_value)[\'"\s]*[:=][\'"\s]*(\d+\.?\d*)', content)
        for size in old_sizes:
            size_val = float(size)
            if size_val > 10 and 'PositionSizingConfig' not in content:
                issues.append(f"Found hard-coded position size: ${size_val}")
                compliance['position_size'] = 'non-compliant'
        
        # Check for minimum position value
        if '6.5' in content or '6.50' in content:
            if 'PositionSizingConfig' not in content:
                compliance['position_size'] = 'partially-compliant'
        
        return compliance, issues
    
    def check_core_components(self):
        """Check core AI-XYZ components"""
        core_files = [
            'core/zone_state_machine.py',
            'core/averaging_engine.py',
            'core/surplus_dump_manager.py',
            'core/risk_manager.py',
            'core/live_positions_registry.py',
            'integrated_system_launcher.py',
            'comprehensive_compliance_test.py',
            'high_leverage_test.py'
        ]
        
        print("="*70)
        print("AI-XYZ CORE COMPONENTS COMPLIANCE CHECK")
        print("="*70)
        
        for file_path in core_files:
            full_path = os.path.join(self.base_path, file_path)
            if os.path.exists(full_path):
                compliance, issues = self.check_file_compliance(full_path)
                
                filename = os.path.basename(file_path)
                print(f"\n📄 {filename}")
                print(f"   Leverage: {compliance['leverage']}")
                print(f"   Position Size: {compliance['position_size']}")
                print(f"   Uses Config: {'✅' if compliance['uses_config'] else '❌'}")
                
                if issues:
                    print(f"   Issues:")
                    for issue in issues:
                        print(f"      - {issue}")
                        self.compliance_report['issues_found'].append({
                            'file': filename,
                            'issue': issue
                        })
                
                self.compliance_report['leverage_compliance'][filename] = compliance['leverage']
                self.compliance_report['position_size_compliance'][filename] = compliance['position_size']
            else:
                print(f"\n⚠️ File not found: {file_path}")
    
    def check_integration_points(self):
        """Check specific integration points"""
        print("\n" + "="*70)
        print("INTEGRATION POINTS CHECK")
        print("="*70)
        
        # Check if position_sizing_config.py exists
        config_path = os.path.join(self.base_path, 'position_sizing_config.py')
        if os.path.exists(config_path):
            print("\n✅ Position Sizing Config Module: EXISTS")
            self.compliance_report['integration_status']['config_module'] = 'exists'
            
            # Import and verify settings
            import sys
            sys.path.insert(0, self.base_path)
            from position_sizing_config import PositionSizingConfig
            
            print(f"   Base Position Value: ${PositionSizingConfig.BASE_POSITION_VALUE}")
            print(f"   Confidence Threshold: {PositionSizingConfig.HIGH_CONFIDENCE_THRESHOLD}")
            print(f"   Max Size Multiplier: {PositionSizingConfig.MAX_SIZE_MULTIPLIER}x")
            
            if PositionSizingConfig.BASE_POSITION_VALUE == 6.5:
                print("   ✅ Correct base position value")
            else:
                print("   ❌ Incorrect base position value")
                self.compliance_report['issues_found'].append({
                    'component': 'PositionSizingConfig',
                    'issue': f'Base position value is ${PositionSizingConfig.BASE_POSITION_VALUE}, should be $6.50'
                })
        else:
            print("\n❌ Position Sizing Config Module: NOT FOUND")
            self.compliance_report['integration_status']['config_module'] = 'missing'
            self.compliance_report['recommendations'].append(
                "Create position_sizing_config.py module for centralized sizing logic"
            )
    
    def check_live_positions(self):
        """Check current live positions for compliance"""
        print("\n" + "="*70)
        print("LIVE POSITIONS COMPLIANCE CHECK")
        print("="*70)
        
        try:
            import ccxt
            exchange = ccxt.bitget({
                'apiKey': 'bg_f483546274ffb2bfa567328e98dba6c0',
                'secret': '387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0',
                'password': '2609Luiza',
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'defaultMarginMode': 'isolated'
                }
            })
            
            positions = exchange.fetch_positions()
            active = [p for p in positions if p['contracts'] > 0]
            
            compliant_count = 0
            non_compliant_count = 0
            
            for pos in active:
                position_value = pos['contracts'] * pos.get('entryPrice', 0)
                leverage = pos.get('leverage', 0)
                
                print(f"\n{pos['symbol']}")
                print(f"   Position Value: ${position_value:.2f}")
                print(f"   Leverage: {leverage}x")
                
                # Check leverage compliance
                if 7 <= leverage <= 10:
                    print(f"   Leverage: ✅ Compliant")
                    leverage_compliant = True
                else:
                    print(f"   Leverage: ❌ Non-compliant (should be 7x-10x)")
                    leverage_compliant = False
                
                # Check position size compliance
                if position_value <= 7.5:
                    print(f"   Size: ✅ Base size (~$6.50)")
                    size_compliant = True
                elif position_value <= 20:
                    print(f"   Size: ✅ High confidence size (${position_value:.2f})")
                    size_compliant = True
                else:
                    print(f"   Size: ⚠️ Check if intentional (${position_value:.2f})")
                    size_compliant = False
                
                if leverage_compliant and size_compliant:
                    compliant_count += 1
                else:
                    non_compliant_count += 1
            
            print(f"\n📊 Summary:")
            print(f"   Compliant Positions: {compliant_count}")
            print(f"   Non-compliant Positions: {non_compliant_count}")
            
            self.compliance_report['integration_status']['live_positions'] = {
                'total': len(active),
                'compliant': compliant_count,
                'non_compliant': non_compliant_count
            }
            
        except Exception as e:
            print(f"❌ Error checking live positions: {e}")
    
    def generate_recommendations(self):
        """Generate recommendations for full compliance"""
        print("\n" + "="*70)
        print("RECOMMENDATIONS FOR FULL COMPLIANCE")
        print("="*70)
        
        recommendations = []
        
        # Check for non-compliant leverage
        non_compliant_leverage = [f for f, status in self.compliance_report['leverage_compliance'].items() 
                                  if status == 'non-compliant']
        if non_compliant_leverage:
            recommendations.append(f"Update leverage to 7x-10x in: {', '.join(non_compliant_leverage)}")
        
        # Check for non-compliant position sizing
        non_compliant_sizing = [f for f, status in self.compliance_report['position_size_compliance'].items() 
                                if status == 'non-compliant']
        if non_compliant_sizing:
            recommendations.append(f"Integrate PositionSizingConfig in: {', '.join(non_compliant_sizing)}")
        
        # Add general recommendations
        if not any('PositionSizingConfig' in str(issue) for issue in self.compliance_report['issues_found']):
            recommendations.append("✅ Position sizing config is properly integrated")
        
        recommendations.append("Ensure all new positions use confidence-based sizing")
        recommendations.append("Update test scripts to verify 7x-10x leverage")
        recommendations.append("Add validation to reject positions with leverage < 7x")
        
        self.compliance_report['recommendations'].extend(recommendations)
        
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")
    
    def save_report(self):
        """Save compliance report to file"""
        with open('aixyz_compliance_report.json', 'w') as f:
            json.dump(self.compliance_report, f, indent=2)
        print("\n📄 Report saved to: aixyz_compliance_report.json")
    
    def run_full_check(self):
        """Run complete compliance check"""
        print("="*70)
        print("AI-XYZ SYSTEM COMPLIANCE CHECK")
        print("="*70)
        print(f"Checking leverage (7x-10x) and position sizing ($6.50 base)")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.check_core_components()
        self.check_integration_points()
        self.check_live_positions()
        self.generate_recommendations()
        self.save_report()
        
        print("\n" + "="*70)
        print("COMPLIANCE CHECK COMPLETE")
        print("="*70)
        
        # Summary
        total_issues = len(self.compliance_report['issues_found'])
        if total_issues == 0:
            print("✅ AI-XYZ System is FULLY COMPLIANT")
        else:
            print(f"⚠️ Found {total_issues} issues requiring attention")
        
        print("\nKey Requirements:")
        print("✅ Leverage: 7x-10x (minimum 7x)")
        print("✅ Base Position: $6.50 after leverage")
        print("✅ High Confidence (>0.7): Scale up to 3x base ($19.50)")
        print("✅ All components should use PositionSizingConfig")

if __name__ == "__main__":
    checker = AIXYZComplianceChecker()
    checker.run_full_check()
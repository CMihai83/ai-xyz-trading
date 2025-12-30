#!/usr/bin/env python3
"""
Comprehensive AI-XYZ System Analysis
Generates complete documentation of active components
"""

import os
import ast
import json
from pathlib import Path
from typing import Set, Dict, List
import subprocess

class SystemAnalyzer:
    def __init__(self):
        self.root_dir = Path('/app')
        self.active_files = set()
        self.dependencies = {}
        self.all_python_files = set()
        self.unused_files = set()
        
    def get_running_processes(self) -> List[str]:
        """Get all running Python processes in ai_xyz"""
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        processes = []
        for line in result.stdout.splitlines():
            if 'python' in line and ('ai_xyz' in line or 'aixyz' in line):
                if 'grep' not in line:
                    # Extract the script name
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if '.py' in part:
                            script = part.split('/')[-1]
                            processes.append(script)
                            break
        return list(set(processes))
    
    def get_imports(self, file_path: Path) -> Set[str]:
        """Extract all imports from a Python file"""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            tree = ast.parse(content)
            
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module)
                        for alias in node.names:
                            imports.add(f"{node.module}.{alias.name}")
            return imports
        except Exception as e:
            return set()
    
    def trace_dependencies(self, start_file: str, visited: Set[str] = None):
        """Recursively trace all dependencies from a starting file"""
        if visited is None:
            visited = set()
        
        if start_file in visited:
            return visited
        
        visited.add(start_file)
        
        file_path = self.root_dir / start_file
        if not file_path.exists():
            # Check in subdirectories
            for subdir in ['core', 'services', 'services/api-gateway/src']:
                alt_path = self.root_dir / subdir / start_file
                if alt_path.exists():
                    file_path = alt_path
                    break
        
        if file_path.exists():
            imports = self.get_imports(file_path)
            
            for imp in imports:
                # Check if it's a local module
                base_module = imp.split('.')[0]
                py_file = f"{base_module}.py"
                
                # Check various locations
                for location in ['', 'core/', 'services/']:
                    check_path = self.root_dir / location / py_file
                    if check_path.exists():
                        self.trace_dependencies(f"{location}{py_file}", visited)
        
        return visited
    
    def analyze(self):
        """Main analysis function"""
        # Get running processes
        running = self.get_running_processes()
        
        # Add manually identified core files
        running.extend([
            'aixyz_continuous_profit_system.py',
            'automatic_surplus_executor.py',
            'exchange_connector.py'
        ])
        running = list(set(running))
        
        print(f"Found {len(running)} running services:")
        for svc in running:
            print(f"  - {svc}")
        
        # Trace all dependencies
        for service in running:
            deps = self.trace_dependencies(service)
            self.active_files.update(deps)
            self.dependencies[service] = deps
        
        # Find all Python files
        for file in self.root_dir.glob('**/*.py'):
            if not any(skip in str(file) for skip in ['venv/', '__pycache__', '.pyc']):
                rel_path = str(file.relative_to(self.root_dir))
                self.all_python_files.add(rel_path)
        
        # Identify unused files
        self.unused_files = self.all_python_files - self.active_files
        
        # Generate report
        self.generate_report()
    
    def generate_report(self):
        """Generate comprehensive report"""
        report = {
            'running_services': list(self.dependencies.keys()),
            'total_active_files': len(self.active_files),
            'total_python_files': len(self.all_python_files),
            'unused_files_count': len(self.unused_files),
            'active_files': sorted(list(self.active_files)),
            'unused_files': sorted(list(self.unused_files))
        }
        
        # Save to JSON
        with open('system_analysis.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n=== SYSTEM ANALYSIS SUMMARY ===")
        print(f"Total Python files: {len(self.all_python_files)}")
        print(f"Active files: {len(self.active_files)}")
        print(f"Unused files: {len(self.unused_files)}")
        print(f"\nReport saved to system_analysis.json")

if __name__ == '__main__':
    analyzer = SystemAnalyzer()
    analyzer.analyze()

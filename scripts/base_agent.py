"""
Base Agent Class for Accessibility Testing
All persona agents inherit from this class
"""

from abc import ABC, abstractmethod
import json
from datetime import datetime
from pathlib import Path


class BaseAgent(ABC):
    """
    Abstract base class for all persona agents.
    
    Each persona agent must implement:
    - run_tool(): Execute the assistive technology or testing tool
    - analyze_output(): Analyze tool output for accessibility issues
    """
    
    def __init__(self, persona_name, persona_description):
        """
        Initialize the agent.
        
        Args:
            persona_name (str): Name of the persona (e.g., "Lakshmi")
            persona_description (str): Brief description of persona and their needs
        """
        self.persona_name = persona_name
        self.persona_description = persona_description
        self.results = []
        
    @abstractmethod
    def run_tool(self, url_or_html):
        """
        Run the assistive technology or testing tool.
        
        Args:
            url_or_html (str): Either a URL to test or HTML content
            
        Returns:
            dict: Raw output from the tool
            
        Example return:
        {
            'tool': 'NVDA',
            'version': '2024.1',
            'output': [...list of announcements...],
            'timestamp': '2024-02-05T14:30:00'
        }
        """
        pass
    
    @abstractmethod
    def analyze_output(self, tool_output):
        """
        Analyze tool output for accessibility issues.
        
        Args:
            tool_output (dict): Output from run_tool()
            
        Returns:
            list: List of issues found
            
        Example return:
        [
            {
                'wcag_criterion': '1.1.1',
                'issue_type': 'uninformative_alt_text',
                'severity': 'critical',
                'evidence': 'NVDA announced: "graphic"',
                'element': '<img src="product.jpg" alt="image">',
                'recommendation': 'Add descriptive alt text'
            }
        ]
        """
        pass
    
    def evaluate(self, url_or_html):
        """
        Main evaluation method - run tool and analyze output.
        
        Args:
            url_or_html (str): URL or HTML to evaluate
            
        Returns:
            dict: Complete evaluation result
        """
        print(f"[{self.persona_name}] Starting evaluation...")
        
        # Run the tool
        tool_output = self.run_tool(url_or_html)
        
        # Analyze output
        issues = self.analyze_output(tool_output)
        
        # Format result
        result = {
            'persona': self.persona_name,
            'persona_description': self.persona_description,
            'timestamp': datetime.now().isoformat(),
            'input': url_or_html[:100] + '...' if len(url_or_html) > 100 else url_or_html,
            'tool_used': tool_output.get('tool', 'unknown'),
            'issues_found_count': len(issues),
            'issues': issues,
            'label': self._determine_label(issues)
        }
        
        self.results.append(result)
        
        print(f"[{self.persona_name}] Evaluation complete. Found {len(issues)} issues.")
        
        return result
    
    def _determine_label(self, issues):
        """
        Determine overall label based on issues found.
        
        Args:
            issues (list): List of issues
            
        Returns:
            str: 'PASS', 'FAIL', or 'PARTIAL'
        """
        if not issues:
            return 'PASS'
        
        # If any critical issues, it's a FAIL
        critical_issues = [i for i in issues if i.get('severity') == 'critical']
        if critical_issues:
            return 'FAIL'
        
        # If only moderate/minor issues, it's PARTIAL
        return 'PARTIAL'
    
    def save_results(self, filepath):
        """
        Save all evaluation results to JSON file.
        
        Args:
            filepath (str): Path to save results
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"[{self.persona_name}] Results saved to {filepath}")
    
    def get_summary(self):
        """
        Get summary of all evaluations performed.
        
        Returns:
            dict: Summary statistics
        """
        if not self.results:
            return {
                'evaluations_performed': 0,
                'total_issues': 0
            }
        
        total_issues = sum(r['issues_found_count'] for r in self.results)
        
        # Count by severity
        all_issues = []
        for r in self.results:
            all_issues.extend(r['issues'])
        
        severity_counts = {
            'critical': sum(1 for i in all_issues if i.get('severity') == 'critical'),
            'serious': sum(1 for i in all_issues if i.get('severity') == 'serious'),
            'moderate': sum(1 for i in all_issues if i.get('severity') == 'moderate'),
            'minor': sum(1 for i in all_issues if i.get('severity') == 'minor')
        }
        
        return {
            'persona': self.persona_name,
            'evaluations_performed': len(self.results),
            'total_issues': total_issues,
            'severity_breakdown': severity_counts,
            'pass_rate': sum(1 for r in self.results if r['label'] == 'PASS') / len(self.results)
        }
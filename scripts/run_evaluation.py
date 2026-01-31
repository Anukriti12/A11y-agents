"""
Script to run evaluations on test scenarios
"""

import json
from pathlib import Path
from lakshmi_agent import LakshmiAgent


def load_scenario(scenario_path):
    """Load a test scenario from JSON file"""
    with open(scenario_path, 'r') as f:
        return json.load(f)


def evaluate_scenario(agent, scenario):
    """
    Evaluate a scenario with an agent and compare to expected results.
    
    Args:
        agent: The persona agent instance
        scenario: Scenario dictionary loaded from JSON
        
    Returns:
        dict: Comparison results
    """
    # Get HTML from scenario
    html = scenario['html']
    
    # Run agent evaluation
    result = agent.evaluate(html)
    
    # Get expected result for this persona
    persona_name = agent.persona_name.lower()
    expected = scenario['expected_results'].get(persona_name, {})
    
    # Compare
    comparison = {
        'scenario_id': scenario['scenario_id'],
        'expected_label': expected.get('result', 'UNKNOWN'),
        'agent_label': result['label'],
        'match': expected.get('result', 'UNKNOWN') == result['label'],
        'expected_issues': expected.get('reasoning', ''),
        'agent_found': result['issues_found_count'],
        'agent_issues': result['issues']
    }
    
    return comparison


def main():
    """Run evaluation on all scenarios for Lakshmi"""
    
    # Initialize agent
    agent = LakshmiAgent()
    
    # Path to scenarios
    scenarios_dir = Path('scenarios/shared')
    
    # Results
    all_comparisons = []
    
    # Evaluate each scenario
    for scenario_file in scenarios_dir.glob('*.json'):
        print(f"\n{'='*60}")
        print(f"Evaluating: {scenario_file.name}")
        print('='*60)
        
        scenario = load_scenario(scenario_file)
        comparison = evaluate_scenario(agent, scenario)
        
        all_comparisons.append(comparison)
        
        # Print comparison
        print(f"Expected: {comparison['expected_label']}")
        print(f"Agent:    {comparison['agent_label']}")
        print(f"Match:    {'✓' if comparison['match'] else '✗'}")
        print(f"\nAgent found {comparison['agent_found']} issues:")
        for issue in comparison['agent_issues']:
            print(f"  - {issue['issue_type']}: {issue['evidence']}")
    
    # Calculate metrics
    total = len(all_comparisons)
    matches = sum(1 for c in all_comparisons if c['match'])
    accuracy = matches / total if total > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"OVERALL RESULTS")
    print('='*60)
    print(f"Scenarios evaluated: {total}")
    print(f"Matches: {matches}")
    print(f"Accuracy: {accuracy:.2%}")
    
    # Save results
    results_path = Path('results/lakshmi_evaluation.json')
    results_path.parent.mkdir(exist_ok=True)
    
    with open(results_path, 'w') as f:
        json.dump({
            'agent': 'Lakshmi',
            'comparisons': all_comparisons,
            'summary': {
                'total_scenarios': total,
                'matches': matches,
                'accuracy': accuracy
            }
        }, f, indent=2)
    
    print(f"\nResults saved to {results_path}")


if __name__ == "__main__":
    main()
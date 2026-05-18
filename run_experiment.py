"""
Main Experiment Runner
Runs 3 conditions × N snippets × 3 repetitions
"""

import json
import os
from datetime import datetime
from dotenv import load_dotenv

from conditions.condition_a_axe_baseline import AxeCoreBaseline
from conditions.condition_b_generic_llm import GenericLLMBaseline
from personas.stefan_agent import StefanAgent
from personas.sophie_agent import SophieAgent
from personas.ade_agent import AdeAgent
from personas.lakshmi_agent import LakshmiAgent
from personas.elias_agent import EliasAgent
from personas.ian_agent import IanAgent

load_dotenv()


def load_corpus(path):
    with open(path) as f:
        return json.load(f)


def save_result(result, output_path):
    with open(output_path, 'a') as f:
        f.write(json.dumps(result) + '\n')


def run_experiment(corpus_path, output_path, num_snippets=None):
    print("=" * 70)
    print("ACCESSIBILITY EVALUATION EXPERIMENT")
    print("=" * 70)
    
    # Initialize conditions
    api_key = os.environ["OPENAI_API_KEY"]
    
    condition_a = AxeCoreBaseline()
    condition_b = GenericLLMBaseline(api_key)
    
    persona_agents = {
        "stefan": StefanAgent(api_key),
        "sophie": SophieAgent(api_key),
        "ade": AdeAgent(api_key),
        "lakshmi": LakshmiAgent(api_key),
        "elias": EliasAgent(api_key),
        "ian": IanAgent(api_key)
    }
    
    # Load corpus
    corpus = load_corpus(corpus_path)
    if num_snippets:
        corpus = corpus[:num_snippets]
    
    total_evals = len(corpus) * 3 * 3  # 3 conditions, 3 reps
    completed = 0
    
    print(f"Corpus: {len(corpus)} snippets")
    print(f"Total evaluations: {total_evals}")
    print()
    
    # Run experiment
    for snippet in corpus:
        snippet_id = snippet['snippet_id']
        html = snippet['html']
        persona = snippet.get('primary_persona', 'stefan')
        
        print(f"\n{'='*70}")
        print(f"Snippet: {snippet_id} (Persona: {persona})")
        print(f"{'='*70}")
        
        # Condition A: axe-core (3 reps)
        for rep in range(3):
            print(f"  Condition A (axe), Rep {rep+1}/3...")
            
            try:
                result = condition_a.evaluate(html)
                
                output = {
                    "snippet_id": snippet_id,
                    "condition": "A_axe_baseline",
                    "persona": None,
                    "repetition": rep,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    **result
                }
                
                save_result(output, output_path)
                completed += 1
                print(f"    ✓ {completed}/{total_evals}")
                
            except Exception as e:
                print(f"    ✗ Error: {e}")
                error_output = {
                    "snippet_id": snippet_id,
                    "condition": "A_axe_baseline",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                save_result(error_output, output_path)
        
        # Condition B: Generic LLM (3 reps)
        for rep in range(3):
            print(f"  Condition B (Generic LLM), Rep {rep+1}/3...")
            
            try:
                result = condition_b.evaluate(html)
                
                output = {
                    "snippet_id": snippet_id,
                    "condition": "B_generic_llm",
                    "persona": None,
                    "repetition": rep,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    **result
                }
                
                save_result(output, output_path)
                completed += 1
                print(f"    ✓ {completed}/{total_evals}")
                
            except Exception as e:
                print(f"    ✗ Error: {e}")
                error_output = {
                    "snippet_id": snippet_id,
                    "condition": "B_generic_llm",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                save_result(error_output, output_path)
        
        # Condition C: Persona Agent (3 reps)
        agent = persona_agents[persona]
        
        for rep in range(3):
            print(f"  Condition C ({persona}), Rep {rep+1}/3...")
            
            try:
                result = agent.evaluate(html)
                
                output = {
                    "snippet_id": snippet_id,
                    "condition": "C_persona_agent",
                    "persona": persona,
                    "repetition": rep,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    **result
                }
                
                save_result(output, output_path)
                completed += 1
                print(f"    ✓ {completed}/{total_evals}")
                
            except Exception as e:
                print(f"    ✗ Error: {e}")
                error_output = {
                    "snippet_id": snippet_id,
                    "condition": "C_persona_agent",
                    "persona": persona,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                save_result(error_output, output_path)
    
    print("\n" + "=" * 70)
    print("EXPERIMENT COMPLETE")
    print(f"Completed: {completed}/{total_evals}")
    print(f"Results: {output_path}")
    print("=" * 70)


if __name__ == "__main__":
    # Create results directory
    os.makedirs("results", exist_ok=True)
    
    # Run with test corpus (3 snippets = 27 evaluations)
    run_experiment(
        corpus_path="corpus/full_corpus.json",
        output_path="results/experiment_results.jsonl"
        # num_snippets=3 
        
        # Remove for full run
    )
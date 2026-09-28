import json
from legal_assistant.agent.orchestrator import run_orchestrator
from legal_assistant.agent.race_evaluation import RACE_CASES

report = run_orchestrator('What is the late payment fee?')
print(json.dumps({'completed': report['completed'], 'token_count': report['token_count'], 'cost': report['estimated_cost_usd'], 'elapsed': report['elapsed_seconds'], 'tool_calls': report['tool_calls'], 'question_count': len(RACE_CASES)}, indent=2))

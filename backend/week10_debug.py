import json
from legal_assistant.agent.orchestrator import run_orchestrator

report = run_orchestrator('What is the late payment fee?')
print(json.dumps({
    'completed': report['completed'],
    'token_count': report['token_count'],
    'estimated_cost_usd': report['estimated_cost_usd'],
    'elapsed_seconds': report['elapsed_seconds'],
    'tool_calls': report['tool_calls'],
    'strategy': report['strategy'],
    'result': report['result'],
}, indent=2))

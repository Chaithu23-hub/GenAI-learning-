# Recoverable tool error transcript

## Before

Call: `get_contract_clause(contract_id="MSA-2021-0142", clause_number="12.4")`

Tool docstring: `Get a contract clause.`

Tool result: `Error 3`

Model response: `I cannot determine whether clause 12.4 exists.`

## After

Call: `get_contract_clause(contract_id="MSA-2021-0142", clause_number="12.4")`

Tool docstring prompt: `Use this read-only tool to return one clause, or explain the available range when it is absent.`

Tool result: `No clause 12.4 in MSA-2021-0142 as amended: clauses run 1-11; see Amendment 2 effective 2023-06-01.`

Model response: `Clause 12.4 is not present in the executed agreement. The repository reports clauses 1-11 and points to Amendment 2, effective 2023-06-01, for the amendment context.`
